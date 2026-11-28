"""SVG renderer for the Group F SMD/Layout draft contract.

The renderer is deliberately semantic-passive: names and behavior text come only
from the SMD model; coordinates come only from the layout document.
"""
from __future__ import annotations

import html
import json
import math
from numbers import Real
from pathlib import Path
from typing import Any

from src.geometry import bar_bounds, behavior_lines, corner_radius, text_lines, text_width, transition_text


class RenderError(ValueError):
    """Raised when an SMD model and its layout cannot be rendered safely."""


def _esc(value: Any) -> str:
    value = str(value)
    if any(not (c in "\t\n\r" or 32 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD
                or 0x10000 <= ord(c) <= 0x10FFFF) for c in value):
        raise RenderError("Text contains a character that cannot be represented in XML 1.0.")
    return html.escape(value, quote=True)


def _finite(value):
    return isinstance(value, Real) and not isinstance(value, bool) and abs(value) <= 1e9 and math.isfinite(value)


def _box(value: dict, context: str) -> tuple[float, float, float, float]:
    if not isinstance(value, dict) or not all(_finite(value.get(k)) for k in ("x", "y", "width", "height")):
        raise RenderError(f"{context}: expected finite numeric x, y, width and height")
    x, y, w, h = (float(value[k]) for k in ("x", "y", "width", "height"))
    if w <= 0 or h <= 0:
        raise RenderError(f"{context}: width and height must be positive")
    return x, y, w, h


def _point(value, context):
    if not isinstance(value, dict) or not all(_finite(value.get(key)) for key in ("x", "y")):
        raise RenderError(f"{context}: expected a finite numeric x and y")


def _index_model(model: dict) -> tuple[dict, dict, dict]:
    vertices: dict[str, dict] = {}
    regions: dict[str, dict] = {}
    transitions: dict[str, dict] = {}
    seen: set[str] = set()

    def unique(item_id: str, kind: str) -> None:
        if not isinstance(item_id, str) or not item_id or any(c.isspace() for c in item_id):
            raise RenderError(f"{kind} has an invalid internal id")
        if item_id in seen:
            raise RenderError(f"duplicate model id: {item_id}")
        seen.add(item_id)

    def visit_region(region: dict) -> None:
        unique(region.get("id"), "region")
        regions[region["id"]] = region
        for vertex in region.get("vertices", []):
            unique(vertex.get("id"), "vertex")
            vertices[vertex["id"]] = vertex
            if vertex.get("kind") == "composite":
                for child in vertex.get("regions", []):
                    visit_region(child)
        for edge in region.get("transitions", []):
            unique(edge.get("id"), "transition")
            transitions[edge["id"]] = edge

    if not isinstance(model, dict) or model.get("schemaVersion") != "0.1.0-draft":
        raise RenderError("unsupported or missing SMD schemaVersion")
    unique(model.get("id"), "model")
    for region in model.get("regions", []):
        visit_region(region)
    for edge in transitions.values():
        if edge.get("sourceId") not in vertices or edge.get("targetId") not in vertices:
            raise RenderError(f"transition {edge.get('id')!r} has a dangling endpoint")
    return vertices, regions, transitions


def validate_pair(model: dict, layout: dict) -> None:
    vertices, regions, transitions = _index_model(model)
    if not isinstance(layout, dict) or layout.get("schemaVersion") != model.get("schemaVersion"):
        raise RenderError("model and layout schemaVersion do not match")
    if layout.get("modelId") != model.get("id"):
        raise RenderError("layout.modelId does not match model.id")
    _box(layout.get("viewport"), "layout.viewport")
    expected = (
        ("nodes", set(vertices)),
        ("regions", set(regions)),
        ("edges", set(transitions)),
    )
    for key, ids in expected:
        if not isinstance(layout.get(key), dict):
            raise RenderError(f"layout.{key}: expected a placement object")
        actual = set(layout[key])
        missing, extra = ids - actual, actual - ids
        if missing or extra:
            details = []
            if missing:
                details.append("missing " + ", ".join(sorted(missing)))
            if extra:
                details.append("unknown " + ", ".join(sorted(extra)))
            raise RenderError(f"layout.{key}: " + "; ".join(details))
    for key, entries in (("nodes", layout["nodes"]), ("regions", layout["regions"])):
        for item_id, placement in entries.items():
            if not isinstance(placement, dict):
                raise RenderError(f"layout.{key}.{item_id}: expected a placement object")
            _box(placement.get("bounds"), f"layout.{key}.{item_id}.bounds")
            if key == "regions" and "separatorSegments" in placement:
                segments = placement["separatorSegments"]
                if not isinstance(segments, list):
                    raise RenderError("Region separatorSegments must be an array")
                for segment in segments:
                    if not isinstance(segment, list) or len(segment) != 2:
                        raise RenderError("Each region separator needs two points")
                    for point in segment:
                        _point(point, f"layout.regions.{item_id}.separatorSegments")
            if "labelBounds" in placement:
                _box(placement["labelBounds"], f"layout.{key}.{item_id}.labelBounds")
    for edge_id, placement in layout["edges"].items():
        if not isinstance(placement, dict):
            raise RenderError(f"layout.edges.{edge_id}: expected a placement object")
        points = placement.get("points")
        if not isinstance(points, list) or len(points) < 2:
            raise RenderError(f"layout.edges.{edge_id}.points must contain at least two points")
        for point in points:
            _point(point, f"layout.edges.{edge_id}.points")
        if "labelBounds" in placement:
            _box(placement["labelBounds"], f"layout.edges.{edge_id}.labelBounds")


class _SVG:
    def __init__(self, model: dict, layout: dict):
        self.model, self.layout = model, layout
        self.vertices, self.regions, self.transitions = _index_model(model)
        self.out: list[str] = []

    def add(self, value: str) -> None:
        self.out.append(value)

    def rect(self, x: float, y: float, w: float, h: float, *, rx: float = 0,
             fill: str = "white", stroke: str = "#20252b", sw: float = 1.5,
             dash: str | None = None) -> None:
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx:g}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:g}"{d}/>')

    def line(self, x1: float, y1: float, x2: float, y2: float, *,
             stroke: str = "#303840", sw: float = 1.4, dash: str | None = None) -> None:
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="{stroke}" stroke-width="{sw:g}"{d}/>')

    def text(self, x: float, y: float, value: str, *, size: float = 12,
             anchor: str = "middle", weight: str = "normal", color: str = "#20252b") -> None:
        self.add(f'<text x="{x:g}" y="{y:g}" text-anchor="{anchor}" font-family="Inter,Segoe UI,Noto Sans TC,sans-serif" font-size="{size:g}" font-weight="{weight}" fill="{color}">{_esc(value)}</text>')

    def multiline(self, x, y, lines, *, size=11, anchor="middle", line_height=14):
        self.add(f'<text xml:space="preserve" x="{x:g}" y="{y:g}" text-anchor="{anchor}" font-family="Inter,Segoe UI,Noto Sans TC,sans-serif" font-size="{size:g}" fill="#303840">')
        for index, line in enumerate(lines):
            self.add(f'<tspan x="{x:g}" dy="{0 if index == 0 else line_height:g}">{_esc(line)}</tspan>')
        self.add("</text>")

    def composite_backgrounds(self):
        # The model index is pre-order, so a parent fill always precedes its children.
        for vertex_id, vertex in self.vertices.items():
            if vertex["kind"] == "composite":
                bounds = self.layout["nodes"][vertex_id]["bounds"]
                self.rect(*_box(bounds, f"node {vertex_id}"), rx=corner_radius(bounds, True))

    def region_lines(self):
        for region_id in self.regions:
            for a, b in self.layout["regions"][region_id].get("separatorSegments", []):
                self.line(a["x"], a["y"], b["x"], b["y"], stroke="#68727d", sw=1.2, dash="6 5")

    def region_labels(self):
        for region_id, region in self.regions.items():
            name = region.get("displayName")
            if not name:
                continue
            placement = self.layout["regions"][region_id]
            lb = placement.get("labelBounds")
            if lb:
                x, y, w, h = _box(lb, f"region {region_id} label")
            else:
                rx, ry, rw, _ = _box(placement["bounds"], f"region {region_id}.bounds")
                w, h = max(36, text_width(name, 11) + 12), 18
                x, y = rx + (rw - w)/2, ry - h/2
            self.rect(x, y, w, h, fill="white", stroke="none", sw=0)
            self.text(x + w/2, y + h*.72, name, size=11, weight="600")

    def edge_paths(self):
        for edge_id in self.transitions:
            points = self.layout["edges"][edge_id]["points"]
            coords = " ".join(f'{float(p["x"]):g},{float(p["y"]):g}' for p in points)
            self.add(f'<polyline data-edge-id="{_esc(edge_id)}" tabindex="0" points="{coords}" fill="none" stroke="#303840" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#arrow)"/>')

    def edge_labels(self):
        for edge_id, edge in self.transitions.items():
            label = transition_text(edge)
            if not label:
                continue
            placement = self.layout["edges"][edge_id]
            lines = text_lines(label)
            if "labelBounds" in placement:
                x, y, w, h = _box(placement["labelBounds"], f"edge {edge_id} label")
                h = max(h, 12 * len(lines) + 6)
            else:
                mid = placement["points"][len(placement["points"]) // 2]
                w, h = max(20, max(text_width(line, 10.5) for line in lines) + 8), 12 * len(lines) + 6
                x, y = mid["x"] - w/2, mid["y"] - h - 4
            self.add(f'<g data-edge-id="{_esc(edge_id)}">')
            self.rect(x, y, w, h, rx=3, fill="white", stroke="none", sw=0)
            self.multiline(x + w/2, y + 12, lines, size=10.5, line_height=12)
            self.add("</g>")

    def node_symbols(self):
        for vertex_id, vertex in self.vertices.items():
            bounds = self.layout["nodes"][vertex_id]["bounds"]
            x, y, w, h = _box(bounds, f"node {vertex_id}")
            cx, cy = x + w/2, y + h/2
            kind = vertex.get("pseudostateKind", vertex["kind"])
            self.add(f'<g data-node-id="{_esc(vertex_id)}" data-kind="{_esc(kind)}" tabindex="0">')
            if kind == "state":
                self.rect(x, y, w, h, rx=corner_radius(bounds))
            elif kind == "choice":
                self.add(f'<path d="M {cx:g} {y:g} L {x+w:g} {cy:g} L {cx:g} {y+h:g} L {x:g} {cy:g} Z" fill="white" stroke="#20252b" stroke-width="1.5"/>')
            elif kind in ("fork", "join"):
                self.rect(*_box(bar_bounds(bounds), f"{kind} bar"), fill="#20252b", sw=0)
            elif kind != "composite":
                radius = min(w,h)/2
                if kind in ("initial", "junction"):
                    self.circle(cx, cy, radius, "#20252b")
                elif kind == "final":
                    self.circle(cx, cy, radius * .96, "white")
                    self.circle(cx, cy, radius * .62, "#20252b")
                elif kind != "terminate":
                    self.circle(cx, cy, radius, "white")
                if kind in ("exitPoint", "terminate"):
                    offset = .56 * radius
                    self.line(cx-offset, cy-offset, cx+offset, cy+offset, sw=1.8)
                    self.line(cx+offset, cy-offset, cx-offset, cy+offset, sw=1.8)
                if kind in ("shallowHistory", "deepHistory"):
                    self.text(cx, cy + 4, "H" if kind == "shallowHistory" else "H*", size=11, weight="600")
            if kind == "composite":
                # The fill is on the bottom layer. A transparent outline is selectable.
                self.rect(x, y, w, h, rx=corner_radius(bounds, True), fill="none", stroke="transparent", sw=6)
            self.add("</g>")

    def circle(self, x, y, radius, fill):
        self.add(f'<circle cx="{x:g}" cy="{y:g}" r="{radius:g}" fill="{fill}" stroke="#20252b" stroke-width="1.5"/>')

    def node_labels(self):
        for vertex_id, vertex in self.vertices.items():
            placement = self.layout["nodes"][vertex_id]
            x, y, w, h = _box(placement["bounds"], f"node {vertex_id}")
            kind, name = vertex["kind"], vertex.get("displayName")
            lines = behavior_lines(vertex)
            if not name and not lines:
                continue
            self.add(f'<g data-node-label-id="{_esc(vertex_id)}">')
            if name:
                lb = placement.get("labelBounds")
                if lb:
                    lx, ly, lw, lh = _box(lb, f"node {vertex_id} label")
                elif kind == "composite":
                    lw, lh = max(42, text_width(name) + 14), 20
                    lx, ly = x + (w-lw)/2, y-lh/2
                elif kind in ("pseudostate", "final"):
                    lw, lh = max(20, text_width(name) + 6), 18
                    lx, ly = x + (w-lw)/2, y+h+3
                else:
                    lx, ly, lw, lh = x, y+4, w, 20
                if kind in ("composite", "pseudostate", "final"):
                    self.rect(lx, ly, lw, lh, fill="white", stroke="none", sw=0)
                self.multiline(lx+lw/2, ly+13, text_lines(name), size=12)
            if lines:
                heading = 28 + max(0, len(text_lines(name)) - 1) * 14 if name else 8
                if kind == "composite":
                    heading = 17
                divider = y + heading
                self.line(x+1, divider, x+w-1, divider, stroke="#9aa2aa", sw=1)
                for index, line in enumerate(lines):
                    self.text(x+8, divider+14+index*13, line, size=9.5, anchor="start")
            self.add("</g>")

    def build(self) -> str:
        validate_pair(self.model, self.layout)
        vx, vy, vw, vh = _box(self.layout["viewport"], "layout.viewport")
        self.add('<?xml version="1.0" encoding="UTF-8"?>')
        self.add(f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="UML State Machine Diagram" viewBox="{vx:g} {vy:g} {vw:g} {vh:g}" width="{vw:g}" height="{vh:g}">')
        self.add('<title>UML State Machine Diagram</title><desc>Generated from an SMD model and layout data.</desc>')
        self.add('<defs><marker id="arrow" markerWidth="9" markerHeight="7" refX="9" refY="3.5" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L9,3.5 L0,7 Z" fill="#303840"/></marker></defs>')
        self.add('<rect x="0" y="0" width="100%" height="100%" fill="white"/>')
        for name, draw in (
            ("containers", self.composite_backgrounds),
            ("regions", self.region_lines),
            ("edges", self.edge_paths),
            ("symbols", self.node_symbols),
            ("node-labels", self.node_labels),
            ("region-labels", self.region_labels),
            ("edge-labels", self.edge_labels),
        ):
            self.add(f'<g data-layer="{name}">')
            draw()
            self.add("</g>")
        self.add("</svg>")
        return "\n".join(self.out)


def render(model: dict, layout: dict) -> str:
    """Render a complete, standalone SVG string from a paired model and layout."""
    return _SVG(model, layout).build()


def render_files(model_path: str | Path, layout_path: str | Path, output_path: str | Path) -> Path:
    """Render JSON files to an SVG file and return its path."""
    model = json.loads(Path(model_path).read_text(encoding="utf-8"))
    layout = json.loads(Path(layout_path).read_text(encoding="utf-8"))
    svg = render(model, layout)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(svg, encoding="utf-8")
    return destination
