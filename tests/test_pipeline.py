import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from pretty_smd import InputError, LayoutOptions, generate, load_json
from src.model import ModelError
from src.renderer import RenderError, render

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/basic.smd.json"


class PipelineTests(unittest.TestCase):
    def test_same_model_drives_every_export_and_shapes_are_finite(self):
        model = load_json(FIXTURE.read_bytes())
        result = generate(model, options=LayoutOptions(direction="vertical"))
        self.assertEqual(result.model, model)
        self.assertEqual(result.layout["modelId"], model["id"])
        self.assertTrue(result.quality["semantic_preservation"])
        self.assertEqual(result.quality["disconnected_anchors"], 0)
        self.assertIn("待機", result.svg)
        result.layout["edges"]["begin"]["points"][0]["x"] = float("nan")
        with self.assertRaisesRegex(RenderError, "finite"):
            render(model, result.layout)

    def test_invalid_json_is_rejected_at_input_boundary(self):
        for text in ('{"id":"a","id":"b"}', '{"x":NaN}', '{"x":1e999}', "["*80+"0"+"]"*80):
            with self.subTest(text=text), self.assertRaises(InputError):
                load_json(text)
        with self.assertRaisesRegex(InputError, "1 MiB"):
            load_json(b" " * (1024 * 1024 + 1))
        with self.assertRaisesRegex(InputError, "100 digits"):
            load_json("1" * 101)

    def test_external_adapter_boundary_and_unresolved_source(self):
        class FixtureAdapter:
            def adapt(self, source):
                return load_json(source)
        result = generate(FIXTURE.read_bytes().decode("utf-8"), input_format="pa", adapter=FixtureAdapter())
        self.assertIn("待機", result.svg)
        with self.assertRaisesRegex(InputError, "external Converter"):
            generate("i1 . ◉", input_format="pa")
        with self.assertRaises(ModelError) as error:
            generate({"kind":"unresolved","operator":"seq","sourceText":"i1 seq i2 . ◉"})
        self.assertEqual(error.exception.diagnostics[0].path, "/operator")
        self.assertEqual(error.exception.diagnostics[0].source_text, "i1 seq i2 . ◉")

    def test_cli_exports_work_from_a_separate_destination(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            args = [sys.executable, "-m", "pretty_smd", "generate", str(FIXTURE),
                    "--output", str(output/"graph.svg"), "--layout-output", str(output/"layout.json"),
                    "--smd-output", str(output/"smd.json"), "--quality-output", str(output/"quality.json")]
            result = subprocess.run(args, cwd=ROOT, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
            self.assertIn("待機", (output/"graph.svg").read_text(encoding="utf-8"))
            self.assertTrue(json.loads((output/"quality.json").read_bytes())["semantic_preservation"])
