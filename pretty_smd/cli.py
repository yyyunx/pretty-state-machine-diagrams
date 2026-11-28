"""Command-line entry point to the shared pipeline."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from src.model import ModelError, serialize_model

from .benchmark import run_benchmark
from .pipeline import InputError, generate, prepare_model, read_json
from src.layout.engine import LayoutOptions


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _diagnostic(item):
    return f"{item.severity} {item.code} at {item.path or '<root>'}: {item.message}"


def _set_option(argument):
    name, sep, value = argument.partition("=")
    if not sep or name not in vars(LayoutOptions()) or name == "direction":
        raise argparse.ArgumentTypeError("Use OPTION=NUMBER with a numeric LayoutOptions field")
    try:
        return name, float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Layout setting needs a number") from exc


def _input_args(command):
    command.add_argument("input", type=Path)
    command.add_argument("--format", choices=("auto", "smd", "mock", "pa"), default="auto")
    command.add_argument("--case", help="Pick a member of a JSON fixture bundle.")
    command.add_argument("--structural", action="store_true", help="Validate the SMD schema and graph only.")


def _save_outputs(input_path, outputs):
    filled = [(path, text) for path, text in outputs if path is not None]
    resolved = [path.resolve() for path, _ in filled]
    if len(resolved) != len(set(resolved)) or input_path.resolve() in resolved:
        raise InputError("Choose different input and output file paths.")
    for path, text in filled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pretty-smd")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("generate", help="Generate an SVG and optional JSON outputs.")
    _input_args(make)
    make.add_argument("--output", type=Path, help="SVG file. Defaults to stdout.")
    make.add_argument("--smd-output", type=Path)
    make.add_argument("--layout-output", type=Path)
    make.add_argument("--quality-output", type=Path)
    make.add_argument("--direction", choices=("horizontal", "vertical"), default="horizontal")
    make.add_argument("--algorithm", choices=("topology","legacy","advanced","hybrid"), default="topology")
    make.add_argument("--dot",help="Optional dot executable for a Hybrid candidate.")
    make.add_argument("--mode", choices=("fast","balanced","quality"), default="balanced")
    make.add_argument("--timeout",type=float,help="Cancel advanced or topology search after this many seconds.")
    make.add_argument("--allow-rotate",action="store_true",help="Let advanced search test the other direction.")
    make.add_argument("--set", type=_set_option, action="append", default=[], metavar="OPTION=NUMBER")
    _input_args(commands.add_parser("validate", help="Validate a document and report diagnostics."))
    bench = commands.add_parser("benchmark", help="Run the same dataset through the two layout engines.")
    bench.add_argument("--output-dir", type=Path, default=Path("benchmark-output"))
    bench.add_argument("--repeats", type=int, default=1)
    bench.add_argument("--memory", action="store_true")
    large = commands.add_parser("benchmark-advanced",help="Run isolated reference and stress workloads.")
    large.add_argument("--output-dir",type=Path,default=Path("benchmark-output/advanced"))
    large.add_argument("--suite",choices=("all","reference","stress"),default="all")
    large.add_argument("--timeout",type=float,default=6)
    large.add_argument("--repeats",type=int,default=1)
    large.add_argument("--dot",help="Path to an optional Graphviz dot executable.")
    large.add_argument("--case",action="append",help="Select one or more benchmark cases.")
    large.add_argument("--engine",action="append",
                       choices=("legacy","topology","advanced-fast","advanced-balanced","advanced-quality",
                                "graphviz","hybrid","hybrid-dot"))
    web = commands.add_parser("serve", help="Run the local web app.")
    web.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            from .web import serve
            serve(args.port)
        elif args.command == "benchmark":
            rows = run_benchmark(args.output_dir, repeats=args.repeats, memory=args.memory)
            print(f"Saved {len(rows)} runs to {args.output_dir}")
        elif args.command == "benchmark-advanced":
            from .phase4_benchmark import run
            rows = run(args.output_dir,suite=args.suite,timeout=args.timeout,dot=args.dot,
                       repeats=args.repeats,case_filter=args.case,engines=args.engine,
                       on_row=lambda row:print(row["case"],row["algorithm"],row["status"],flush=True))
            print(f"Saved {len(rows)} runs to {args.output_dir}")
        else:
            source = read_json(args.input)
            options = dict(input_format=args.format, case=args.case, uml=not args.structural)
            if args.command == "validate":
                _, warnings = prepare_model(source, **options)
                sys.stdout.buffer.write(_json({"valid": True, "warnings": [asdict(item) for item in warnings]}).encode("utf-8"))
                return 0
            external = None
            if args.dot and (args.direction=="horizontal" or args.allow_rotate):
                from subprocess import SubprocessError
                from .graphviz import graphviz_layout
                def external(model,remaining):
                    try:
                        return graphviz_layout(model,args.dot,timeout=remaining)
                    except SubprocessError as error:
                        raise InputError("Graphviz failed or exceeded its time budget.") from error
            result = generate(
                source, options=LayoutOptions(direction=args.direction, **dict(args.set)), algorithm=args.algorithm,
                mode=args.mode, timeout=args.timeout, allow_rotate=args.allow_rotate,
                external_name="graphviz" if external is not None else None,external_layout=external,
                **options,
            )
            _save_outputs(args.input, (
                (args.output, result.svg), (args.smd_output, serialize_model(result.model)),
                (args.layout_output, _json(result.layout)), (args.quality_output, _json(result.quality)),
            ))
            for warning in result.warnings:
                sys.stderr.buffer.write((_diagnostic(warning) + "\n").encode("utf-8"))
            if args.output is None:
                sys.stdout.buffer.write(result.svg.encode("utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        message = "\n".join(_diagnostic(item) for item in exc.diagnostics) if isinstance(exc, ModelError) else str(exc)
        sys.stderr.buffer.write((message + "\n").encode("utf-8", errors="backslashreplace"))
        return 2
    return 0
