"""Normative UML errors and non-blocking projection diagnostics."""

import unittest

from src.model import ModelError, build_model, validate_model

from tests.model.test_recursive_transformation import fixture, transform


def vertex(vertex_id, kind="state", pseudo=None):
    result = {"kind": kind, "id": vertex_id}
    if pseudo is not None:
        result["pseudostateKind"] = pseudo
    return result


def edge(start, end, **interaction):
    return {"sourceId": start, "targetId": end, **interaction}


def model_with(vertices, transitions):
    return build_model({"regions": [{"vertices": vertices, "transitions": transitions}]})


class UmlValidationTests(unittest.TestCase):
    def test_rejects_multiple_initials_initial_guards_and_final_exit(self):
        model = model_with(
            [
                vertex("start", "pseudostate", "initial"), vertex("another", "pseudostate", "initial"),
                vertex("state"), vertex("end", "final"),
            ],
            [edge("start", "state", guard="ok", triggers=["go"]), edge("start", "end"), edge("end", "state")],
        )
        with self.assertRaises(ModelError) as captured:
            validate_model(model, uml=True)
        self.assertEqual({issue.code for issue in captured.exception.diagnostics if issue.severity == "error"}, {
            "uml-duplicate-region-pseudostate", "uml-pseudostate-outgoing", "uml-segment-guard",
            "uml-final-outgoing",
        })
        self.assertEqual(
            [issue.code for issue in captured.exception.diagnostics if issue.severity == "warning"],
            ["uml-initial-trigger-context"],
        )

    def test_initial_label_context_is_nonblocking_at_root_but_nested_trigger_is_invalid(self):
        nodes = [vertex("start", "pseudostate", "initial"), vertex("active")]
        transitions = [edge("start", "active", triggers=["create"])]
        notes = validate_model(model_with(nodes, transitions), uml=True)
        self.assertEqual([(note.code, note.severity) for note in notes], [
            ("uml-initial-trigger-context", "warning"),
        ])
        nested = model_with([{"id": "parent", "kind": "composite", "regions": [{
            "vertices": nodes, "transitions": transitions,
        }]}], [])
        with self.assertRaisesRegex(ModelError, "uml-pseudostate-trigger"):
            validate_model(nested, uml=True)

    def test_accepts_an_effect_on_an_initial_segment(self):
        model = model_with(
            [vertex("start", "pseudostate", "initial"), vertex("state")],
            [edge("start", "state", effect="initialize()")],
        )
        self.assertEqual(validate_model(model, uml=True), ())

    def test_rejects_invalid_fork_join_segments_and_same_region_branches(self):
        model = transform(fixture("orthogonal"))
        root = model["regions"][0]
        fork = next(node["id"] for node in root["vertices"] if node.get("pseudostateKind") == "fork")
        join = next(node["id"] for node in root["vertices"] if node.get("pseudostateKind") == "join")
        forks = [item for item in root["transitions"] if item["sourceId"] == fork]
        joins = [item for item in root["transitions"] if item["targetId"] == join]
        forks[1]["targetId"] = forks[0]["targetId"]
        forks[0]["guard"] = "invalid"
        joins[1]["sourceId"] = joins[0]["sourceId"]
        joins[0]["triggers"] = ["invalid"]
        with self.assertRaises(ModelError) as captured:
            validate_model(model, uml=True)
        codes = {issue.code for issue in captured.exception.diagnostics if issue.severity == "error"}
        self.assertEqual(codes, {
            "uml-segment-guard", "uml-join-trigger", "uml-fork-orthogonal-regions", "uml-join-orthogonal-regions",
        })

    def test_reports_partial_fork_and_join_as_warnings(self):
        model = model_with([vertex("start", "pseudostate", "fork"), vertex("end", "pseudostate", "join")], [])
        issues = validate_model(model, uml=True)
        self.assertEqual({(issue.code, issue.severity) for issue in issues}, {
            ("uml-fork-incomplete", "warning"), ("uml-join-incomplete", "warning"),
        })

    def test_history_allows_one_of_each_kind_but_at_most_one_default_transition(self):
        vertices = [
            vertex("deep", "pseudostate", "deepHistory"), vertex("shallow", "pseudostate", "shallowHistory"),
            vertex("active"),
        ]
        self.assertEqual(validate_model(model_with(vertices, [edge("deep", "active")]), uml=True), ())
        model = model_with(
            [*vertices, vertex("duplicate", "pseudostate", "deepHistory")],
            [edge("deep", "active"), edge("deep", "shallow")],
        )
        with self.assertRaises(ModelError) as captured:
            validate_model(model, uml=True)
        self.assertEqual({issue.code for issue in captured.exception.diagnostics}, {
            "uml-duplicate-region-pseudostate", "uml-pseudostate-outgoing",
        })

    def test_owner_recommendation_does_not_reject_or_reassign_a_cross_level_edge(self):
        model = transform(fixture("orthogonal"))
        root = model["regions"][0]
        operating = next(node for node in root["vertices"] if node["kind"] == "composite")
        region = operating["regions"][0]
        incoming = next(item for item in root["transitions"] if item["targetId"] == region["vertices"][0]["id"])
        root["transitions"].remove(incoming)
        region["transitions"].append(incoming)
        issues = validate_model(model, uml=True)
        self.assertEqual(len(issues), 1)
        self.assertEqual((issues[0].code, issues[0].severity), ("uml-region-owner", "warning"))
        self.assertIs(region["transitions"][-1], incoming)
