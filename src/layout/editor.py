"""Transactional geometry edits and collapsed projections of the original SMD."""

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import json
from math import isfinite
from time import perf_counter

from jsonschema import Draft202012Validator

from src.geometry import SIDES, behavior_lines, box, rect, stroke_box, transition_text
from src.model import validate_model
from src.renderer.renderer import validate_pair

from .advanced import HARD_ZERO, _hierarchy, _labels
from .budget import SearchBudget
from .engine import LayoutError, LayoutOptions, PlacementProfile, _Placement, _label_size
from .quality import evaluate, model_index
from .routing import hits_box, overlap
from .spatial import Occupancy, SpatialIndex, segment_bounds


@dataclass(frozen=True)
class EditedLayout:
    layout: dict
    quality: dict
    edit: dict


def _spatial(geometry):
    index = SpatialIndex()
    for identifier,node in geometry["nodes"].items():
        bounds = rect(node["bounds"])
        index.add(bounds,(identifier,bounds))
    return index


def _shift(value,delta):
    value["x"] += delta[0]
    value["y"] += delta[1]


def _shift_node(placement,delta):
    for field in ("bounds","labelBounds"):
        if field in placement:
            _shift(placement[field],delta)


def _reframe(geometry):
    spans = [rect(part[field]) for key in ("nodes","regions","edges")
             for part in geometry[key].values() for field in ("bounds","labelBounds") if field in part]
    spans.extend((p["x"],p["y"],p["x"],p["y"]) for part in geometry["edges"].values() for p in part["points"])
    x,y = min(s[0] for s in spans)-20,min(s[1] for s in spans)-20
    r,b = max(s[2] for s in spans)+20,max(s[3] for s in spans)+20
    geometry["viewport"] = box(x,y,r-x,b-y)


def _link_paths(model, geometry, affected, options, budget):
    placement = _Placement(model,options,PlacementProfile(),budget)
    placement.nodes,placement.regions = geometry["nodes"],geometry["regions"]
    placement.behaviors = {k:behavior_lines(v) for k,v in placement.vertices.items()}
    placement.names = {k:_label_size(v["displayName"]) if v.get("displayName") else (0,0)
                       for k,v in placement.vertices.items()}
    opposite = dict(zip(SIDES,("right","left","bottom","top"),strict=True))
    for key,vertex in placement.vertices.items():
        if vertex.get("pseudostateKind") not in ("entryPoint","exitPoint") or not placement.ancestors[key]:
            continue
        x,y,r,b = rect(geometry["nodes"][key]["bounds"])
        u,v,s,t = rect(geometry["nodes"][placement.ancestors[key][-1]]["bounds"])
        cx,cy = (x+r)/2,(y+b)/2
        side = min(zip(SIDES,(abs(cx-u),abs(cx-s),abs(cy-v),abs(cy-t)),strict=True),key=lambda value:value[1])[0]
        placement.boundary_ports[key] = side,opposite[side]
    occupancy = Occupancy()
    index = _spatial(geometry)
    path_segments = placement._segments
    paths = {key:part for key,part in geometry["edges"].items() if key not in affected}
    occupied = [part["labelBounds"] for part in (*placement.nodes.values(),*placement.regions.values(),*paths.values())
                if "labelBounds" in part]
    dividers = [stroke_box(a,b) for region in placement.regions.values()
                for a,b in region.get("separatorSegments",())]
    for key,part in paths.items():
        occupancy.add(key,path_segments(part["points"]))
    lanes = Counter()
    for edge in placement.transitions:
        pair = tuple(sorted((edge["sourceId"],edge["targetId"])))
        lane = lanes[pair]
        lanes[pair] += 1
        identifier = edge["id"]
        if identifier not in affected:
            continue
        points = placement._route(edge,lane,(),index,occupancy)
        paths[identifier] = {"points":points}
        occupancy.add(identifier,path_segments(points))
    for edge in placement.transitions:
        key = edge["id"]
        if key in affected and transition_text(edge):
            label = placement._label(edge,paths[key]["points"],occupied,dividers,occupancy)
            paths[key]["labelBounds"] = label
            occupied.append(label)
    geometry["edges"] = paths


def _position(value,identifier):
    if (not isinstance(value,dict) or set(value)!={"x","y"}
            or any(type(n) not in (int,float) or abs(n)>1e7 or not isfinite(n) for n in value.values())):
        raise LayoutError(f"Invalid requested position for {identifier!r}.")
    return value["x"],value["y"]


@lru_cache(maxsize=1)
def _layout_validator():
    schema = json.loads(files("schemas").joinpath("layout.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_scene(model, geometry, *, timeout=8):
    validate_model(model,uml=True)
    failure = next(_layout_validator().iter_errors(geometry), None)
    if failure:
        location = "/".join(map(str,failure.absolute_path)) or "layout"
        raise LayoutError(f"Invalid layout at {location}: {failure.message[:200]}")
    validate_pair(model,geometry)
    pending = [geometry]
    while pending:
        value = pending.pop()
        if isinstance(value,dict):
            pending.extend(value.values())
        elif isinstance(value,list):
            pending.extend(value)
        elif type(value) in (int,float) and (abs(value)>1e7 or not isfinite(value)):
            raise LayoutError("A saved coordinate exceeds the editor's geometry limits.")
    quality = evaluate(model,geometry,budget=SearchBudget(320_000,timeout))
    if (not quality["semantic_preservation"] or any(quality[key] for key in HARD_ZERO)
            or not _hierarchy(geometry,model["regions"]) or not _labels(model,geometry,model_index(model))):
        raise LayoutError("The saved layout fails the hierarchy, anchor or collision checks.")
    return quality


def validate_locks(geometry, locked):
    if not isinstance(locked,dict) or set(locked)-set(geometry["nodes"]):
        raise LayoutError("A locked State ID does not exist.")
    for identifier,value in locked.items():
        bounds = geometry["nodes"][identifier]["bounds"]
        if _position(value,identifier)!=(bounds["x"],bounds["y"]):
            raise LayoutError(f"Locked position differs from the current State {identifier!r}.")


def edit_layout(model, geometry, moves, *, locked=None, options=None, timeout=8):
    """Move nodes without mutation. Re-route incident and newly obstructed paths."""
    start = perf_counter()
    validate_pair(model,geometry)
    validate_model(model,uml=True)
    options = options or LayoutOptions()
    vertices,ancestors,region_owners,transitions = model_index(model)
    locked = {} if locked is None else locked
    if not isinstance(moves,dict) or set(moves)-set(vertices):
        raise LayoutError("An edited State ID does not exist.")
    validate_locks(geometry,locked)
    direct = {}
    for identifier,value in moves.items():
        point = _position(value,identifier)
        bounds = geometry["nodes"][identifier]["bounds"]
        delta = point[0]-bounds["x"],point[1]-bounds["y"]
        direct[identifier] = delta
        if delta==(0,0):
            continue
        if vertices[identifier].get("pseudostateKind") in ("entryPoint","exitPoint") and ancestors[identifier]:
            raise LayoutError("A connection point moves only with its owning Composite State.")
    moving = {identifier for identifier,delta in direct.items() if delta!=(0,0)}
    for identifier in locked:
        if identifier in moving or set(ancestors[identifier]) & moving:
            raise LayoutError(f"State {identifier!r} is locked.")
    edited = deepcopy(geometry)
    shifted = {}
    for identifier,path in ancestors.items():
        delta = next((direct[key] for key in reversed((*path,identifier)) if key in direct),None)
        if delta and delta!=(0,0):
            _shift_node(edited["nodes"][identifier],delta)
            shifted[identifier] = delta
    for key,path in region_owners.items():
        if path and path[-1] in shifted:
            delta = shifted[path[-1]]
            placement = edited["regions"][key]
            _shift_node(placement,delta)
            for segment in placement.get("separatorSegments",()):
                for point in segment:
                    _shift(point,delta)
    if not _hierarchy(edited,model["regions"]):
        raise LayoutError("The move would leave its Region or move a boundary point off its owner.")
    index = SpatialIndex()
    for identifier,part in edited["nodes"].items():
        r = rect(part["bounds"])
        if any(ident not in ancestors[identifier] and identifier not in ancestors[ident]
               and overlap(edited["nodes"][ident]["bounds"],part["bounds"]) for ident in index.query(r)):
            raise LayoutError(f"The move would overlap another State near {identifier!r}.")
        index.add(r,identifier)
    moved_bounds = _spatial({"nodes":{key:edited["nodes"][key] for key in shifted}})
    affected = set()
    for identifier,edge in transitions.items():
        src,dst = edge["sourceId"],edge["targetId"]
        if src in shifted or dst in shifted:
            affected.add(identifier)
            continue
        path = geometry["edges"][identifier]
        legal = {src,dst,*ancestors[src],*ancestors[dst]}
        segments = _Placement._segments(path["points"])
        if any(crossed not in legal and hits_box(a,b,bounds) for a,b in segments
               for crossed,bounds in moved_bounds.query(segment_bounds(a,b))):
            affected.add(identifier)
        elif "labelBounds" in path and any(crossed not in legal for crossed,_ in
                                           moved_bounds.query(rect(path["labelBounds"]))):
            affected.add(identifier)
    budget = SearchBudget(320_000,timeout)
    started = perf_counter()
    fallback = False
    def route_and_check(paths):
        if paths:
            _link_paths(model,edited,paths,options,budget)
        _reframe(edited)
        quality = evaluate(model,edited,execution_ms=round((perf_counter()-started)*1000,3),budget=budget)
        if any(quality[key] for key in HARD_ZERO) or not quality["semantic_preservation"]:
            raise LayoutError("This move would introduce blocked paths or disconnected anchors.")
        return quality

    try:
        quality = route_and_check(affected)
    except LayoutError:
        if not affected or affected==transitions.keys():
            raise
        fallback = True
        quality = route_and_check(set(transitions))
    budget.check()
    info = {"rerouted":sum(geometry["edges"][k]!=edited["edges"][k] for k in transitions),
            "affected":len(affected),"moved":len(shifted),"unaffected_displacement":0,
            "fallback":fallback,"total_ms":round((perf_counter()-start)*1000,3)}
    return EditedLayout(edited,quality,info)


def collapse_projection(model, geometry, collapsed, *, options=None, timeout=8):
    """Create disposable geometry for the collapsed view without touching the source model."""
    validate_pair(model,geometry)
    validate_model(model,uml=True)
    vertices,ancestors,_,transitions = model_index(model)
    if not isinstance(collapsed,list) or any(not isinstance(key,str) or key not in vertices
        or vertices[key]["kind"]!="composite" for key in collapsed):
        raise LayoutError("Only existing Composite States can be collapsed.")
    if len(set(collapsed))!=len(collapsed):
        raise LayoutError("A collapsed Composite State ID is duplicated.")
    collapsed = frozenset(collapsed)
    hidden = {}
    for key,path in ancestors.items():
        parent = next((owner for owner in path if owner in collapsed),None)
        if parent is not None:
            hidden[key] = parent
    scene = deepcopy(model)
    by_region,vertex_region = {},{}
    proposed = deepcopy(geometry)
    regions = proposed["regions"]
    nodes = proposed["nodes"]
    edges = proposed["edges"]
    for key in hidden:
        del nodes[key]

    def visit(region):
        by_region[region["id"]] = region
        region["transitions"] = []
        for node in region["vertices"]:
            key = node["id"]
            vertex_region[key] = region["id"]
            if key in collapsed:
                node["kind"] = "state"
                node.pop("regions",None)
                if "labelBounds" in nodes[key]:
                    nodes[key]["labelBounds"]["y"] = nodes[key]["bounds"]["y"]+5
            else:
                for child in node.get("regions",()):
                    visit(child)
    for region in scene["regions"]:
        visit(region)
    proposed["regions"] = {key:regions[key] for key in by_region}
    affected = set()
    summaries = {key:{"vertices":0,"internal_transitions":0} for key in vertices
                 if key in collapsed and key not in hidden}
    for owner in hidden.values():
        summaries[owner]["vertices"] += 1
    for identifier,edge in transitions.items():
        a,b = edge["sourceId"],edge["targetId"]
        source,target = hidden.get(a,a),hidden.get(b,b)
        if source==target and (source!=a or target!=b):
            summaries[source]["internal_transitions"] += 1
            del edges[identifier]
            continue
        if source!=a or target!=b:
            affected.add(identifier)
        by_region[vertex_region[source]]["transitions"].append(dict(edge,sourceId=source,targetId=target))
    budget = SearchBudget(320_000,timeout)
    if affected:
        _link_paths(scene,proposed,affected,options or LayoutOptions(),budget)
    _reframe(proposed)
    quality = evaluate(scene,proposed,budget=budget)
    if any(quality[key] for key in HARD_ZERO) or not quality["semantic_preservation"]:
        raise LayoutError("The collapsed view cannot preserve its external connections.")
    return scene,proposed,summaries
