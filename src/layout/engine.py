"""Topology-aware layered placement with recursive UML region geometry."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise
import math

from src.geometry import behavior_lines, box, point, rect, text_lines, text_width, transition_text

from . import legacy, routing
from .topology import layers


class LayoutError(ValueError):
    pass


@dataclass(frozen=True)
class LayoutOptions:
    direction: str = "horizontal"
    node_spacing: float = 48
    layer_spacing: float = 84
    region_padding: float = 28
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


def _connection(vertex):
    return vertex.get("pseudostateKind") in ("entryPoint", "exitPoint")


def _label_size(name, size=12):
    lines = text_lines(name)
    return max(20, max(text_width(line, size) for line in lines) + 14), 14 * len(lines) + 6


class _Placement:
    def __init__(self, model, options):
        self.model, self.options = model, options
        self.horizontal = options.direction == "horizontal"
        self.nodes, self.regions, self.edges = {}, {}, {}
        self.vertices, self.ancestors, self.representatives = {}, {}, defaultdict(dict)
        self.transitions = []
        self.vertex_sizes, self.region_sizes, self.region_layers = {}, {}, {}
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
        label_w, label_h = _label_size(name) if name else (0, 0)
        lines = behavior_lines(vertex)
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
        return 34 + 13 * len(behavior_lines(vertex)) + (
            max(0, _label_size(vertex["displayName"])[1]-20) if "displayName" in vertex else 0
        )

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
        projected = [(owners.get(edge["sourceId"]), owners.get(edge["targetId"])) for edge in self.transitions]
        ranks = layers(ids, [(a, b) for a, b in projected if a in local and b in local])
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
                self.place_vertex(vertex_id, cx-vw/2, cy-vh/2, vw, vh, boundary=True)

    def place_vertex(self, vertex_id, x, y, w, h, boundary=False):
        vertex = self.vertices[vertex_id]
        name, kind = vertex.get("displayName"), vertex["kind"]
        if kind in ("pseudostate", "final"):
            glyph_w, glyph_h = self.symbol_size(vertex)
            bx, by = x + (w-glyph_w)/2, y
            placement = {"bounds": box(bx, by, glyph_w, glyph_h)}
            if name:
                lw, lh = _label_size(name)
                nx, ny = bx+(glyph_w-lw)/2, by+glyph_h+4
                if boundary and self.horizontal:
                    nx = bx-lw-7 if vertex["pseudostateKind"] == "entryPoint" else bx+glyph_w+7
                    ny = by+(glyph_h-lh)/2
                placement["labelBounds"] = box(nx, ny, lw, lh)
        else:
            placement = {"bounds": box(x, y, w, h)}
            if name:
                lw, lh = _label_size(name)
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

    def connect(self):
        used, lanes = [], defaultdict(int)
        occupied = [part["labelBounds"] for part in (*self.nodes.values(), *self.regions.values())
                    if "labelBounds" in part]
        for edge in self.transitions:
            src, dst = edge["sourceId"], edge["targetId"]
            allowed = {src, dst, *self.ancestors[src], *self.ancestors[dst]}
            obstacles = [placement["bounds"] for key, placement in self.nodes.items() if key not in allowed]
            key = tuple(sorted((src, dst)))
            lane = lanes[key]
            lanes[key] += 1
            a, b = self.nodes[src]["bounds"], self.nodes[dst]["bounds"]
            try:
                points = routing.route(
                    self.vertices[src], self.vertices[dst], a, b, obstacles,
                    clearance=self.options.edge_clearance, bend_penalty=self.options.bend_penalty,
                    crossing_penalty=self.options.crossing_penalty, lane=lane, self_loop=src == dst,
                    inward=(src in self.ancestors[dst], dst in self.ancestors[src]), used=used,
                )
            except routing.RoutingError as exc:
                raise LayoutError(f"Transition {edge['id']!r}: {exc}") from exc
            used.extend(pairwise((p["x"], p["y"]) for p in points))
            geometry = {"points": points}
            text = transition_text(edge)
            if text:
                geometry["labelBounds"] = routing.label_position(
                    points, text, [*obstacles, a, b, *occupied], self.options.label_clearance)
                occupied.append(geometry["labelBounds"])
            self.edges[edge["id"]] = geometry

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


def layout(model, options=None, *, algorithm="topology"):
    """Compute a Layout JSON object without mutating the model."""
    if algorithm == "legacy":
        return legacy.layout(model)
    if algorithm != "topology":
        raise LayoutError(f"Unknown layout algorithm {algorithm!r}")
    if options is None:
        options = LayoutOptions()
    if not isinstance(options, LayoutOptions):
        raise LayoutError("Expected LayoutOptions or None")
    return _Placement(model, options).run()
