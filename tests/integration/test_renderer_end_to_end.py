import json
import tempfile
import unittest
from pathlib import Path

from src.renderer import render, render_files

ROOT = Path(__file__).resolve().parents[2]


class RendererEndToEndTests(unittest.TestCase):
    def test_nested_model_and_layout_produce_complete_svg_file(self):
        model = json.loads((ROOT / "examples/nested-orthogonal.smd.json").read_text(encoding="utf-8"))
        layout = json.loads((ROOT / "examples/nested-orthogonal.layout.json").read_text(encoding="utf-8"))
        svg = render(model, layout)
        self.assertTrue(svg.startswith('<?xml version="1.0"'))
        self.assertTrue(svg.endswith("</svg>"))
        self.assertIn("Operating", svg)
        self.assertIn("Monitoring", svg)
        self.assertIn("Calibration", svg)
        self.assertIn("flush()", svg)
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "model.json"
            layout_path = Path(directory) / "layout.json"
            output_path = Path(directory) / "diagram.svg"
            model_path.write_text(json.dumps(model), encoding="utf-8")
            layout_path.write_text(json.dumps(layout), encoding="utf-8")
            self.assertEqual(render_files(model_path, layout_path, output_path), output_path)
            self.assertEqual(output_path.read_text(encoding="utf-8"), svg)


if __name__ == "__main__":
    unittest.main()
