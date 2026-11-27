"""Run the three real modules from an isolated integration checkout."""

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree

from jsonschema import Draft202012Validator

from src.layout.engine import layout
from src.model import MockConverterAdapter, serialize_model, transform_model, validate_model
from src.renderer import render
from tests.integration.test_contracts import validate_pair

ROOT = Path(__file__).resolve().parents[2]
SVG = "{http://www.w3.org/2000/svg}"

CASES = (
    ("p1", "linear", ("待機", 'start(jobId) [ready  && hasJob(jobId)] / notify("開始")')),
    ("p1", "resolvedBranch", ("待審查", "通過")),
    ("p2", "nested", ("Processing", "Reviewing", "entry / openJob()", "do / check()")),
    ("p2", "orthogonal", ("Operating", "Monitoring", "Collected", "Monitored")),
    ("p2", "pseudostates", ("Idle", "Session", "H", "H*")),
)


def load_json(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    layout_schema = Draft202012Validator(load_json("schemas/layout.schema.json"))
    fixtures = {version: load_json(f"tests/model/cases/mock-converter-{version}.json") for version in ("p1", "p2")}
    for version, case, expected_text in CASES:
        model = transform_model(fixtures[version][case], MockConverterAdapter())
        for warning in validate_model(model, uml=True):
            print(f"{case}: warning {warning.code} {warning.path}: {warning.message}")
        model_json = serialize_model(model)
        layout_json = json.dumps(layout(json.loads(model_json)), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        positioned = json.loads(layout_json)
        layout_schema.validate(positioned)
        validate_pair(model, positioned)

        svg = render(json.loads(model_json), positioned)
        svg_tree = ElementTree.fromstring(svg)
        if svg_tree.tag != SVG + "svg":
            raise ValueError(f"{case}: renderer did not return SVG.")
        labels = set()
        for label in svg_tree.iter(SVG + "text"):
            lines = label.findall(SVG + "tspan")
            labels.add("\n".join(line.text or "" for line in lines) if lines else (label.text or ""))
        missing = set(expected_text) - labels
        if missing:
            raise ValueError(f"{case}: missing rendered text: {sorted(missing)!r}.")
        if labels & (set(positioned["nodes"]) | set(positioned["regions"])):
            raise ValueError(f"{case}: generated internal IDs leaked into rendered text.")
        paths = ("smd.json", "layout.json", "svg")
        for extension, content in zip(paths, (model_json, layout_json, svg), strict=True):
            (args.output_dir / f"{case}.{extension}").write_bytes(content.encode("utf-8"))
        print(f"{case}: {len(positioned['nodes'])} vertices, {len(positioned['edges'])} transitions, valid SVG")


if __name__ == "__main__":
    main()
