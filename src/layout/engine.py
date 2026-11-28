"""Topology-aware layered placement with recursive UML region geometry."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise
import math

from src.geometry import SIDES, behavior_lines, box, outline_boxes, point, rect, stroke_box, text_lines, text_width, transition_text

from . import legacy, routing
from .spatial import Occupancy, SpatialIndex
from .topology import layers


class LayoutError(ValueError):
    pass


@dataclass(frozen=True)
class LayoutOptions:
    direction: str = "horizontal"
    node_spacing: float = 48
    layer_spacing: float = 64
    region_padding: float = 24
    edge_clearance: float = 8
    crossing_penalty: float = 85
    bend_penalty: float = 22
    label_clearance: float = 8

    def __post_init__(self):
        if self.direction not in ("horizontal", "vertical"):
            raise LayoutError("direction must be horizontal or vertical")
        for key, value in vars(self).items():
            low = 0 if key.endswith("penalty") else 4
            if key != "direction" and (
                type(value) not in (int, float) or not low <= value <= 500 or not math.isfinite(value)
            ):
                raise LayoutError(f"{key} must be a finite number from {low} to 500")


@dataclass(frozen=True)
class PlacementProfile:
    order: str = "mean"
    reverse_sweep: bool = False
    split_cycles: bool = False
    route_order: str = "model"
    extra_channels: bool = False
    reroutes: int = 0


def _connection(vertex):
    return vertex.get("pseudostateKind") in ("entryPoint", "exitPoint")


def _label_size(name, size=12):
    lines = text_lines(name)
    return max(20, max(text_width(line, size) for line in lines) + 14), 14 * len(lines) + 6


class _Placement:
    def __init__(self, model, options, profile=None, budget=None):
        self.model, self.options = model, options
        self.profile, self.budget = profile, budget
        self.horizontal = options.direction == "horizontal"
        self.nodes, self.regions, self.edges = {}, {}, {}
        self.vertices, self.ancestors, self.representatives = {}, {}, defaultdict(dict)
        self.transitions = []
        self.vertex_sizes, self.region_sizes, self.region_layers = {}, {}, {}
        self.names, self.behaviors, self.boundary_ports = {}, {}, {}
        self.index(model["regions"])

    def index(self, regions, containers=(), ancestor_regions=()):
        for region in regions:
            region_id = region["id"]
            self.transitions.extend(region["transitions"])
            for vertex in region["vertices"]:
                vertex_id = vertex["id"]
                self.vertices[vertex_id], self.ancestors[vertex_id] = vertex, containers
                self.representatives[region_id][vertex_id] = vertex_id
                for owner, representative in ancestor_regions:
                    self.representatives[owner][vertex_id] = representative
                self.index(vertex.get("regions", []), (*containers, vertex_id),
                           (*ancestor_regions, (region_id, vertex_id)))

    def size_vertex(self, vertex_id):
        if vertex_id in self.vertex_sizes:
            return self.vertex_sizes[vertex_id]
        vertex = self.vertices[vertex_id]
        name = vertex.get("displayName")
        label_w, label_h = self.names[vertex_id] = _label_size(name) if name else (0, 0)
        lines = self.behaviors[vertex_id] = behavior_lines(vertex)
        behavior_w = max((text_width(line, 9.5) + 20 for line in lines), default=0)
        if vertex["kind"] == "composite":
            regions = [self.size_region(child, True) for child in vertex["regions"]]
            header = self.header(vertex)
            if self.horizontal:
                result = (max(180, behavior_w, label_w+30, *(w+28 for w, _ in regions)),
                          sum(h for _, h in regions)+header+18)
            else:
                result = (max(180, behavior_w, label_w+30, sum(w for w, _ in regions)+28),
                          max(h for _, h in regions)+header+18)
        elif vertex["kind"] == "state":
            result = max(100, label_w, behavior_w), max(48, label_h+16 + (len(lines)*13+14 if lines else 0))
        else:
            symbol = self.symbol_size(vertex)
            result = max(symbol[0], label_w), symbol[1] + (label_h+6 if name else 0)
        self.vertex_sizes[vertex_id] = result
        return result

    def header(self, vertex):
        identifier = vertex["id"]
        return 34 + 13 * len(self.behaviors[identifier]) + max(0,self.names[identifier][1]-20)

    @staticmethod
    def symbol_size(vertex):
        kind = vertex.get("pseudostateKind")
        if kind in ("entryPoint", "exitPoint"):
            return 18, 18
        if kind == "junction":
            return 14, 14
        if kind in ("fork", "join"):
            return 34, 24
        return 24, 24

    def size_region(self, region, nested=False):
        region_id = region["id"]
        if region_id in self.region_sizes:
            return self.region_sizes[region_id]
        ids = [v["id"] for v in region["vertices"] if not (nested and _connection(v))]
        owners = self.representatives[region_id]
        local = set(ids)
        projected = ((owners.get(edge["sourceId"]), owners.get(edge["targetId"]))
                     for edge in self.transitions)
        profile = self.profile or PlacementProfile()
        ranks = layers(ids, ((a,b) for a,b in projected if a in local and b in local),
                       order=profile.order, reverse_sweep=profile.reverse_sweep, split_cycles=profile.split_cycles)
        extents = []
        for column in ranks:
            sizes = [self.size_vertex(node) for node in column]
            if self.horizontal:
                extents.append((max(w for w, _ in sizes), sum(h for _, h in sizes)))
            else:
                extents.append((max(h for _, h in sizes), sum(w for w, _ in sizes)))
        along = sum(a for a, _ in extents) + self.options.layer_spacing * max(0, len(extents)-1)
        across = max((amount + self.options.node_spacing * (len(column)-1)
                      for column, (_, amount) in zip(ranks, extents)), default=0)
        inner_w, inner_h = (along, across) if self.horizontal else (across, along)
        padding = self.options.region_padding
        name = region.get("displayName")
        labels = max((self.size_vertex(v["id"])[0] for v in region["vertices"]
                      if nested and _connection(v)), default=0)
        ports = max((sum(v.get("pseudostateKind") == kind for v in region["vertices"])
                     for kind in ("entryPoint", "exitPoint")), default=0)
        size = (
            max(120, inner_w + 2*padding, labels+28,
                _label_size(name, 11)[0]+36 if name else 0,
                ports*max(30, labels+7)+2*padding if nested and not self.horizontal else 0),
            max(100, inner_h + 2*padding,
                ports*32+2*padding if nested and self.horizontal else 0),
        )
        self.region_sizes[region_id], self.region_layers[region_id] = size, (ranks, extents)
        return size

    def region_decoration(self, region, x, y, w, h, divider):
        placement = {"bounds": box(x, y, w, h)}
        name = region.get("displayName")
        if name:
            lw, lh = _label_size(name, 11)
            placement["labelBounds"] = box(x+(w-lw)/2, y-lh/2, lw, lh) if self.horizontal else box(
                x-lw/2, y+(h-lh)/2, lw, lh)
        if divider or name:
            if self.horizontal:
                segments = [(x, x+w)] if not name else [(x, x+(w-lw)/2-5), (x+(w+lw)/2+5, x+w)]
                placement["separatorSegments"] = [[point(a, y), point(b, y)] for a, b in segments if b > a]
            else:
                segments = [(y, y+h)] if not name else [(y, y+(h-lh)/2-5), (y+(h+lh)/2+5, y+h)]
                placement["separatorSegments"] = [[point(x, a), point(x, b)] for a, b in segments if b > a]
        return placement

    def place_region(self, region, x, y, w, h, divider=False, parent=None):
        region_id = region["id"]
        self.regions[region_id] = self.region_decoration(region, x, y, w, h, divider)
        ranks, extents = self.region_layers[region_id]
        primary = (x if self.horizontal else y) + self.options.region_padding
        secondary = y if self.horizontal else x
        available = h if self.horizontal else w
        for column, (length, span) in zip(ranks, extents):
            spacing = self.options.node_spacing
            cursor = secondary + (available - span - spacing*(len(column)-1))/2
            for vertex_id in column:
                vw, vh = self.size_vertex(vertex_id)
                if self.horizontal:
                    self.place_vertex(vertex_id, primary+(length-vw)/2, cursor, vw, vh)
                    cursor += vh + spacing
                else:
                    self.place_vertex(vertex_id, cursor, primary+(length-vh)/2, vw, vh)
                    cursor += vw + spacing
            primary += length + self.options.layer_spacing
        if parent is None:
            return
        for kind in ("entryPoint", "exitPoint"):
            ports = [v["id"] for v in region["vertices"] if v.get("pseudostateKind") == kind]
            for index, vertex_id in enumerate(ports, start=1):
                fraction = index / (len(ports) + 1)
                px, py, pw, ph = parent
                if self.horizontal:
                    cx, cy = (px if kind == "entryPoint" else px+pw), y + h*fraction
                else:
                    cx, cy = x+w*fraction, (py if kind == "entryPoint" else py+ph)
                vw, vh = self.symbol_size(self.vertices[vertex_id])
                sides = ("left","right") if self.horizontal else ("top","bottom")
                self.boundary_ports[vertex_id] = sides if kind == "entryPoint" else sides[::-1]
                self.place_vertex(vertex_id, cx-vw/2, cy-vh/2, vw, vh, boundary=True)

    def place_vertex(self, vertex_id, x, y, w, h, boundary=False):
        vertex = self.vertices[vertex_id]
        name, kind = vertex.get("displayName"), vertex["kind"]
        if kind in ("pseudostate", "final"):
            glyph_w, glyph_h = self.symbol_size(vertex)
            bx, by = x + (w-glyph_w)/2, y
            placement = {"bounds": box(bx, by, glyph_w, glyph_h)}
            if name:
                if vertex_id not in self.names:  # boundary vertices skip rank sizing
                    self.size_vertex(vertex_id)
                lw, lh = self.names[vertex_id]
                nx, ny = bx+(glyph_w-lw)/2, by+glyph_h+4
                if boundary and self.horizontal:
                    nx = bx-lw-7 if vertex["pseudostateKind"] == "entryPoint" else bx+glyph_w+7
                    ny = by+(glyph_h-lh)/2
                elif boundary and self.profile is not None and vertex["pseudostateKind"] == "entryPoint":
                    ny = by-lh-4
                placement["labelBounds"] = box(nx, ny, lw, lh)
        else:
            placement = {"bounds": box(x, y, w, h)}
            if name:
                lw, lh = self.names[vertex_id]
                label_y = y - lh/2 if kind == "composite" else y+5
                placement["labelBounds"] = box(x+(w-lw)/2, label_y, lw, lh)
        self.nodes[vertex_id] = placement
        if kind != "composite":
            return
        children = vertex["regions"]
        split = self.header(vertex)
        if self.horizontal:
            ry = y + split
            for index, child in enumerate(children):
                _, rh = self.region_sizes[child["id"]]
                self.place_region(child, x+14, ry, w-28, rh, index>0, (x,y,w,h))
                ry += rh
        else:
            total_width = sum(self.region_sizes[child["id"]][0] for child in children)
            rx = x+(w-total_width)/2
            for index, child in enumerate(children):
                rw, _ = self.region_sizes[child["id"]]
                self.place_region(child, rx, y+split, rw, h-split-18, index>0, (x,y,w,h))
                rx += rw

    def _allowed(self, edge):
        src, dst = edge["sourceId"], edge["targetId"]
        return {src,dst,*self.ancestors[src],*self.ancestors[dst]}

    def _boundary_side(self, node, other):
        if node not in self.boundary_ports:
            return SIDES
        outside, inside = self.boundary_ports[node]
        owner = self.ancestors[node][-1]
        return (inside if owner == other or owner in self.ancestors[other] else outside,)

    def _route(self, edge, lane, used, index=None, occupancy=None):
        src, dst = edge["sourceId"], edge["targetId"]
        allowed = self._allowed(edge)
        obstacles = [] if index is not None else [
            part["bounds"] for key,part in self.nodes.items() if key not in allowed]
        try:
            return routing.route(
                self.vertices[src], self.vertices[dst], self.nodes[src]["bounds"], self.nodes[dst]["bounds"],
                obstacles, clearance=self.options.edge_clearance, bend_penalty=self.options.bend_penalty,
                crossing_penalty=self.options.crossing_penalty, lane=lane, self_loop=src==dst,
                inward=(src in self.ancestors[dst],dst in self.ancestors[src]), used=used,
                budget=self.budget,index=index,allowed=allowed,occupancy=occupancy,edge_id=edge["id"],
                boundary_sides=(self._boundary_side(src,dst),self._boundary_side(dst,src))
                if index is not None else (SIDES,SIDES),
                extra_channels=self.profile.extra_channels if self.profile is not None else False,
            )
        except routing.RoutingError as exc:
            raise LayoutError(f"Transition {edge['id']!r}: {exc}") from exc

    def _label(self, edge, points, occupied, dividers, occupancy=None):
        src, dst = edge["sourceId"], edge["targetId"]
        allowed = self._allowed(edge)
        obstacles = [part["bounds"] for key,part in self.nodes.items() if key not in allowed]
        borders = [border for parent in allowed-{src,dst}
                   for border in outline_boxes(self.nodes[parent]["bounds"])]
        headers = [box(bounds["x"],bounds["y"],bounds["width"],self.header(self.vertices[parent]))
                   for parent in allowed-{src,dst} if self.behaviors[parent]
                   for bounds in (self.nodes[parent]["bounds"],)]
        return routing.label_position(
            points, transition_text(edge),
            [*obstacles,self.nodes[src]["bounds"],self.nodes[dst]["bounds"],*occupied,*dividers,*borders,*headers],
            self.options.label_clearance,occupancy=occupancy)

    @staticmethod
    def _segments(points):
        return pairwise((p["x"],p["y"]) for p in points)

    def _rip_up(self, occupancy, index, lanes, paths):
        def score(identifier, points):
            crossings, shared, length = 0, 0.0, 0.0
            for a,b in self._segments(points):
                length += routing.manhattan(a,b)
                for c,d in occupancy.nearby(a,b,ignore=identifier):
                    cross, overlap = routing.segment_conflict(a,b,c,d)
                    crossings += cross
                    shared += overlap
            return crossings, round(shared,7), length + self.options.bend_penalty * (len(points)-2)

        congested = sorted(self.transitions, key=lambda edge: score(edge["id"],paths[edge["id"]]), reverse=True)
        for edge in congested[:self.profile.reroutes]:
            identifier = edge["id"]
            before = score(identifier, paths[identifier])
            if before[:2] == (0,0):
                break
            for lane in (lanes[identifier]+1, lanes[identifier]+3):
                try:
                    trial = self._route(edge,lane,(),index,occupancy)
                except LayoutError:
                    continue
                after = score(identifier, trial)
                if after < before:
                    paths[identifier], before = trial, after
                    occupancy.add(identifier,self._segments(trial))

    def connect(self):
        used, paths, lanes, counts = [], {}, {}, defaultdict(int)
        advanced = self.profile is not None
        index, occupancy = (SpatialIndex(),Occupancy()) if advanced else (None,None)
        if advanced:
            for key,part in self.nodes.items():
                bounds = rect(part["bounds"])
                index.add(bounds,(key,bounds))
        for edge in self.transitions:
            key = tuple(sorted((edge["sourceId"],edge["targetId"])))
            lanes[edge["id"]] = counts[key]
            counts[key] += 1
        order = self.transitions
        if advanced and self.profile.route_order != "model":
            def length(edge):
                a,b = (self.nodes[edge[key]]["bounds"] for key in ("sourceId","targetId"))
                return abs(a["x"]-b["x"])+abs(a["y"]-b["y"])
            order = sorted(order,key=length,reverse=self.profile.route_order=="long")
        for edge in order:
            identifier = edge["id"]
            points = paths[identifier] = self._route(edge,lanes[identifier],used,index,occupancy)
            if advanced:
                occupancy.add(identifier,self._segments(points))
            else:
                used.extend(self._segments(points))
        if advanced and self.profile.reroutes:
            self._rip_up(occupancy,index,lanes,paths)
        occupied = [part["labelBounds"] for part in (*self.nodes.values(),*self.regions.values())
                    if "labelBounds" in part]
        dividers = [stroke_box(a,b) for part in self.regions.values()
                    for a,b in part.get("separatorSegments", ())]
        for edge in self.transitions:
            identifier = edge["id"]
            geometry = {"points": paths[identifier]}
            if transition_text(edge):
                geometry["labelBounds"] = self._label(edge,paths[identifier],occupied,dividers,occupancy)
                occupied.append(geometry["labelBounds"])
            self.edges[identifier] = geometry

    def run(self):
        roots = self.model["regions"]
        sizes = [self.size_region(region) for region in roots]
        x, y = 36, 36
        for index, (region, (w, h)) in enumerate(zip(roots, sizes, strict=True)):
            width = max(value[0] for value in sizes) if self.horizontal else w
            height = max(value[1] for value in sizes) if not self.horizontal else h
            self.place_region(region, x, y, width, height, index>0)
            if self.horizontal:
                y += height
            else:
                x += width
        self.connect()
        extent = [rect(part[key]) for part in (*self.nodes.values(), *self.regions.values(), *self.edges.values())
                  for key in ("bounds", "labelBounds") if key in part]
        extent.extend((p["x"],p["y"],p["x"],p["y"]) for edge in self.edges.values() for p in edge["points"])
        left, top = min(a for a, _, _, _ in extent)-20, min(a for _, a, _, _ in extent)-20
        right, bottom = max(a for _, _, a, _ in extent)+20, max(a for _, _, _, a in extent)+20
        return dict(schemaVersion=self.model["schemaVersion"], modelId=self.model["id"],
                    viewport=box(left, top, right-left, bottom-top), nodes=self.nodes,
                    regions=self.regions, edges=self.edges)


def layout(model, options=None, *, algorithm="topology", mode="balanced", timeout=None, allow_rotate=False):
    """Compute a Layout JSON object without mutating the model."""
    if algorithm == "legacy":
        return legacy.layout(model)
    if algorithm not in ("topology","advanced","hybrid"):
        raise LayoutError(f"Unknown layout algorithm {algorithm!r}")
    if options is None:
        options = LayoutOptions()
    if not isinstance(options, LayoutOptions):
        raise LayoutError("Expected LayoutOptions or None")
    if algorithm == "advanced":
        from .advanced import optimize
        return optimize(model, options, mode=mode, timeout=timeout, allow_rotate=allow_rotate).layout
    if algorithm == "hybrid":
        from .hybrid import optimize_hybrid
        return optimize_hybrid(model,options,mode=mode,timeout=timeout,allow_rotate=allow_rotate).layout
    if timeout is not None:
        from .budget import SearchBudget
        budget = SearchBudget(4_000_000,timeout)
        result = _Placement(model,options,budget=budget).run()
        budget.check()
        return result
    return _Placement(model, options).run()
