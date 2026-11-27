import json
from pathlib import Path
import unittest
from xml.etree import ElementTree

from src.layout.engine import LayoutOptions, layout
from src.layout.quality import evaluate
from src.model import MockConverterAdapter, build_model, transform_model
from src.renderer import render

ROOT = Path(__file__).resolve().parents[2]
SVG = "{http://www.w3.org/2000/svg}"


def fixture(case):
    path = ROOT / "tests/model/cases/mock-converter-p2.json"
    return transform_model(json.loads(path.read_text(encoding="utf-8"))[case], MockConverterAdapter())


class TopologyTests(unittest.TestCase):
    def test_chain_uses_transition_topology_in_both_directions(self):
        draft = {"regions": [{"vertices": [{"id": x, "kind": "state"} for x in ("c", "a", "b")],
                              "transitions": [{"sourceId": a, "targetId": b} for a, b in (("a","b"),("b","c"))]}]}
        model = build_model(draft)
        for direction, coordinate in (("horizontal", "x"), ("vertical", "y")):
            result = layout(model, LayoutOptions(direction=direction))
            self.assertEqual(list(sorted(("a","b","c"), key=lambda x: result["nodes"][x]["bounds"][coordinate])),
                             ["a", "b", "c"])
        self.assertEqual([node["id"] for node in model["regions"][0]["vertices"]], ["c","a","b"])

    def test_cross_hierarchy_edges_and_bars_reach_drawn_outlines(self):
        for case in ("orthogonal", "pseudostates"):
            for direction in ("horizontal", "vertical"):
                with self.subTest(case=case, direction=direction):
                    model = fixture(case)
                    result = layout(model, LayoutOptions(direction=direction))
                    self.assertEqual(evaluate(model, result)["disconnected_anchors"], 0)

    def test_layering_and_connection_points(self):
        model = fixture("pseudostates")
        result = layout(model)
        scene = ElementTree.fromstring(render(model, result))
        layers = [item.get("data-layer") for item in scene if item.get("data-layer")]
        self.assertLess(layers.index("containers"), layers.index("edges"))
        self.assertLess(layers.index("edges"), layers.index("symbols"))
        self.assertLess(layers.index("regions"), layers.index("region-labels"))
        glyphs = {item.get("data-kind"): item for item in scene.iter(SVG+"g") if item.get("data-kind")}
        self.assertEqual(glyphs["junction"].find(SVG+"circle").get("fill"), "#20252b")
        self.assertIsNone(glyphs["terminate"].find(SVG+"circle"))
        self.assertEqual(len(glyphs["exitPoint"].findall(SVG+"line")), 2)
        vertices = model["regions"][0]["vertices"]
        owner = next(node for node in vertices if node["kind"] == "composite")
        bounds = result["nodes"][owner["id"]]["bounds"]
        for node in owner["regions"][0]["vertices"]:
            if node.get("pseudostateKind") in ("entryPoint", "exitPoint"):
                placed = result["nodes"][node["id"]]["bounds"]
                expected = bounds["x"] + (bounds["width"] if node["pseudostateKind"] == "exitPoint" else 0)
                self.assertAlmostEqual(placed["x"] + placed["width"]/2, expected)
