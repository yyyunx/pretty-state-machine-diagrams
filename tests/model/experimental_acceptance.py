"""P0/P1 acceptance cases ready to bind to a consented experiment."""

import json
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
INTERACTION_FIELDS = ("triggers", "guard", "effect", "sourceText", "sourceInteractionId")


def read_json(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def acceptance_suite(build, transform):
    """Bind two test wrappers and return the suite for unittest.

    Each wrapper returns (JSON text or None, diagnostics). Diagnostics are
    normalized by the wrappers to (category, JSON pointer) pairs. These are
    conventions for the test suite. The implementation can expose its own API.
    """
    validator = Draft202012Validator(read_json("schemas/smd-model.schema.json"))
    mocks = read_json("tests/model/cases/mock-converter-p1.json")

    class ExperimentTests(unittest.TestCase):
        def assert_model(self, result):
            json_text, diagnostics = result
            self.assertEqual(tuple(diagnostics), ())
            self.assertIsInstance(json_text, str)
            model = json.loads(json_text)
            validator.validate(model)
            return model

        def assert_interaction(self, expected, edge):
            self.assertEqual(
                {field: edge[field] for field in INTERACTION_FIELDS if field in edge},
                expected,
            )

        def test_builds_and_serializes_nested_regions(self):
            expected = read_json("examples/nested-orthogonal.smd.json")
            draft = deepcopy(expected)
            del draft["schemaVersion"]
            self.assertEqual(self.assert_model(build(draft)), expected)

        def test_allocates_repeatable_ids_without_naming_unnamed_vertices(self):
            draft = read_json("examples/basic.smd.json")
            del draft["schemaVersion"]
            region = draft["regions"][0]
            vertices = region["vertices"]
            given_ids = {element["id"] for element in (draft, region, *vertices, *region["transitions"])}
            vertices.extend([{"kind": "state"}, {"kind": "state"}])

            first = build(deepcopy(draft))
            second = build(deepcopy(draft))
            model = self.assert_model(first)
            self.assertEqual(self.assert_model(second), model)
            self.assertEqual(first[0], second[0])
            generated = model["regions"][0]["vertices"][-2:]
            generated_ids = {vertex["id"] for vertex in generated}
            self.assertEqual(len(generated_ids), 2)
            self.assertTrue(generated_ids.isdisjoint(given_ids))
            for vertex in generated:
                self.assertNotIn("displayName", vertex)

        def test_reports_malformed_model_with_a_location(self):
            faults = (
                ("duplicate-id", ("vertices", 1, "id"), "root"),
                ("invalid-endpoint", ("transitions", 0, "targetId"), "does-not-exist"),
                ("invalid-endpoint", ("transitions", 0, "targetId"), "root"),
                ("invalid-hierarchy", ("vertices", 1, "regions"), []),
                ("missing-field", ("transitions", 0, "sourceId"), None),
            )
            for category, (collection, index, field), replacement in faults:
                with self.subTest(category=category, field=field, replacement=replacement):
                    draft = read_json("examples/basic.smd.json")
                    del draft["schemaVersion"]
                    item = draft["regions"][0][collection][index]
                    if field == "regions":
                        item["kind"] = "composite"
                    if replacement is None:
                        del item[field]
                    else:
                        item[field] = replacement
                    json_text, diagnostics = build(draft)
                    self.assertIsNone(json_text)
                    self.assertIn((category, f"/regions/0/{collection}/{index}/{field}"), diagnostics)

        def test_transforms_linear_mock_preserving_order_and_original_text(self):
            model = self.assert_model(transform(deepcopy(mocks["linear"])))
            region = model["regions"][0]
            steps = mocks["linear"]["steps"]
            edges = [edge for edge in region["transitions"] if "sourceInteractionId" in edge]
            for step, edge in zip(steps, edges, strict=True):
                self.assert_interaction(step["interaction"], edge)
            first, second = edges
            vertices = {vertex["id"]: vertex for vertex in region["vertices"]}
            self.assertEqual(first["targetId"], second["sourceId"])
            self.assertEqual(vertices[second["targetId"]]["kind"], "final")
            self.assertNotIn("displayName", vertices[second["sourceId"]])
            for field, expected in steps[0]["sourceState"].items():
                self.assertEqual(vertices[first["sourceId"]][field], expected)

        def test_transforms_resolved_branch_without_inserting_a_choice(self):
            model = self.assert_model(transform(deepcopy(mocks["resolvedBranch"])))
            region = model["regions"][0]
            vertices = {vertex["id"]: vertex for vertex in region["vertices"]}
            edges = [edge for edge in region["transitions"] if "sourceInteractionId" in edge]
            alternatives = mocks["resolvedBranch"]["alternatives"]
            for expected, edge in zip(alternatives, edges, strict=True):
                self.assert_interaction(expected["interaction"], edge)
                target = vertices[edge["targetId"]]
                if "displayName" in expected["targetState"]:
                    self.assertEqual(target["displayName"], expected["targetState"]["displayName"])
                else:
                    self.assertNotIn("displayName", target)
            first, second = edges
            self.assertEqual(first["sourceId"], second["sourceId"])
            self.assertNotEqual(first["targetId"], second["targetId"])
            for field, expected in mocks["resolvedBranch"]["sourceState"].items():
                self.assertEqual(vertices[first["sourceId"]][field], expected)
            self.assertFalse(any(vertex.get("pseudostateKind") == "choice" for vertex in vertices.values()))

        def test_reports_unresolved_semantics_without_returning_a_model(self):
            for case in mocks["unresolvedOperators"]:
                with self.subTest(operator=case["operator"]):
                    json_text, diagnostics = transform(deepcopy(case))
                    self.assertIsNone(json_text)
                    self.assertIn(("unresolved-semantic", "/operator"), diagnostics)

    return unittest.defaultTestLoader.loadTestsFromTestCase(ExperimentTests)
