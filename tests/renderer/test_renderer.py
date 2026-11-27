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

    def test_svg_escapes_untrusted_text(self):
        model, layout = fixture("basic.smd.json"), fixture("basic.layout.json")
        model["regions"][0]["vertices"][1]["displayName"] = "<script>alert(1)</script>"
        svg = render(model, layout)
        self.assertIn("&lt;script&gt;", svg)
        self.assertNotIn("<script>", svg)


if __name__ == "__main__":
    unittest.main()
