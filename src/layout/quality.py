"""Measure layout geometry independently of the routing algorithm."""

from itertools import combinations, pairwise
import math

from src.geometry import bar_bounds, corner_radius, outline_boxes, rect, stroke_box, symbol
from .routing import EPSILON, overlap


def model_index(model):
    vertices, owners, regions, transitions = {}, {}, {}, {}

    def visit(region, parents=()):
        regions[region["id"]] = parents
        for vertex in region["vertices"]:
            node = vertex["id"]
            vertices[node], owners[node] = vertex, parents
            for child in vertex.get("regions", []):
                visit(child, (*parents, node))
        transitions.update((edge["id"], edge) for edge in region["transitions"])

    for root in model["regions"]:
        visit(root)
    return vertices, owners, regions, transitions


def _segment_distance(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = dx*dx+dy*dy
    factor = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0
    return math.hypot(p[0]-a[0]-factor*dx, p[1]-a[1]-factor*dy)


def anchor_gap(vertex, bounds, p):
    x, y, r, b = rect(bounds)
    cx, cy = (x+r)/2, (y+b)/2
    w, h = r-x, b-y
    radius = min(w,h)/2
    kind = symbol(vertex)
    if kind == "choice":
        polygon = [(cx,y), (r,cy), (cx,b), (x,cy), (cx,y)]
        return min(_segment_distance(p,a,b) for a,b in pairwise(polygon))
    if kind == "terminate":
        offset = .56*radius
        return min(_segment_distance(p,(cx-offset,cy-sign*offset),(cx+offset,cy+sign*offset)) for sign in (-1,1))
    if kind in ("fork", "join"):
        x, y, r, b = rect(bar_bounds(bounds))
        cx, cy = (x+r)/2, (y+b)/2
        w, h, rounded = r-x, b-y, 0
    elif kind in ("state", "composite"):
        rounded = corner_radius(bounds, kind == "composite")
    else:
        return abs(math.hypot(p[0]-cx,p[1]-cy) - radius*(.96 if kind == "final" else 1))
    dx = abs(p[0]-cx) - (w/2-rounded)
    dy = abs(p[1]-cy) - (h/2-rounded)
    return abs(math.hypot(max(0,dx),max(0,dy)) + min(max(dx,dy),0) - rounded)


def _cross(a, b):
    return a[0]*b[1] - a[1]*b[0]


def _contact(a, b, c, d):
    """Return an intersection point and shared length for arbitrary straight segments."""
    r, s = (b[0]-a[0],b[1]-a[1]), (d[0]-c[0],d[1]-c[1])
    offset = c[0]-a[0],c[1]-a[1]
    determinant = _cross(r,s)
    if abs(determinant) > EPSILON:
        x, y = _cross(offset,s)/determinant, _cross(offset,r)/determinant
        if -EPSILON <= x <= 1+EPSILON and -EPSILON <= y <= 1+EPSILON:
            return (a[0]+x*r[0],a[1]+x*r[1]), 0.0
        return None, 0.0
    if abs(_cross(offset,r)) > EPSILON:
        return None, 0.0
    axis = 0 if abs(r[0]) >= abs(r[1]) else 1
    if not r[axis]:
        return None, 0.0
    common = max(0, min(max(a[axis],b[axis]),max(c[axis],d[axis])) -
                 max(min(a[axis],b[axis]),min(c[axis],d[axis])))
    return None, common * math.hypot(*r) / abs(r[axis])


def _crosses_interior(a, b, bounds):
    """Clip against the open interior of a node rectangle."""
    x, y, r, t = rect(bounds)
    lo, hi = 0.0, 1.0
    for axis, (left, right) in enumerate(((x+EPSILON,r-EPSILON),(y+EPSILON,t-EPSILON))):
        delta = b[axis]-a[axis]
        if not delta:
            if not left < a[axis] < right:
                return False
            continue
        interval = sorted(((left-a[axis])/delta,(right-a[axis])/delta))
        lo, hi = max(lo, interval[0]), min(hi, interval[1])
        if lo >= hi:
            return False
    return True


def evaluate(model, layout, *, original_model=None, execution_ms=None):
    """Return metrics; contact at a shared logical vertex is excluded."""
    vertices, parents, region_owners, transitions = model_index(model)
    preservation = (
        (original_model is None or model == original_model) and model["id"] == layout["modelId"]
        and model["schemaVersion"] == layout["schemaVersion"]
        and set(vertices) == set(layout["nodes"]) and set(region_owners) == set(layout["regions"])
        and set(transitions) == set(layout["edges"])
        and all(edge["sourceId"] in vertices and edge["targetId"] in vertices for edge in transitions.values())
    )
    node_boxes = {i: part["bounds"] for i, part in layout["nodes"].items() if i in vertices}
    node_overlaps = sum(
        overlap(node_boxes[a], node_boxes[b])
        for a,b in combinations(node_boxes, 2) if a not in parents[b] and b not in parents[a]
    )
    labels = []
    dividers = [stroke_box(a,b) for part in layout["regions"].values()
                for a,b in part.get("separatorSegments", ())]
    edge_label_collisions = 0
    for key in ("nodes", "regions", "edges"):
        for identifier, part in layout[key].items():
            if "labelBounds" not in part:
                continue
            if key == "nodes" and identifier in parents:
                legal = {identifier, *parents[identifier]}
            elif key == "regions" and identifier in region_owners:
                legal = set(region_owners[identifier])
            elif key == "edges" and identifier in transitions:
                edge = transitions[identifier]
                legal = set(parents[edge["sourceId"]]) | set(parents[edge["targetId"]])
                borders = [border for owner in legal if owner in node_boxes
                           for border in outline_boxes(node_boxes[owner])]
                edge_label_collisions += sum(overlap(part["labelBounds"], box) for box in (*dividers, *borders))
            else:
                continue
            labels.append((part["labelBounds"], legal))
    label_collisions = edge_label_collisions + sum(overlap(a,b) for (a,_),(b,_) in combinations(labels,2))
    label_collisions += sum(overlap(label, bounds) for label, legal in labels
                            for node, bounds in node_boxes.items() if node not in legal)
    paths, edge_node, anchors, bends, length = {}, 0, 0, 0, 0.0
    for identifier, edge in transitions.items():
        if identifier not in layout["edges"] or not all(edge[k] in node_boxes for k in ("sourceId", "targetId")):
            continue
        path = []  # retain repeated nonconsecutive points in loops
        for point in layout["edges"][identifier]["points"]:
            candidate = point["x"], point["y"]
            if not path or candidate != path[-1]:
                path.append(candidate)
        if not path:
            continue
        paths[identifier] = path
        start, end = edge["sourceId"], edge["targetId"]
        anchors += int(anchor_gap(vertices[start], node_boxes[start], path[0]) > .05)
        anchors += int(anchor_gap(vertices[end], node_boxes[end], path[-1]) > .05)
        segments = list(pairwise(path))
        length += sum(math.dist(a,b) for a,b in segments)
        bends += sum(abs(_cross((b[0]-a[0],b[1]-a[1]),(c[0]-b[0],c[1]-b[1]))) > EPSILON
                     for (a,b),(_,c) in pairwise(segments))
        legal = {start, end, *parents[start], *parents[end]}
        edge_node += sum(any(_crosses_interior(a,b,bounds) for a,b in segments)
                         for node,bounds in node_boxes.items() if node not in legal)
    crossings, shared_length = 0, 0.0
    for left, right in combinations(paths, 2):
        p, q = paths[left], paths[right]
        le, re = transitions[left], transitions[right]
        endpoints = ((p[0],le["sourceId"]),(p[-1],le["targetId"]))
        other = ((q[0],re["sourceId"]),(q[-1],re["targetId"]))
        allowed = {pos for pos,node in endpoints for pos2,node2 in other if pos == pos2 and node == node2}
        touched = set()
        for a,b in pairwise(p):
            for c,d in pairwise(q):
                contact, shared = _contact(a,b,c,d)
                if contact is not None and contact not in allowed:
                    # Ignore any endpoint touching exactly the other path's endpoint only.
                    if not (contact in (p[0],p[-1]) and contact in (q[0],q[-1])):
                        touched.add(tuple(round(coordinate,7) for coordinate in contact))
                shared_length += shared
        crossings += len(touched)
    viewport = layout["viewport"]
    return {
        "node_overlaps": node_overlaps, "label_collisions": label_collisions, "edge_crossings": crossings,
        "edge_node_intersections": edge_node, "edge_overlap_length": round(shared_length,3),
        "disconnected_anchors": anchors, "edge_bends": bends, "total_edge_length": round(length,3),
        "diagram_area": round(viewport["width"]*viewport["height"],3), "execution_ms": execution_ms,
        "semantic_preservation": preservation,
    }
