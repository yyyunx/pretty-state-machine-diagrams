import copy
import json
import unittest
from pathlib import Path
from jsonschema import Draft202012Validator
from src.layout.engine import layout

ROOT=Path(__file__).resolve().parents[2]

class LayoutTests(unittest.TestCase):
    def test_fixtures(self):
        schema=json.loads((ROOT/"schemas/layout.schema.json").read_text())
        for name in ("basic","nested-orthogonal"):
            with self.subTest(name=name):
                model=json.loads((ROOT/f"examples/{name}.smd.json").read_text())
                original=copy.deepcopy(model)
                result=layout(model)
                Draft202012Validator(schema).validate(result)
                self.assertEqual(model,original)
                self.assertEqual(result,layout(model))
                def visit(r):
                    self.assertIn(r["id"],result["regions"])
                    for v in r["vertices"]:
                        self.assertIn(v["id"],result["nodes"])
                        if "displayName" not in v:
                            self.assertNotIn("labelBounds",result["nodes"][v["id"]])
                        for child in v.get("regions",[]):
                            visit(child)
                    for t in r["transitions"]:
                        pts=result["edges"][t["id"]]["points"]
                        self.assertGreaterEqual(len(pts),2)
                        for a,b in zip(pts,pts[1:]):
                            self.assertTrue(a["x"]==b["x"] or a["y"]==b["y"])
                for r in model["regions"]: visit(r)
