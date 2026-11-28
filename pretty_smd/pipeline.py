"""Shared validation, layout and rendering entry point for Python, CLI and HTTP."""

from copy import deepcopy
from dataclasses import dataclass
import json
import math
from pathlib import Path
from time import perf_counter

from src.layout.advanced import optimize
from src.layout.engine import LayoutOptions, layout
from src.layout.quality import evaluate, model_index
from src.model import MockConverterAdapter, transform_model, validate_model
from src.model.model import Diagnostic
from src.renderer import render

MAX_INPUT_BYTES = 1024 * 1024


class InputError(ValueError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"Duplicate JSON property {key!r}.")
        result[key] = value
    return result


def _reject_constant(value):
    raise InputError(f"Non-finite JSON number {value!r}.")


def _finite_float(number):
    result = float(number)
    if not math.isfinite(result):
        raise InputError(f"Non-finite JSON number {number!r}.")
    return result


def _bounded_integer(number):
    if len(number.lstrip("-")) > 100:
        raise InputError("JSON integer exceeds 100 digits.")
    return int(number)


def _bounded(value):
    """Bound work on untrusted JSON trees before recursive validation."""
    count, text_size = 0, 0
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 64 or count > 30000:
            raise InputError("Input nesting exceeds 64 levels or 30,000 values.")
        if isinstance(item, dict):
            pending.extend((child, depth+1) for child in item.values())
            text_size += sum(len(key) for key in item if isinstance(key, str))
        elif isinstance(item, list):
            pending.extend((child, depth+1) for child in item)
        elif isinstance(item, str):
            text_size += len(item)
        if text_size > 256000:
            raise InputError("Input text exceeds 256,000 characters.")


def load_json(data):
    """Parse UTF-8 JSON without duplicate keys or non-finite numbers."""
    if len(data) > MAX_INPUT_BYTES:
        raise InputError("JSON exceeds 1 MiB.")
    try:
        if isinstance(data, bytes):
            data = data.decode("utf-8-sig")
        value = json.loads(data, object_pairs_hook=_object, parse_constant=_reject_constant,
                           parse_float=_finite_float, parse_int=_bounded_integer)
    except (RecursionError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"Invalid JSON: {exc}") from exc
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    _bounded(value)
    return value


def read_json(path):
    with Path(path).open("rb") as stream:
        return load_json(stream.read(MAX_INPUT_BYTES + 1))


def prepare_model(document, *, input_format="auto", case=None, adapter=None, uml=True,
                  max_vertices=500, max_edges=2400):
    _bounded(document)
    if case is not None:
        if not isinstance(document, dict) or case not in document:
            raise InputError(f"Input case {case!r} was not found.")
        document = document[case]
    if input_format not in ("auto", "smd", "mock", "pa"):
        raise InputError(f"Unknown input format {input_format!r}.")
    if input_format == "pa" and adapter is None:
        raise InputError("Raw Process Algebra needs a confirmed external Converter adapter.")
    if adapter is not None or input_format in ("mock", "pa") or (
        input_format == "auto" and isinstance(document, dict) and "kind" in document
    ):
        model = transform_model(document, adapter if adapter is not None else MockConverterAdapter())
        _bounded(model)
    else:
        validate_model(document)
        model = deepcopy(document)
    vertices, _, _, edges = model_index(model)
    if len(vertices) > max_vertices or len(edges) > max_edges:
        raise InputError(f"Model exceeds {max_vertices} vertices or {max_edges} transitions.")
    warnings = validate_model(model, uml=uml) or ()
    return model, warnings


@dataclass(frozen=True)
class GenerationResult:
    model: dict
    layout: dict
    svg: str
    quality: dict
    warnings: tuple[Diagnostic, ...]


def generate(document, *, input_format="auto", case=None, adapter=None, options=None, algorithm="topology",
             uml=True, max_vertices=500, max_edges=2400, mode="balanced", timeout=None, allow_rotate=False,
             progress=None):
    """Generate SVG, SMD, Layout Data and a quality report from the same model."""
    start = perf_counter()
    if progress is not None:
        progress("validate")
    model, warnings = prepare_model(
        document, input_format=input_format, case=case, adapter=adapter, uml=uml,
        max_vertices=max_vertices, max_edges=max_edges,
    )
    original_model = deepcopy(model)
    if progress is not None:
        progress("layout")
    started_layout = perf_counter()
    optimization = None
    if algorithm == "advanced":
        optimization = optimize(model,options,mode=mode,timeout=timeout,allow_rotate=allow_rotate)
        geometry = optimization.layout
    else:
        geometry = layout(model,options,algorithm=algorithm,timeout=timeout)
    layout_ms = 1000 * (perf_counter() - started_layout)
    started_render = perf_counter()
    if progress is not None:
        progress("render")
    svg = render(model, geometry)
    render_ms = 1000 * (perf_counter() - started_render)
    if progress is not None:
        progress("quality")
    quality = (dict(optimization.metrics) if optimization is not None
               else evaluate(model,geometry,original_model=original_model))
    quality["execution_ms"] = round(layout_ms,3)
    if optimization is not None:
        quality["optimization"] = optimization.search
    quality["render_ms"] = round(render_ms, 3)
    quality["pipeline_ms"] = round(1000 * (perf_counter() - start), 3)
    return GenerationResult(model, geometry, svg, quality, warnings)
