"""Command-line entry point: python -m src.renderer MODEL.json LAYOUT.json OUTPUT.svg."""
import argparse
from .renderer import render_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Render an SMD model and layout as SVG.")
    parser.add_argument("model", help="SMD Model JSON path")
    parser.add_argument("layout", help="Layout Data JSON path")
    parser.add_argument("output", help="Output SVG path")
    args = parser.parse_args()
    print(render_files(args.model, args.layout, args.output))


if __name__ == "__main__":
    main()
