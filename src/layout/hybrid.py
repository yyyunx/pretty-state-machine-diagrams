"""Explainable algorithm portfolio using model features and hard geometry gates."""

from collections import Counter
from copy import deepcopy
from math import isfinite
from time import monotonic, perf_counter

from src.geometry import behavior_lines, text_lines, transition_text
from src.model import validate_model

from .advanced import HARD_ZERO, WEIGHTS, _finite, _hierarchy, _labels, _score, optimize, OptimizationResult
from .budget import BudgetExceeded
from .engine import LayoutError, LayoutOptions, layout
from .quality import evaluate, model_index
from .topology import connected_components


def analyze_graph(model):
    vertices,ancestors,regions,transitions = model_index(model)
    region_of = {}
    region_labels = []
    orthogonal = 0
    pending = [model["regions"]]
    while pending:
        group = pending.pop()
        if len(group)>1:
            orthogonal += len(group)
        for region in group:
            if region.get("displayName"):
                region_labels.append(region["displayName"])
            for vertex in region["vertices"]:
                region_of[vertex["id"]]=region["id"]
                if vertex.get("regions"):
                    pending.append(vertex["regions"])
    pairs = [(edge["sourceId"],edge["targetId"]) for edge in transitions.values()]
    components,owner,_,_ = connected_components(list(vertices),pairs)
    loops = sum(a==b for a,b in pairs)
    unique = set(pairs)
    cyclic = sum(a!=b and owner[a]==owner[b] for a,b in unique)
    count = len(vertices)
    labeled = region_labels + [vertex["displayName"] for vertex in vertices.values() if vertex.get("displayName")]
    labeled += [line for vertex in vertices.values() for line in behavior_lines(vertex)]
    labeled.extend(filter(None,map(transition_text,transitions.values())))
    return {
        "vertices":count,"transitions":len(pairs),
        "density":round(sum(a!=b for a,b in unique)/max(1,count*(count-1)),8),
        "edges_per_vertex":round(len(pairs)/max(1,count),5),
        "scc_count":len(components),"largest_scc":max(map(len,components),default=0),
        "cycle_complexity":cyclic+loops,"self_loops":loops,"parallel_edges":len(pairs)-len(unique),
        "hierarchy_depth":max((len(path) for path in ancestors.values()),default=0),
        "orthogonal_regions":orthogonal,"region_count":len(regions),
        "cross_region":sum(region_of[a]!=region_of[b] for a,b in pairs),
        "cross_level":sum(ancestors[a]!=ancestors[b] for a,b in pairs),
        "pseudostates":dict(sorted(Counter(v["pseudostateKind"] for v in vertices.values()
                                          if "pseudostateKind" in v).items())),
        "labels":{"count":len(labeled),"characters":sum(map(len,labeled)),
                  "longest":max(map(len,labeled),default=0),
                  "lines":sum(len(text_lines(label)) for label in labeled)},
    }


def passes_geometry(model, geometry, metrics, index):
    return (metrics["semantic_preservation"] and all(metrics[key]==0 for key in HARD_ZERO)
            and _finite(geometry) and _hierarchy(geometry,model["regions"]) and _labels(model,geometry,index))


def _plan(features,mode,budget,external):
    n,e = features["vertices"],features["transitions"]
    dense = features["edges_per_vertex"]>=2.7
    cycles = features["largest_scc"]>=4
    complex_graph = cycles or features["cross_level"] or features["orthogonal_regions"]
    reasons = []
    if dense: reasons.append("high-edge-density")
    if cycles: reasons.append("large-scc")
    if features["hierarchy_depth"]: reasons.append("composite-hierarchy")
    if features["cross_level"]: reasons.append("cross-level-transitions")
    if n>=40 or budget<=3: reasons.append("bounded-runtime")
    if external is None:
        reasons.append("optional-external-engine-unavailable")
    candidates = []
    if n>=80 or dense or budget<=3 or mode=="fast":
        candidates.append("advanced-fast")
        if dense and external is not None:
            candidates.append(external)
        if n<40 and (not dense or mode!="fast"):
            candidates.append("advanced-balanced")
    elif n<=16 and e<=max(1,n*2) and not complex_graph and mode!="quality":
        candidates.append("topology")
        reasons.append("small-sparse-graph")
    else:
        candidates.append("advanced-quality" if mode=="quality" and n<=60 else "advanced-balanced")
        if n<60 and not dense:
            candidates.append("topology")
    return tuple(dict.fromkeys(candidates)),reasons


def optimize_hybrid(model, options=None, *, mode="balanced", timeout=None, allow_rotate=False,
                    external_name=None, external_layout=None):
    if mode not in ("fast","balanced","quality"):
        raise LayoutError("Hybrid mode must be fast, balanced or quality.")
    seconds = 10.0 if timeout is None else timeout
    if type(seconds) not in (int,float) or not isfinite(seconds) or seconds<=0:
        raise LayoutError("Layout timeout must be a positive finite number.")
    options = options if options is not None else LayoutOptions()
    original = deepcopy(model)
    validate_model(model,uml=True)
    features = analyze_graph(model)
    index = model_index(model)
    budget_end = monotonic()+seconds
    names,reasons = _plan(features,mode,seconds,external_name if external_layout is not None else None)
    accepted, rows = [],[]
    for i,name in enumerate(names):
        elapsed = budget_end-monotonic()
        if elapsed<=0:
            break
        remaining = elapsed if i==len(names)-1 else elapsed*.63
        mark = perf_counter()
        search = {}
        try:
            if name.startswith("advanced-"):
                result = optimize(model,options,mode=name.removeprefix("advanced-"),
                                  timeout=remaining,allow_rotate=allow_rotate)
                geometry,metrics = result.layout,result.metrics
                search = result.search
                work = search["work"]
            elif name=="topology":
                geometry = layout(model,options,timeout=remaining)
                metrics = evaluate(model,geometry,original_model=original)
                work = max(1,features["transitions"]*140)
            else:
                geometry = external_layout(remaining)
                metrics = evaluate(model,geometry,original_model=original)
                work = max(1,features["transitions"]*90)
            if not passes_geometry(model,geometry,metrics,index):
                rows.append({"candidate":name,"status":"invalid-geometry"})
                continue
            row = {"candidate":name,"status":"valid","work":work,
                   "elapsed_ms":round((perf_counter()-mark)*1000,3),
                   **({"placement":search["selected"]} if search else {})}
            rows.append(row)
            accepted.append((row,geometry,metrics,dict(metrics,work=work)))
        except (ValueError,OSError) as error:
            rows.append({"candidate":name,"status":"rejected","detail":str(error)[:300]})
    if not accepted and "topology" not in names and features["vertices"]<=120 and monotonic()<budget_end:
        reasons.append("advanced-candidates-rejected")
        try:
            geometry = layout(model,options,timeout=budget_end-monotonic())
            metrics = evaluate(model,geometry,original_model=original)
            if passes_geometry(model,geometry,metrics,index):
                row = {"candidate":"topology","status":"valid","fallback":True}
                rows.append(row)
                accepted.append((row,geometry,metrics,dict(metrics,work=1)))
        except (ValueError,OSError) as error:
            rows.append({"candidate":"topology","status":"rejected","detail":str(error)[:300]})
    if not accepted:
        detail = "; ".join(f"{row['candidate']}: {row.get('detail',row['status'])}" for row in rows)
        if monotonic()>=budget_end or "time limit" in detail:
            raise BudgetExceeded("Hybrid layout exceeded its time limit. "+detail)
        raise LayoutError("No hybrid candidate satisfies the geometry constraints. "+detail)
    # Bound every cost contribution by its weight, including metrics whose
    # first candidate starts at zero. Time is reported; stable work breaks ties.
    reference = {key:max(value[key] for _,_,_,value in accepted) for key in WEIGHTS}
    for row,_,metrics,value in accepted:
        row["score"] = round(_score(metrics,value["work"],reference),8)
        row["crossings"] = metrics["edge_crossings"]
        row["area"] = metrics["diagram_area"]
    row,geometry,metrics,_ = min(accepted,key=lambda value:value[0]["score"])
    return OptimizationResult(geometry,metrics,{"mode":mode,"selected":row["candidate"],"candidates":rows,
                                                "reasons":reasons,"features":features})
