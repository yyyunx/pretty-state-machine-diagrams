from copy import deepcopy
import json
from unittest import TestCase

from pretty_smd.benchmark import resource
from pretty_smd.bridge import execute_json, request_action
from pretty_smd.pipeline import generate
from src.layout.editor import collapse_projection, edit_layout, validate_scene
from src.layout.engine import LayoutError, LayoutOptions
from src.layout.hybrid import analyze_graph
from src.layout.quality import model_index


def generate_case(name, **options):
    examples = json.loads(resource("mock-converter-p1.json"))
    examples.update(json.loads(resource("mock-converter-p2.json")))
    return generate(examples[name], **options)


class EditorTests(TestCase):
    def test_converter_is_injected_by_the_host_and_still_uses_model_validation(self):
        expected = generate_case("linear")
        payload = {"source":"external fixture","format":"pa","adapter":"untrusted"}

        class Converter:
            def adapt(self, source):
                if source!="external fixture":
                    raise ValueError("Unexpected converter input.")
                return expected.model

        self.assertEqual(json.loads(execute_json("generate",json.dumps(payload)))["status"],422)
        response = json.loads(execute_json("generate",json.dumps(payload),adapter=Converter()))
        self.assertEqual(response["status"],200)
        self.assertEqual(response["body"]["model"],expected.model)

    def test_move_is_transactional_and_routes_using_same_model(self):
        result = generate_case("linear")
        before = deepcopy(result.layout)
        state = next(identifier for identifier, vertex in model_index(result.model)[0].items() if vertex["kind"]=="state")
        bounds = before["nodes"][state]["bounds"]
        point = {"x": bounds["x"], "y": bounds["y"] + 10}
        edited = edit_layout(result.model,before,{state:point})
        self.assertEqual(before,result.layout)
        self.assertTrue(edited.quality["semantic_preservation"])
        self.assertGreater(edited.edit["rerouted"],0)
        for key in before["nodes"].keys()-{state}:
            self.assertEqual(before["nodes"][key],edited.layout["nodes"][key])
        validate_scene(result.model,edited.layout)
        with self.assertRaisesRegex(LayoutError,"locked"):
            edit_layout(result.model,before,{state:point},locked={state:{"x":bounds["x"],"y":bounds["y"]}})
        with self.assertRaisesRegex(LayoutError,"Region"):
            edit_layout(result.model,before,{state:{"x":-999,"y":-999}})

    def test_composite_can_move_with_children_but_not_with_locked_descendant(self):
        result = generate_case("nested")
        vertices, ancestors, _, _ = model_index(result.model)
        owner = next(key for key,v in vertices.items() if v["kind"]=="composite")
        child = next(key for key,path in ancestors.items() if owner in path)
        parent_bounds = result.layout["nodes"][owner]["bounds"]
        child_bounds = result.layout["nodes"][child]["bounds"]
        target = {"x":parent_bounds["x"]+5,"y":parent_bounds["y"]}
        edited = edit_layout(result.model,result.layout,{owner:target})
        self.assertEqual(edited.layout["nodes"][child]["bounds"]["x"],child_bounds["x"]+5)
        inner_state = next(key for key,path in ancestors.items() if owner in path and vertices[key]["kind"]=="state")
        anchor = result.layout["nodes"][inner_state]["bounds"]
        pinned = edit_layout(result.model,result.layout,{owner:target,
            inner_state:{"x":anchor["x"],"y":anchor["y"]}})
        self.assertEqual(pinned.layout["nodes"][inner_state]["bounds"],anchor)
        with self.assertRaisesRegex(LayoutError,"locked"):
            edit_layout(result.model,result.layout,{owner:target},locked={child:{"x":child_bounds["x"],"y":child_bounds["y"]}})

    def test_unrelated_route_is_recomputed_when_a_moved_state_blocks_it(self):
        model = {"schemaVersion":"0.1.0-draft","id":"test","regions":[{"id":"root",
            "vertices":[{"id":key,"kind":"state"} for key in ("a","b","c","d")],
            "transitions":[{"id":"ac","sourceId":"a","targetId":"c"},
                           {"id":"bd","sourceId":"b","targetId":"d"}]}]}
        options = LayoutOptions(layer_spacing=240,node_spacing=120)
        result = generate(model,options=options)
        path = result.layout["edges"]["ac"]["points"]
        x = (path[0]["x"]+path[-1]["x"])/2 - 50
        y = path[0]["y"]-20
        edited = edit_layout(model,result.layout,{"b":{"x":x,"y":y}},options=options)
        self.assertEqual(edited.edit["affected"],2)
        self.assertNotEqual(edited.layout["edges"]["ac"],result.layout["edges"]["ac"])
        self.assertEqual(edited.quality["edge_node_intersections"],0)

    def test_collapse_and_workspace_roundtrip_preserve_source(self):
        result = generate_case("orthogonal")
        before = deepcopy(result.model)
        state = next(key for key,v in model_index(before)[0].items() if v["kind"]=="composite")
        view,geometry,summary = collapse_projection(result.model,result.layout,[state])
        self.assertEqual(result.model,before)
        self.assertEqual(len(model_index(before)[0])-len(geometry["nodes"]),summary[state]["vertices"])
        hidden_edges = len(model_index(before)[3])-len(model_index(view)[3])
        self.assertEqual(hidden_edges,summary[state]["internal_transitions"])
        document = {"version":1,"mode":"balanced","algorithm":"topology","options":{},"model":before,
                    "flags":{"allowRotate":False,"compare":False,"useElk":False},
                    "layout":result.layout,"locked":{},"collapsed":[state]}
        response = request_action("workspace",{"source":json.dumps(document)})
        self.assertEqual(response["workspace"],document)
        self.assertEqual(response["model"],before)
        self.assertEqual(response["projection"]["model"],view)
        document["layout"]["viewport"]["extra"] = "<script>"
        error = json.loads(execute_json("workspace",json.dumps({"source":json.dumps(document)})))
        self.assertEqual(error["status"],422)
        self.assertIn("viewport",error["body"]["diagnostics"][0]["message"])

    def test_hybrid_explains_hierarchy_and_keeps_geometry_valid(self):
        result = generate_case("orthogonal",algorithm="hybrid")
        features = analyze_graph(result.model)
        self.assertGreater(features["hierarchy_depth"],0)
        self.assertGreaterEqual(features["orthogonal_regions"],2)
        self.assertGreater(features["cross_level"],0)
        self.assertEqual(result.quality["optimization"]["features"],features)
        self.assertEqual(result.quality["disconnected_anchors"],0)
        self.assertEqual(result.quality["edge_node_intersections"],0)
