"""Assemble the static GitHub Pages artifact from reviewed benchmark assets."""

import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def build(output):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    for name in ("index.html","gallery.css","gallery.js"):
        shutil.copyfile(ROOT/"demo"/name,output/name)
    target = output/"benchmarks"/"phase4"
    target.mkdir(parents=True,exist_ok=True)
    for name in ("comparison.json","comparison.csv","performance.svg"):
        shutil.copyfile(ROOT/"benchmarks"/"phase4"/name,target/name)
    for algorithm in ("legacy","topology","advanced-quality"):
        folder = target/algorithm
        folder.mkdir(exist_ok=True)
        for svg in (ROOT/"benchmarks"/"phase4"/algorithm).glob("*.svg"):
            shutil.copyfile(svg,folder/svg.name)
    (output/".nojekyll").touch()


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=Path("dist"))
    build(parser.parse_args().output)
