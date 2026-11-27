"""Exercise the draft JSON boundary using committed fixtures."""

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ("basic", "nested-orthogonal")


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def validate_pair(model, layout):
    """Check references and ID correspondence after shape validation."""
    ids = {model["id"]}
    regions = set()
    nodes = set()
    transitions = {}

    def register(element_id):
        if element_id in ids:
            raise ValueError(f"Duplicate internal ID {element_id}")
        ids.add(element_id)

    def visit(region):
        register(region["id"])
        regions.add(region["id"])
        for vertex in region["vertices"]:
            register(vertex["id"])
            nodes.add(vertex["id"])
            for child in vertex.get("regions", []):
                visit(child)
        for transition in region["transitions"]:
            register(transition["id"])
            transitions[transition["id"]] = transition

    for region in model["regions"]:
        visit(region)

    for transition in transitions.values():
        for field in ("sourceId", "targetId"):
            if transition[field] not in nodes:
                raise ValueError(f"Unknown endpoint {transition[field]} on {transition['id']}")
    if layout["modelId"] != model["id"]:
        raise ValueError("Layout belongs to a different model")
    for field, expected in (("nodes", nodes), ("regions", regions), ("edges", set(transitions))):
        recorded = set(layout[field])
        if recorded != expected:
            raise ValueError(f"{field} mismatch: missing={expected - recorded}, extra={recorded - expected}")


class DraftContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model_schema = read_json("schemas/smd-model.schema.json")
        cls.layout_schema = read_json("schemas/layout.schema.json")
        cls.model_validator = Draft202012Validator(cls.model_schema)
        cls.layout_validator = Draft202012Validator(cls.layout_schema)

    def test_schemas_are_valid_draft_2020_12(self):
        for schema in (self.model_schema, self.layout_schema):
            Draft202012Validator.check_schema(schema)

    def test_mock_pairs_follow_the_contract(self):
        for name in EXAMPLES:
            with self.subTest(name=name):
                model = read_json(f"examples/{name}.smd.json")
                layout = read_json(f"examples/{name}.layout.json")
                self.model_validator.validate(model)
                self.layout_validator.validate(layout)
                validate_pair(model, layout)

    def test_fixture_retains_transition_fields(self):
        model = read_json("examples/basic.smd.json")
        start, run, finish = model["regions"][0]["transitions"]
        self.assertNotIn("triggers", start)
        self.assertEqual(run["triggers"], ["start(jobId)"])
        self.assertEqual(run["guard"], "ready && count < limit")
        self.assertEqual(run["effect"], 'log("started"); count += 1')
        self.assertEqual(run["sourceInteractionId"], "i1")
        self.assertEqual(run["sourceText"], 'start(jobId) [ready && count < limit] / log("started"); count += 1')
        self.assertEqual(finish["triggers"], ["done"])

    def test_fixture_preserves_nested_regions_and_unnamed_elements(self):
        model = read_json("examples/nested-orthogonal.smd.json")
        layout = read_json("examples/nested-orthogonal.layout.json")
        operating = model["regions"][0]["vertices"][1]
        control_region, monitor_region = operating["regions"]
        control = control_region["vertices"][1]
        motion_region, calibration_region = control["regions"]
        self.assertEqual(operating["displayName"], "Operating")
        for unnamed in (control, control_region, motion_region, monitor_region["vertices"][1]):
            self.assertNotIn("displayName", unnamed)
        self.assertNotIn("labelBounds", layout["nodes"][control["id"]])
        for region, name in ((monitor_region, "Monitoring"), (calibration_region, "Calibration")):
            self.assertEqual(region["displayName"], name)
            placement = layout["regions"][region["id"]]
            label = placement["labelBounds"]
            left_segment, right_segment = placement["separatorSegments"]
            self.assertLess(left_segment[1]["x"], label["x"])
            self.assertGreater(right_segment[0]["x"], label["x"] + label["width"])

    def test_rejects_blank_display_name(self):
        model = read_json("examples/basic.smd.json")
        model["regions"][0]["vertices"][1]["displayName"] = " "
        with self.assertRaises(ValidationError):
            self.model_validator.validate(model)

    def test_rejects_pseudostate_without_subtype(self):
        model = read_json("examples/basic.smd.json")
        del model["regions"][0]["vertices"][0]["pseudostateKind"]
        with self.assertRaises(ValidationError):
            self.model_validator.validate(model)

    def test_rejects_composite_without_regions(self):
        model = read_json("examples/nested-orthogonal.smd.json")
        del model["regions"][0]["vertices"][1]["regions"]
        with self.assertRaises(ValidationError):
            self.model_validator.validate(model)

    def test_rejects_edge_with_only_one_point(self):
        layout = read_json("examples/basic.layout.json")
        layout["edges"]["run"]["points"].pop()
        with self.assertRaises(ValidationError):
            self.layout_validator.validate(layout)

    def test_detects_repeat_id_in_a_nested_region(self):
        model = read_json("examples/nested-orthogonal.smd.json")
        layout = read_json("examples/nested-orthogonal.layout.json")
        outer = model["regions"][0]["vertices"][1]
        outer["regions"][1]["vertices"][1]["id"] = "start"
        with self.assertRaisesRegex(ValueError, "Duplicate internal ID start"):
            validate_pair(model, layout)

    def test_detects_dangling_transition(self):
        model = read_json("examples/basic.smd.json")
        layout = read_json("examples/basic.layout.json")
        model["regions"][0]["transitions"][0]["targetId"] = "root"
        with self.assertRaisesRegex(ValueError, "Unknown endpoint root"):
            validate_pair(model, layout)

    def test_detects_mismatched_model_and_layout(self):
        model = read_json("examples/basic.smd.json")
        layout = read_json("examples/nested-orthogonal.layout.json")
        with self.assertRaisesRegex(ValueError, "different model"):
            validate_pair(model, layout)

    def test_detects_missing_and_extra_layout_entries(self):
        model = read_json("examples/basic.smd.json")
        layout = read_json("examples/basic.layout.json")
        layout["edges"]["extra"] = layout["edges"].pop("run")
        with self.assertRaisesRegex(ValueError, "edges mismatch.*run.*extra"):
            validate_pair(model, layout)
