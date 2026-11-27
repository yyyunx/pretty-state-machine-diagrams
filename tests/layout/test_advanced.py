"""Regression cases and generated invariants for the experimental engine."""

from copy import deepcopy
from pathlib import Path
from random import Random
import json
import unittest
from xml.etree import ElementTree as XML

from pretty_smd import BudgetExceeded, generate, optimize
from pretty_smd.benchmark import cases
from pretty_smd.stress import generated_case
from src.layout.engine import LayoutOptions, layout
from src.layout.quality import evaluate
from src.model import ModelError, build_model

ROOT = Path(__file__).resolve().parents[2]
XML_NS = {"s":"http://www.w3.org/2000/svg"}


class AdvancedTests(unittest.TestCase):
    def test_phase3_reference_remains_identical(self):
        for name,model in cases():
            with self.subTest(name=name):
                saved = json.loads((ROOT/"benchmarks/after"/f"{name}.layout.json").read_bytes())
                self.assertEqual(layout(model),saved)

    def test_seeded_models_preserve_geometry_names_and_behavior(self):
        rng = Random(9107)
        for example in range(6):
            with self.subTest(example=example):
                vertices = [{"kind":"state","id":f"private-{i}",
                             **({"displayName":"初始 ＆ 測試 é <ok>"} if i==0 else {})} for i in range(8)]
                rng.shuffle(vertices)
                transitions = [{"sourceId":f"private-{i}","targetId":f"private-{i+1}",
                               "triggers":["arrive"]} for i in range(7)]
                loop = rng.randrange(8)
                transitions.append({"sourceId":f"private-{loop}","targetId":f"private-{loop}",
                                    "effect":'record("<img>")'})
                model = build_model({"regions":[{"vertices":vertices,"transitions":transitions}]})
                original = deepcopy(model)
                options = LayoutOptions(direction="horizontal" if example%2 else "vertical")
                result = generate(model,algorithm="advanced",mode="fast",options=options)
                self.assertEqual(model,original)
                self.assertEqual(result.layout,optimize(model,options,mode="fast").layout)
                self.assertTrue(result.quality["semantic_preservation"])
                for key in ("node_overlaps","disconnected_anchors","broken_paths","edge_node_intersections"):
                    self.assertEqual(result.quality[key],0)
                document = XML.fromstring(result.svg)
                self.assertEqual(len(document.findall(".//s:polyline",XML_NS)),len(transitions))
                labels = " ".join(item.text or "" for item in document.findall(".//s:tspan",XML_NS))
                self.assertIn("測試 é <ok>",labels)
                self.assertNotIn("private-",labels)
                self.assertNotIn("<img>",result.svg)
                json.dumps(result.layout,allow_nan=False)

    def test_pseudostate_benchmark_reduces_crossings_and_coincident_runs(self):
        model = dict(cases())["pseudostates"]
        before = evaluate(model,layout(model))
        after = optimize(model,mode="balanced")
        self.assertLess(after.metrics["edge_crossings"],before["edge_crossings"])
        self.assertLess(after.metrics["edge_overlap_length"],before["edge_overlap_length"])
        self.assertEqual(after.metrics["disconnected_anchors"],0)

    def test_self_loop_uses_two_distinct_ports(self):
        model = dict(cases())["self-loop"]
        before = evaluate(model,layout(model))
        result = optimize(model,mode="fast")
        self.assertLess(result.metrics["edge_bends"],before["edge_bends"])
        for edge in model["regions"][0]["transitions"]:
            if edge["sourceId"]==edge["targetId"]:
                points = result.layout["edges"][edge["id"]]["points"]
                self.assertNotEqual(points[0],points[-1])

    def test_deadline_and_bad_semantics_fail_explicitly(self):
        model = generated_case("loops",25)
        with self.assertRaisesRegex(BudgetExceeded,"time limit"):
            optimize(model,timeout=1e-9)
        broken = deepcopy(model)
        broken["regions"][0]["transitions"][0]["sourceId"]="missing"
        with self.assertRaises(ModelError):
            optimize(broken)
        duplicate = deepcopy(model)
        duplicate["regions"][0]["vertices"][1]["id"]=duplicate["regions"][0]["vertices"][0]["id"]
        with self.assertRaises(ModelError):
            optimize(duplicate)
        with self.assertRaises(ModelError):
            optimize({"id":"empty","schemaVersion":model["schemaVersion"],"regions":[]})
        empty = build_model({"regions":[{"vertices":[],"transitions":[]}]})
        self.assertTrue(optimize(empty,mode="fast").metrics["semantic_preservation"])

    def test_long_text_and_nested_input_are_bounded(self):
        text = "節點 🔒 Alpha é " * 420
        model = build_model({"regions":[{"vertices":[{"kind":"state","displayName":text}],"transitions":[]}]})
        self.assertGreater(generate(model,algorithm="advanced",mode="fast").layout["viewport"]["height"],100)
        from pretty_smd import InputError, load_json
        with self.assertRaises(InputError):
            load_json("["*65+"null"+"]"*65)
