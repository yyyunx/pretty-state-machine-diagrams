"""Regression checks for the builder, validator, serializer and CLI."""

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from src.model import MockConverterAdapter, ModelError, build_model, serialize_model, transform_model, validate_model

ROOT = Path(__file__).resolve().parents[2]
MOCK_FILE = ROOT / "tests/model/cases/mock-converter-p1.json"


def read_json(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


class ModelTests(unittest.TestCase):
    def test_accepts_all_explicit_pseudostate_kinds_through_the_builder(self):
        kinds = (
            "initial", "choice", "junction", "fork", "join", "shallowHistory",
            "deepHistory", "entryPoint", "exitPoint", "terminate",
        )
        vertices = [{"kind": "pseudostate", "pseudostateKind": kind} for kind in kinds]
        vertices.append({"kind": "final"})
        model = build_model({"regions": [{"vertices": vertices, "transitions": []}]})
        serialized = json.loads(serialize_model(model))
        actual = serialized["regions"][0]["vertices"]
        self.assertEqual([vertex["pseudostateKind"] for vertex in actual[:-1]], list(kinds))
        self.assertEqual(actual[-1]["kind"], "final")
        self.assertEqual(len({vertex["id"] for vertex in actual}), len(vertices))
        self.assertTrue(all("displayName" not in vertex for vertex in actual))

    def test_preserves_names_and_cross_level_endpoints_without_mutating_the_draft(self):
        draft = read_json("examples/nested-orthogonal.smd.json")
        root = draft["regions"][0]
        root["transitions"][0]["targetId"] = "move"
        del root["id"]
        root["displayName"] = "root"
        original = deepcopy(draft)

        model = build_model(draft)
        self.assertEqual(draft, original)
        self.assertEqual(model["regions"][0]["displayName"], "root")
        self.assertEqual(model["regions"][0]["transitions"][0]["targetId"], "move")
        model["regions"][0]["vertices"].clear()
        self.assertEqual(draft, original)

    def test_generated_id_never_repairs_a_dangling_endpoint(self):
        draft = read_json("examples/basic.smd.json")
        region = draft["regions"][0]
        region["vertices"].append({"kind": "state"})
        region["transitions"][0]["targetId"] = "vertex-1"
        with self.assertRaises(ModelError) as captured:
            build_model(draft)
        self.assertEqual(captured.exception.diagnostics[0].code, "invalid-endpoint")
        self.assertEqual(captured.exception.diagnostics[0].path, "/regions/0/transitions/0/targetId")

    def test_node_shape_error_points_to_the_disallowed_property(self):
        model = read_json("examples/basic.smd.json")
        model["regions"][0]["vertices"][1]["regions"] = [
            {"id": "unexpected", "vertices": [], "transitions": []}
        ]
        with self.assertRaises(ModelError) as captured:
            validate_model(model)
        self.assertEqual(len(captured.exception.diagnostics), 1)
        error = captured.exception.diagnostics[0]
        self.assertEqual((error.code, error.path), ("invalid-hierarchy", "/regions/0/vertices/1/regions"))

    def test_serializer_rejects_an_invalid_edited_model(self):
        model = build_model(read_json("examples/basic.smd.json"))
        model["regions"][0]["vertices"][1]["displayName"] = " "
        with self.assertRaisesRegex(ModelError, "invalid-display-name at /regions/0/vertices/1/displayName"):
            serialize_model(model)

    def test_builder_assigns_separate_ids_to_a_reused_anonymous_template(self):
        anonymous = {"kind": "state"}
        draft = {"regions": [
            {"vertices": [anonymous], "transitions": []},
            {"vertices": [anonymous], "transitions": []},
        ]}
        model = build_model(draft)
        first, second = (region["vertices"][0] for region in model["regions"])
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(model, build_model(json.loads(json.dumps(draft))))
        self.assertEqual(anonymous, {"kind": "state"})

        anonymous["id"] = "explicit"
        with self.assertRaisesRegex(ModelError, "duplicate-id"):
            build_model(draft)

    def test_builder_reports_circular_containment(self):
        model = {"regions": []}
        model["regions"].append({"vertices": [model], "transitions": []})
        with self.assertRaisesRegex(ModelError, "invalid-hierarchy.*Circular"):
            build_model(model)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = MockConverterAdapter()
        self.linear = read_json(MOCK_FILE)["linear"]

    def test_requires_confirmed_completion_in_a_linear_mock(self):
        for terminal in (
            {"token": "◉"},
            {"token": "0", "resolvedKind": "final"},
            {"token": "C", "resolvedKind": "final"},
            {"token": "©", "resolvedKind": "final"},
        ):
            with self.subTest(terminal=terminal):
                self.linear["terminal"] = terminal
                with self.assertRaises(ModelError) as captured:
                    transform_model(self.linear, self.adapter)
                error = captured.exception.diagnostics[0]
                self.assertEqual((error.code, error.path), ("unresolved-semantic", "/terminal/token"))
                self.assertIn(terminal["token"], error.message)
                self.assertIn(self.linear["sourceText"], error.message)

    def test_surfaces_interaction_fields_that_the_current_schema_cannot_carry(self):
        self.linear["steps"][0]["interaction"]["caller"] = "Console"
        with self.assertRaisesRegex(ModelError, "unsupported-field at /steps/0/interaction/caller"):
            transform_model(self.linear, self.adapter)

    def test_accepts_an_independent_adapter_for_explicit_nested_structure(self):
        source = object()
        fixture = read_json("examples/nested-orthogonal.smd.json")

        class FixtureAdapter:
            def adapt(_, supplied):
                self.assertIs(supplied, source)
                return fixture

        self.assertEqual(transform_model(source, FixtureAdapter()), fixture)


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "src.model", *args], cwd=ROOT, capture_output=True, check=False,
        )

    def test_regenerates_the_committed_utf8_models(self):
        for case in ("linear", "resolvedBranch"):
            with self.subTest(case=case):
                result = self.run_cli("transform", str(MOCK_FILE), "--case", case)
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
                held = (ROOT / f"src/model/generated/{case}.smd.json").read_text(encoding="utf-8")
                self.assertEqual(result.stdout.decode("utf-8"), held)
                validate_model(json.loads(result.stdout))

    def test_rejects_duplicate_json_properties_before_writing_an_output_file(self):
        with tempfile.TemporaryDirectory() as workdir:
            source = Path(workdir) / "input.json"
            output = Path(workdir) / "output.json"
            source.write_text('{"kind":"linear","kind":"resolvedBranch"}', encoding="utf-8")
            result = self.run_cli("transform", str(source), "--output", str(output))
            self.assertEqual(result.returncode, 2)
            self.assertIn("Duplicate JSON property 'kind'", result.stderr.decode("utf-8"))
            self.assertFalse(output.exists())
