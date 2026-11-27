"""SMD draft fixture checks independent of the converter contract."""

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def read_json(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


class SemanticFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = Draft202012Validator(read_json("schemas/smd-model.schema.json"))
        cls.branching_model = read_json("tests/model/cases/guarded-branch.smd.json")

    def test_guarded_branch_keeps_each_interaction_on_its_own_edge(self):
        self.validator.validate(self.branching_model)
        region = self.branching_model["regions"][0]
        branches = [edge for edge in region["transitions"] if edge["sourceId"] == "review"]
        self.assertEqual(
            branches,
            [
                {
                    "id": "approve",
                    "sourceId": "review",
                    "targetId": "pass",
                    "triggers": ["submit(score)"],
                    "guard": "score >= 60",
                    "effect": 'emit("通過")',
                    "sourceText": 'submit(score) [score >= 60] / emit("通過")',
                    "sourceInteractionId": "approveInteraction",
                },
                {
                    "id": "decline",
                    "sourceId": "review",
                    "targetId": "fail",
                    "triggers": ["submit(score)"],
                    "guard": "score < 60",
                    "effect": 'emit("退回")',
                    "sourceText": 'submit(score) [score < 60] / emit("退回")',
                    "sourceInteractionId": "declineInteraction",
                },
            ],
        )
        source = next(vertex for vertex in region["vertices"] if vertex["id"] == "review")
        self.assertEqual(source["kind"], "state")
        self.assertNotIn("displayName", source)

    def test_draft_represents_same_display_name_in_distinct_regions(self):
        model = read_json("examples/nested-orthogonal.smd.json")
        operating = model["regions"][0]["vertices"][1]
        control_region, monitor_region = operating["regions"]
        control = control_region["vertices"][1]
        move = control["regions"][0]["vertices"][1]
        sample = monitor_region["vertices"][1]
        sample["displayName"] = move["displayName"]
        self.validator.validate(model)
        self.assertNotEqual(sample["id"], move["id"])

    def test_nested_orthogonal_regions_keep_behavior_at_its_declaring_state(self):
        model = read_json("examples/nested-orthogonal.smd.json")
        operating = model["regions"][0]["vertices"][1]
        control_region, monitor_region = operating["regions"]
        control = control_region["vertices"][1]
        motion_region, calibration_region = control["regions"]
        move = motion_region["vertices"][1]
        self.assertEqual(
            operating["behaviors"],
            {"entry": ["prepare()"], "exit": ["release()"], "invariant": "active == true"},
        )
        self.assertEqual(move["behaviors"], {"do": ["step()"], "defer": ["pause", "inspect"]})
        self.assertNotIn("behaviors", control)
        self.assertNotIn("displayName", control_region)
        self.assertNotIn("displayName", motion_region)
        self.assertEqual(monitor_region["displayName"], "Monitoring")
        self.assertEqual(calibration_region["displayName"], "Calibration")

    def test_all_explicit_pseudostate_kinds_have_a_draft_representation(self):
        # A shape check only. The witness vertices have no incident transitions.
        kinds = (
            "initial", "choice", "junction", "fork", "join", "shallowHistory",
            "deepHistory", "entryPoint", "exitPoint", "terminate",
        )
        for kind in kinds:
            with self.subTest(pseudostateKind=kind):
                model = {
                    "schemaVersion": self.branching_model["schemaVersion"],
                    "id": "shape-witness",
                    "regions": [
                        {
                            "id": "region",
                            "vertices": [
                                {"id": "vertex", "kind": "pseudostate", "pseudostateKind": kind}
                            ],
                            "transitions": [],
                        }
                    ],
                }
                self.validator.validate(model)

    def test_final_vertex_cannot_have_a_terminate_pseudostate_kind(self):
        model = read_json("examples/basic.smd.json")
        final = model["regions"][0]["vertices"][-1]
        self.assertEqual(final["kind"], "final")
        final["pseudostateKind"] = "terminate"
        with self.assertRaises(ValidationError):
            self.validator.validate(model)
