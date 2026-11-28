"""Isolated measurements with deadlines, failure rows and optional dot."""

import argparse
from copy import deepcopy
import csv
import json
from math import isfinite
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from time import perf_counter

from src.layout.advanced import optimize
from src.layout.budget import BudgetExceeded
from src.layout.engine import layout
from src.layout.hybrid import optimize_hybrid
from src.layout.quality import evaluate, model_index
from src.model import validate_model
from src.renderer import render

from .benchmark import cases
from .graphviz import graphviz_layout, UnsupportedDot
from .stress import holdout_cases, stress_cases, HOLDOUT_SEED


def _peak_process_kib():
    if sys.platform == "win32":
        from ctypes import POINTER, Structure, byref, sizeof, windll
        from ctypes.wintypes import DWORD, HANDLE, BOOL
        from ctypes import c_size_t

        class Counters(Structure):
            _fields_ = [("size",DWORD),("faults",DWORD),("peak",c_size_t),
                        ("remaining",c_size_t*7)]

        psapi = windll.psapi.GetProcessMemoryInfo
        psapi.argtypes = [HANDLE, POINTER(Counters), DWORD]
        psapi.restype = BOOL
        kernel = windll.kernel32.GetCurrentProcess
        kernel.restype = HANDLE
        result = Counters()
        result.size = sizeof(result)
        return round(result.peak/1024,1) if psapi(kernel(),byref(result),result.size) else None
    import resource
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(usage / (1024 if sys.platform=="darwin" else 1),1)


def _worker(algorithm,dot,limit,repeats,include_svg):
    model = json.loads(sys.stdin.buffer.read())
    original = deepcopy(model)
    times, renders, totals = [], [], []
    try:
        for _ in range(repeats):
            started = perf_counter()
            validate_model(model,uml=True)
            begin = perf_counter()
            if algorithm.startswith("advanced-"):
                result = optimize(model,mode=algorithm.removeprefix("advanced-"),timeout=limit)
                geometry = result.layout
                search = {"selected":result.search["selected"],"candidate_count":len(result.search["candidates"]),
                          "work":result.search["work"]}
            elif algorithm=="graphviz":
                geometry = graphviz_layout(model,dot,timeout=limit)
                search = {}
            elif algorithm in ("hybrid","hybrid-dot"):
                def external(remaining):
                    return graphviz_layout(model,dot,timeout=remaining)
                use_dot = algorithm=="hybrid-dot" and dot
                result = optimize_hybrid(model,timeout=limit,external_name="graphviz" if use_dot else None,
                                         external_layout=external if use_dot else None)
                geometry = result.layout
                search = {"selected":result.search["selected"],"candidate_count":len(result.search["candidates"])}
            else:
                geometry = layout(model,algorithm=algorithm)
                search = {}
            laid = perf_counter()
            svg = render(model,geometry)
            ended = perf_counter()
            metrics = evaluate(model,geometry,original_model=original)
            if not metrics["semantic_preservation"]:
                raise ValueError("Model identity or coverage changed.")
            times.append(1000*(laid-begin))
            renders.append(1000*(ended-laid))
            totals.append(1000*(perf_counter()-started))
        metrics.update(layout_ms=round(statistics.median(times),3),
                       render_ms=round(statistics.median(renders),3),
                       pipeline_ms=round(statistics.median(totals),3),
                       peak_rss_kib=_peak_process_kib(),**search)
        response = {"status":"ok","metrics":metrics}
        if include_svg:
            response.update(layout=geometry,svg=svg)
    except UnsupportedDot as error:
        response = {"status":"unsupported","reason":str(error)}
    except (BudgetExceeded,subprocess.TimeoutExpired) as error:
        status = "timeout" if "time limit" in str(error) or isinstance(error,subprocess.TimeoutExpired) else "work-limit"
        response = {"status":status,"reason":str(error)}
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        response = {"status":"failed","reason":str(error)[:300]}
    sys.stdout.buffer.write(json.dumps(response,ensure_ascii=False,allow_nan=False).encode("utf-8"))


def _save(path,value):
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8"))


def _run(model,algorithm,timeout,dot,repeats,artifacts):
    args = [sys.executable,"-m","pretty_smd.phase4_benchmark","--worker",algorithm,
            "--timeout",str(timeout),"--repeats",str(repeats)]
    if dot:
        args.extend(["--dot",dot])
    if artifacts:
        args.append("--svg")
    try:
        process = subprocess.run(args,input=json.dumps(model).encode("utf-8"),capture_output=True,
                                 timeout=timeout*repeats+2)
    except subprocess.TimeoutExpired:
        return {"status":"timeout","reason":f"Isolated process exceeded {timeout*repeats+2:g} s including startup."}
    if process.returncode:
        return {"status":"worker-failed","reason":process.stderr.decode("utf-8",errors="replace")[-350:]}
    return json.loads(process.stdout)


def run(output, *, suite="all", timeout=6.0, dot=None, repeats=1, case_filter=None, engines=None, on_row=None):
    if not isfinite(timeout) or not .01<=timeout<=120 or not 1<=repeats<=5:
        raise ValueError("Use a timeout from .01 to 120 seconds and one to five repetitions.")
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    if suite not in ("reference","stress","all"):
        raise ValueError("Unknown benchmark suite.")
    version = None
    if dot:
        binary = subprocess.run([dot,"-V"],capture_output=True,timeout=5,check=True)
        version = (binary.stdout+binary.stderr).decode("utf-8",errors="replace").strip()
    reference = ("legacy","topology","advanced-fast","advanced-balanced","advanced-quality")
    stress = ("topology","advanced-fast","advanced-balanced")
    rows = []
    groups = []
    if suite in ("all","reference"):
        groups.append(("reference",cases(),reference))
        groups.append(("holdout",holdout_cases(),reference))
    if suite in ("all","stress"):
        groups.append(("stress",stress_cases(),stress))
    for group,models,algorithms in groups:
        for name,model in models:
            if case_filter and name not in case_filter:
                continue
            vertices,_,_,transitions = model_index(model)
            optional = ("hybrid",)+(("hybrid-dot",) if dot else ())
            extras = tuple(name for name in optional if engines and name in engines)
            for algorithm in (*algorithms,*extras,*(("graphviz",) if dot and group!="stress" else ())):
                if engines and algorithm not in engines:
                    continue
                export = group!="stress" and name in (
                    "pseudostates","self-loop","synthetic-48","orthogonal","nested","holdout-cycles-16")
                data = _run(model,algorithm,timeout,dot,repeats,export)
                rows.append(dict(suite=group,case=name,algorithm=algorithm,vertices=len(vertices),
                                 transitions=len(transitions),status=data["status"],
                                 reason=data.get("reason",""),**data.get("metrics",{})))
                if on_row:
                    on_row(rows[-1])
                if export and data["status"]=="ok":
                    folder = output/algorithm
                    folder.mkdir(exist_ok=True)
                    _save(folder/f"{name}.layout.json",data["layout"])
                    _save(folder/f"{name}.smd.json",model)
                    (folder/f"{name}.svg").write_bytes(data["svg"].encode("utf-8"))
    if not rows:
        raise ValueError("No benchmark cases match.")
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with (output/"comparison.csv").open("w",encoding="utf-8",newline="") as file:
        csv_writer = csv.DictWriter(file,fieldnames=keys)
        csv_writer.writeheader()
        csv_writer.writerows(rows)
    _save(output/"comparison.json",{"phase3_baseline":"d863145","python":platform.python_version(),
        "platform":platform.platform(),"processor":platform.processor(),"seed":HOLDOUT_SEED,
        "timeout":timeout,"isolated_overhead_allowance_s":2,"repeats":repeats,"graphviz":version,"results":rows})
    return rows


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker",required=True)
    parser.add_argument("--dot")
    parser.add_argument("--timeout",type=float,required=True)
    parser.add_argument("--repeats",type=int,required=True)
    parser.add_argument("--svg",action="store_true")
    args = parser.parse_args()
    _worker(args.worker,args.dot,args.timeout,args.repeats,args.svg)
