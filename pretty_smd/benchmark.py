"""Repeatable comparison of the integrated baseline and topology-aware layout."""

import csv
from copy import deepcopy
from importlib.resources import files
import json
from pathlib import Path
import platform
from random import Random
import statistics
from time import perf_counter
import tracemalloc

from src.layout.engine import LayoutOptions, layout
from src.layout.quality import evaluate
from src.model import MockConverterAdapter, build_model, serialize_model, transform_model, validate_model
from src.renderer import render

from .pipeline import prepare_model


def resource(name):
    return files("pretty_smd").joinpath("data", name).read_text(encoding="utf-8")


def sample_cases():
    adapter = MockConverterAdapter()
    for version, names in (
        ("p1", ("linear", "resolvedBranch")), ("p2", ("nested", "orthogonal", "pseudostates")),
    ):
        document = json.loads(resource(f"mock-converter-{version}.json"))
        for name in names:
            yield name, transform_model(document[name], adapter)


def _graph(name, count, arcs, titles=(), shuffle=False):
    vertices = [{"id": f"v{i}", "kind": "state", "displayName": titles[i] if i < len(titles) else f"State {i}"}
                for i in range(count)]
    if shuffle:
        Random(19).shuffle(vertices)
    transitions = [{"sourceId": f"v{a}", "targetId": f"v{b}", "triggers": [f"event_{i}"]}
                   for i, (a, b) in enumerate(arcs)]
    return build_model({"id": name, "regions": [{"vertices": vertices, "transitions": transitions}]})


def cases():
    yield from sample_cases()
    yield "cycle", _graph("cycle", 4, [(0,1),(1,2),(2,0),(2,3)], shuffle=True)
    yield "self-loop", _graph("self-loop", 2, [(0,0),(0,1),(1,1)])
    yield "bidirectional", _graph("bidirectional", 3, [(0,1),(1,0),(1,2),(2,1),(0,1)])
    model = _graph("multilingual", 2, [(0,1)], ["待審核 Reviewing αβ", "完成 Completion"])
    edge = model["regions"][0]["transitions"][0]
    edge["sourceText"] = "verify(payload) [輸入資料已驗證 ∧ payload.isReady()] / " + (
        "記錄處理結果並保留稽核資訊 saveValidatedResult(payload); " * 5
    )
    yield "multilingual", model
    for size in (12, 28, 48):
        arcs = [(i,i+1) for i in range(size-1)] + [(i,i+3) for i in range(0,size-3,5)]
        yield f"synthetic-{size}", _graph(f"synthetic-{size}", size, arcs)
    inner = {"vertices": [{"kind": "state", "displayName": "Leaf"}], "transitions": []}
    for level in range(5):
        inner = {"vertices": [{"kind":"composite","displayName":f"Container {level}","regions":[inner]}],
                 "transitions": []}
    yield "depth-5", build_model({"id":"depth-5","regions":[inner]})


def run_benchmark(output, *, repeats=1, memory=False):
    if not 1 <= repeats <= 10:
        raise ValueError("repeats must be from 1 to 10")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, model in cases():
        validate_model(model)
        for algorithm in ("legacy", "topology"):
            folder = output / algorithm
            folder.mkdir(exist_ok=True)
            original = deepcopy(model)
            layouts, renders, totals, complete = [], [], [], []
            for _ in range(repeats):
                start = perf_counter()
                prepared, _ = prepare_model(model)
                ready = perf_counter()
                geometry = layout(prepared, LayoutOptions(), algorithm=algorithm)
                laid = perf_counter()
                svg = render(prepared, geometry)
                ended = perf_counter()
                evaluate(prepared, geometry, original_model=original)
                layouts.append((laid-ready)*1000)
                renders.append((ended-laid)*1000)
                totals.append((ended-ready)*1000)
                complete.append((perf_counter()-start)*1000)
            row = dict(case=name, algorithm=algorithm, nodes=len(geometry["nodes"]),
                       transitions=len(geometry["edges"]))
            row.update(evaluate(model, geometry, original_model=original,
                                execution_ms=round(statistics.median(layouts), 3)))
            row.update(render_ms=round(statistics.median(renders), 3),
                       layout_render_ms=round(statistics.median(totals), 3),
                       pipeline_ms=round(statistics.median(complete), 3))
            if memory:
                tracemalloc.start()
                try:
                    render(model, layout(model, LayoutOptions(), algorithm=algorithm))
                    row["peak_python_kib"] = round(tracemalloc.get_traced_memory()[1] / 1024, 1)
                finally:
                    tracemalloc.stop()
            (folder / f"{name}.smd.json").write_bytes(serialize_model(model).encode("utf-8"))
            (folder / f"{name}.layout.json").write_bytes(
                (json.dumps(geometry, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8"))
            (folder / f"{name}.svg").write_bytes(svg.encode("utf-8"))
            rows.append(row)
    with (output / "comparison.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    metadata = {"python": platform.python_version(), "platform": platform.platform(),
                "repeats": repeats, "memory": memory, "baseline_commit": "5b1eefd", "results": rows}
    (output / "comparison.json").write_bytes((json.dumps(metadata, indent=2)+"\n").encode("utf-8"))
    return rows
