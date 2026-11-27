"""Build or transform a JSON input and emit SMD JSON."""

import argparse
import json
import sys
from pathlib import Path

from . import MockConverterAdapter, ModelError, build_model, serialize_model, transform_model, validate_model


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON property {key!r}.")
        value[key] = item
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "transform"))
    parser.add_argument("input", type=Path)
    parser.add_argument("--case", help="Select a top-level member of a fixture bundle.")
    parser.add_argument("--output", type=Path, help="Write UTF-8 JSON to this file (default: stdout).")
    parser.add_argument("--uml", action="store_true", help="Check UML semantics and report warnings.")
    args = parser.parse_args(argv)

    try:
        data = json.loads(args.input.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        if args.case is not None:
            if not isinstance(data, dict) or args.case not in data:
                raise ValueError(f"Fixture case {args.case!r} was not found in {args.input}.")
            data = data[args.case]
        if args.operation == "transform":
            model = transform_model(data, MockConverterAdapter())
        else:
            model = build_model(data)
        if args.uml:
            for item in validate_model(model, uml=True):
                sys.stderr.buffer.write(f"warning {item.code} at {item.path}: {item.message}\n".encode("utf-8"))
        text = serialize_model(model)
        if args.output is None:
            sys.stdout.buffer.write(text.encode("utf-8"))
        else:
            args.output.write_bytes(text.encode("utf-8"))
    except ModelError as error:
        for item in error.diagnostics:
            sys.stderr.buffer.write(
                f"{item.severity} {item.code} at {item.path or '<root>'}: {item.message}\n".encode(
                    "utf-8", errors="backslashreplace",
                )
            )
        return 2
    except (OSError, ValueError, RecursionError) as error:
        sys.stderr.buffer.write(f"{error}\n".encode("utf-8", errors="backslashreplace"))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
