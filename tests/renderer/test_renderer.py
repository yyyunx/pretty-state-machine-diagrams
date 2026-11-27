import json
import unittest
from pathlib import Path

from src.renderer import RenderError, render, validate_pair

ROOT = Path(__file__).resolve().parents[2]


def fixture(name):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


class RendererTests(unittest.TestCase):
    def test_basic_pair_renders_standalone_svg(self):
        svg = render(fixture("basic.smd.json"), fixture("basic.layout.json"))
        self.assertIn('<svg', svg)
        self.assertIn('marker-end="url(#arrow)"', svg)
        self.assertIn("待機", svg)
        self.assertIn("start(jobId)", svg)
        self.assertIn("ready &amp;&amp; count &lt; limit", svg)
        self.assertNotIn(">idle<", svg)

    def test_nested_regions_keep_explicit_names_only(self):
        svg = render(fixture("nested-orthogonal.smd.json"),
                     fixture("nested-orthogonal.layout.json"))
        self.assertIn("Operating", svg)
        self.assertIn("Monitoring", svg)
        self.assertIn("Calibration", svg)
        self.assertNotIn("control-region", svg)
        self.assertNotIn("motion-region", svg)
        self.assertIn("entry / prepare()", svg)
        self.assertIn("do / step()", svg)
        self.assertIn("defer pause", svg)

    def test_mismatched_model_id_is_rejected(self):
        model, layout = fixture("basic.smd.json"), fixture("basic.layout.json")
        layout["modelId"] = "other"
        with self.assertRaisesRegex(RenderError, "modelId"):
            validate_pair(model, layout)

    def test_missing_layout_node_is_rejected(self):
        model, layout = fixture("basic.smd.json"), fixture("basic.layout.json")
        del layout["nodes"]["idle"]
        with self.assertRaisesRegex(RenderError, "missing idle"):
            render(model, layout)

    def test_dangling_transition_is_rejected(self):
        model, layout = fixture("basic.smd.json"), fixture("basic.layout.json")
        model["regions"][0]["transitions"][0]["targetId"] = "missing"
        with self.assertRaisesRegex(RenderError, "dangling"):
            render(model, layout)


    def test_all_supported_pseudostate_shapes_render(self):
        kinds = [
            "initial", "choice", "junction", "fork", "join",
            "shallowHistory", "deepHistory", "entryPoint", "exitPoint", "terminate",
        ]
        vertices = [
            {"id": kind, "kind": "pseudostate", "pseudostateKind": kind}
            for kind in kinds
        ]
        model = {
            "schemaVersion": "0.1.0-draft",
            "id": "pseudo-machine",
            "regions": [{"id": "root", "vertices": vertices, "transitions": []}],
        }
        nodes = {
            kind: {"bounds": {"x": 12 + i * 32, "y": 20, "width": 24, "height": 24}}
            for i, kind in enumerate(kinds)
        }
        layout = {
            "schemaVersion": "0.1.0-draft",
            "modelId": "pseudo-machine",
            "viewport": {"x": 0, "y": 0, "width": 360, "height": 70},
            "nodes": nodes,
            "regions": {"root": {"bounds": {"x": 4, "y": 4, "width": 350, "height": 60}}},
            "edges": {},
        }
        svg = render(model, layout)
        for marker in ("H", "H*"):
            self.assertIn(marker, svg)
        self.assertIn("<path", svg)
        self.assertIn("<line", svg)

    def test_svg_escapes_untrusted_text(self):
        model, layout = fixture("basic.smd.json"), fixture("basic.layout.json")
        model["regions"][0]["vertices"][1]["displayName"] = "<script>alert(1)</script>"
        svg = render(model, layout)
        self.assertIn("&lt;script&gt;", svg)
        self.assertNotIn("<script>", svg)


if __name__ == "__main__":
    unittest.main()
