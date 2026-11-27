"""Build or transform a JSON input and emit SMD JSON."""

import argparse
import json
import sys
from pathlib import Path

from . import MockConverterAdapter, build_model, serialize_model, transform_model


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
        text = serialize_model(model)
        if args.output is None:
            sys.stdout.buffer.write(text.encode("utf-8"))
        else:
            args.output.write_bytes(text.encode("utf-8"))
    except (OSError, ValueError, RecursionError) as error:
        sys.stderr.buffer.write(f"{error}\n".encode("utf-8", errors="backslashreplace"))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
