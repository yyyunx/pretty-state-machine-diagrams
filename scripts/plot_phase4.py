"""Plot isolated measured timings and failure markers from the report."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter

NAMES = {"topology":"Phase 3", "advanced-fast":"Advanced Fast","advanced-balanced":"Advanced Balanced"}
SIZES = (10,25,50,100,250,500)
matplotlib.rcParams.update({"svg.fonttype":"none","svg.hashsalt":"pretty-smd-phase4"})


def plot(source, output):
    report = json.loads(Path(source).read_bytes())
    rows = [r for r in report["results"] if r["suite"]=="stress"]
    colours = ("#46576e","#2173a8","#ac552a")
    figure, panels = plt.subplots(1,2,figsize=(12,4.4),sharey=True,layout="constrained")
    failure_band = (report["timeout"]+report.get("isolated_overhead_allowance_s",2))*1000
    for panel,family,title in zip(panels,("sparse","dense"),("Sparse graph","Dense graph")):
        for (engine,name),colour in zip(NAMES.items(),colours):
            by_size = {r["vertices"]:r for r in rows if r["case"].startswith(family+"-") and r["algorithm"]==engine}
            if not by_size:
                continue
            panel.plot(SIZES,[by_size.get(n,{}).get("layout_ms",float("nan")) for n in SIZES],
                       marker="o",color=colour,label=name)
            failed = [n for n in SIZES if n in by_size and by_size[n]["status"]!="ok"]
            panel.scatter(failed,[failure_band]*len(failed),marker="x",color=colour,zorder=4,s=55)
        panel.axhline(failure_band,color="#9cabb8",linestyle="--",linewidth=1)
        panel.text(10,failure_band*1.1,"× incomplete (status in CSV)",fontsize=8,color="#3c4f64")
        panel.set(xscale="log",yscale="log",title=title,xlabel="Vertices")
        panel.set_xticks(SIZES)
        panel.xaxis.set_major_formatter(ScalarFormatter())
        panel.grid(True,which="major",alpha=.22)
    panels[0].set_ylabel("Layout time (ms, log scale)")
    panels[0].legend(loc="lower right",fontsize=8)
    figure.suptitle("Phase 4 · isolated seeded workload measurements",fontweight="bold")
    figure.savefig(output,metadata={"Date":None})
    output = Path(output)
    lines = output.read_text(encoding="utf-8").splitlines()
    output.write_text("\n".join(line.rstrip() for line in lines)+"\n",encoding="utf-8")


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    plot(args.source,args.output)
