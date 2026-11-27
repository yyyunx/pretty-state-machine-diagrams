"""Deterministic multi-objective search over topology and routing candidates."""

from copy import deepcopy
from dataclasses import dataclass, replace
from math import isfinite
from time import perf_counter

from src.model import validate_model
from src.geometry import rect, transition_text

from .budget import BudgetExceeded, SearchBudget
from .engine import LayoutError, LayoutOptions, PlacementProfile, _Placement
from .quality import evaluate, model_index


@dataclass(frozen=True)
class OptimizationResult:
    layout: dict
    metrics: dict
    search: dict


# The budgets are deterministic operation ceilings, independent of machine speed.
BUDGETS = {"fast": 320_000, "balanced": 690_000, "quality": 1_250_000}
WEIGHTS = {
    "edge_crossings": 12, "label_collisions": 9, "label_path_intersections": 5,
    "edge_node_intersections": 14, "edge_overlap_length": 4, "total_edge_length": 5,
    "edge_bends": 3, "diagram_area": 2, "work": 1,
}
HARD_ZERO = ("disconnected_anchors", "node_overlaps", "edge_node_intersections", "broken_paths")


def _candidates(options, mode, vertices, edges, allow_rotate):
    dense = edges > vertices * 2
    bounded = vertices >= 100 or dense
    tight = replace(options, layer_spacing=max(4,options.layer_spacing*.8),
                    node_spacing=max(4,options.node_spacing*.82))
    yield "indexed", options, PlacementProfile(split_cycles=vertices>=25)
    if mode == "fast":
        return
    yield "compact", tight, PlacementProfile(order="median", split_cycles=True,
                                            reverse_sweep=True, route_order="long", reroutes=2)
    if bounded:
        return
    yield "crossings", replace(options,crossing_penalty=min(500, options.crossing_penalty*1.65)), PlacementProfile(
        order="median", route_order="short", reroutes=4)
    if mode == "quality":
        wide = replace(options, node_spacing=min(500,options.node_spacing*1.25),
                       layer_spacing=min(500,options.layer_spacing*1.18))
        yield "clearance", wide, PlacementProfile(order="median", reverse_sweep=True,
                                                route_order="long", extra_channels=True, reroutes=6)
        yield "scc", tight, PlacementProfile(split_cycles=True, route_order="short", extra_channels=True, reroutes=6)
    if allow_rotate:
        direction = "vertical" if options.direction=="horizontal" else "horizontal"
        yield "rotated", replace(tight,direction=direction), PlacementProfile(
            order="median", split_cycles=True, route_order="long", reroutes=2)


def _finite(geometry):
    stack = [geometry]
    while stack:
        value = stack.pop()
        if isinstance(value,dict):
            stack.extend(value.values())
        elif isinstance(value,list):
            stack.extend(value)
        elif isinstance(value,(int,float)) and not isfinite(value):
            return False
    return True


def _inside(inner, outer):
    x,y,r,b = rect(inner)
    u,v,s,t = rect(outer)
    return x>=u-1e-6 and y>=v-1e-6 and r<=s+1e-6 and b<=t+1e-6


def _hierarchy(geometry, regions, parent=None):
    for region in regions:
        rb = geometry["regions"][region["id"]]["bounds"]
        if parent is not None and not _inside(rb,parent):
            return False
        for node in region["vertices"]:
            bounds = geometry["nodes"][node["id"]]["bounds"]
            if parent is not None and node.get("pseudostateKind") in ("entryPoint","exitPoint"):
                x,y,r,b = rect(bounds)
                u,v,s,t = rect(parent)
                x,y = (x+r)/2,(y+b)/2
                if not (u<=x<=s and v<=y<=t and min(abs(x-u),abs(x-s),abs(y-v),abs(y-t))<1e-6):
                    return False
            elif not _inside(bounds,rb):
                return False
            if not _hierarchy(geometry,node.get("regions",()),bounds):
                return False
    return True


def _labels(model, geometry, index):
    vertices, _, _, transitions = index
    if any("labelBounds" not in geometry["nodes"][key] for key,node in vertices.items() if node.get("displayName")):
        return False
    if any("labelBounds" not in geometry["edges"][key] for key,edge in transitions.items() if transition_text(edge)):
        return False
    regions = list(model["regions"])
    while regions:
        region = regions.pop()
        if region.get("displayName") and "labelBounds" not in geometry["regions"][region["id"]]:
            return False
        regions.extend(child for node in region["vertices"] for child in node.get("regions",()))
    return True


def _score(metrics, work, reference):
    # Normalize against the first valid geometry. Work is a stable cost proxy;
    # elapsed wall time is reported separately and never changes a winner.
    values = dict(metrics,work=work)
    return sum(weight*values[key]/max(1, reference[key]) for key,weight in WEIGHTS.items())


def optimize(model, options=None, *, mode="balanced", timeout=None, allow_rotate=False):
    if mode not in BUDGETS:
        raise LayoutError("Advanced mode must be fast, balanced or quality.")
    if timeout is not None and (type(timeout) not in (int,float) or not isfinite(timeout) or timeout<=0):
        raise LayoutError("Layout timeout must be a positive finite number.")
    options = options if options is not None else LayoutOptions()
    if not isinstance(options,LayoutOptions):
        raise LayoutError("Expected LayoutOptions or None")
    budget = SearchBudget(BUDGETS[mode],timeout)
    original = deepcopy(model)
    validate_model(model,uml=True)
    index = model_index(model)
    vertices, _, _, transitions = index
    if len(vertices)>500 or len(transitions)>2400:
        raise LayoutError("Advanced layout supports at most 500 vertices and 2,400 transitions per search.")
    candidates, best, reference = [], None, None
    for name,settings,profile in _candidates(options,mode,len(vertices),len(transitions),allow_rotate):
        budget.check()
        start, before = perf_counter(),budget.operations
        try:
            geometry = _Placement(model,settings,profile,budget).run()
        except LayoutError as error:
            candidates.append({"candidate":name,"status":"routing-failed","detail":str(error)})
            continue
        metrics = evaluate(model,geometry,original_model=original,budget=budget)
        work = budget.operations-before
        if not (metrics["semantic_preservation"] and all(metrics[m]==0 for m in HARD_ZERO)
                and _finite(geometry) and _hierarchy(geometry,model["regions"]) and _labels(model,geometry,index)):
            candidates.append({"candidate":name,"status":"invalid-geometry",
                               "violations":{m:metrics[m] for m in HARD_ZERO if metrics[m]}})
            continue
        if reference is None:
            reference = dict(metrics,work=work)
        score = _score(metrics,work,reference)
        candidates.append({"candidate":name,"status":"valid","score":round(score,8),"work":work,
                           "elapsed_ms":round((perf_counter()-start)*1000,3),"direction":settings.direction})
        if best is None or score<best[0]:
            best = score,name,geometry,metrics
    budget.check()
    if best is None:
        detail = "; ".join(row.get("detail",str(row.get("violations"))) for row in candidates)
        raise LayoutError(f"No advanced candidate satisfies the geometry constraints. {detail}")
    _,name,geometry,metrics = best
    return OptimizationResult(geometry,metrics,{"mode":mode,"selected":name,"candidates":candidates,
                                               "work":budget.operations,"work_limit":budget.limit})
