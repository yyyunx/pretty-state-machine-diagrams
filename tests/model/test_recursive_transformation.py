"""Exercise recursive behavior input through the same adapter used by the CLI."""

import json
import unittest
from pathlib import Path

from src.model import MockConverterAdapter, ModelError, serialize_model, transform_model, validate_model

ROOT = Path(__file__).resolve().parents[2]


def fixture(case):
    path = ROOT / "tests/model/cases/mock-converter-p2.json"
    return json.loads(path.read_text(encoding="utf-8"))[case]


def transform(body):
    return transform_model(body, MockConverterAdapter())


def wrap(*body):
    return {"kind": "resolvedBehavior", "regions": [{"body": list(body)}]}


class RecursiveTransformationTests(unittest.TestCase):
    def test_nested_branch_and_loop_preserve_hierarchy_and_raw_interactions(self):
        top = transform(fixture("nested"))["regions"][0]
        processing = next(vertex for vertex in top["vertices"] if vertex["kind"] == "composite")
        middle = processing["regions"][0]
        inner = next(vertex for vertex in middle["vertices"] if vertex["kind"] == "composite")
        self.assertNotIn("displayName", middle)
        self.assertNotIn("displayName", inner)
        self.assertEqual(processing["behaviors"], {
            "entry": ["openJob()"], "exit": ["archive()"], "invariant": "job != null",
        })
        review = inner["regions"][0]
        self.assertEqual(review["displayName"], "Review")
        vertices = {vertex["id"]: vertex for vertex in review["vertices"]}
        edges = review["transitions"]
        approve = next(edge for edge in edges if edge.get("sourceInteractionId") == "approve")
        self.assertEqual(approve["triggers"], ["submit(score)"])
        self.assertEqual(approve["guard"], "score >= 60")
        self.assertEqual(approve["effect"], 'mark("通過")')
        self.assertEqual(approve["sourceText"], 'submit(score) [score >= 60] / mark("通過")')
        self.assertEqual(vertices[approve["sourceId"]]["behaviors"], {"do": ["check()"], "defer": ["cancel"]})
        retry = next(edge for edge in edges if edge.get("triggers") == ["retry"])
        self.assertEqual(retry["targetId"], approve["targetId"])
        self.assertNotIn("displayName", vertices[retry["sourceId"]])
        exits = [edge for edge in edges if edge.get("triggers") in (["close"], ["confirm"])]
        self.assertEqual(len(exits), 2)
        self.assertEqual(len({edge["targetId"] for edge in exits}), 1)

    def test_resolves_forward_reference_and_preserves_cross_level_link_ownership(self):
        model = transform(fixture("orthogonal"))
        root = model["regions"][0]
        composite = next(vertex for vertex in root["vertices"] if vertex["kind"] == "composite")
        left, right = composite["regions"]
        self.assertNotIn("displayName", left)
        self.assertEqual(right["displayName"], "Monitoring")
        fork = next(vertex for vertex in root["vertices"] if vertex.get("pseudostateKind") == "fork")
        edges = root["transitions"]
        self.assertEqual(
            {edge["targetId"] for edge in edges if edge["sourceId"] == fork["id"]},
            {left["vertices"][0]["id"], right["vertices"][0]["id"]},
        )
        finish = next(edge for edge in edges if edge.get("triggers") == ["finish"])
        finals = [vertex for vertex in root["vertices"] if vertex["kind"] == "final"]
        self.assertEqual([vertex["id"] for vertex in finals], [finish["targetId"]])
        self.assertEqual(validate_model(model, uml=True), ())

    def test_generated_snapshots_are_reproducible_and_cover_all_pseudostates(self):
        def kinds(regions):
            for region in regions:
                for vertex in region["vertices"]:
                    if vertex["kind"] == "pseudostate":
                        yield vertex["pseudostateKind"]
                    yield from kinds(vertex.get("regions", []))

        observed = set()
        for case in ("nested", "orthogonal", "pseudostates"):
            with self.subTest(case=case):
                model = transform(fixture(case))
                snapshot = ROOT / f"src/model/generated/{case}.smd.json"
                self.assertEqual(serialize_model(model), snapshot.read_text(encoding="utf-8"))
                self.assertEqual(validate_model(model, uml=True), ())
                observed.update(kinds(model["regions"]))
        self.assertEqual(observed, {
            "initial", "choice", "junction", "fork", "join", "shallowHistory",
            "deepHistory", "entryPoint", "exitPoint", "terminate",
        })

    def test_unresolved_operator_retains_nested_pointer_and_source(self):
        source_text = "(A par B) >> C"
        body = {"kind": "composite", "regions": [{
            "body": [{"kind": "unresolved", "operator": "par", "sourceText": source_text}],
        }]}
        with self.assertRaises(ModelError) as captured:
            transform(wrap(body))
        error = captured.exception.diagnostics[0]
        self.assertEqual(error.code, "unresolved-semantic")
        self.assertEqual(error.path, "/regions/0/body/0/regions/0/body/0/operator")
        self.assertEqual(error.source_text, source_text)

    def test_unknown_reference_is_reported_even_without_an_incident_edge(self):
        with self.assertRaises(ModelError) as captured:
            transform(wrap({"kind": "reference", "target": "missing", "sourceText": "ref A"}))
        error = captured.exception.diagnostics[0]
        self.assertEqual((error.code, error.path, error.source_text), (
            "unresolved-reference", "/regions/0/body/0/target", "ref A",
        ))

    def test_duplicate_symbol_is_rejected_across_regions(self):
        model = wrap({"kind": "state", "key": "same"})
        model["regions"].append({"body": [{"kind": "state", "key": "same"}]})
        with self.assertRaisesRegex(ModelError, "duplicate-vertex-key at /regions/1/body/0/key"):
            transform(model)

    def test_sequence_does_not_invent_a_branch_continuation(self):
        branch = {
            "kind": "branch", "source": {"kind": "state"},
            "alternatives": [{"body": {"kind": "state"}, "interaction": {}} for _ in range(2)],
        }
        sequence = {"kind": "sequence", "parts": [branch, {"kind": "state"}], "connect": [{}]}
        with self.assertRaisesRegex(ModelError, "ambiguous-continuation at /regions/0/body/0/parts/0"):
            transform(wrap(sequence))
