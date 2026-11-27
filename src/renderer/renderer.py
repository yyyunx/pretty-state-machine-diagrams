"""SVG renderer for the Group F SMD/Layout draft contract.

The renderer is deliberately semantic-passive: names and behavior text come only
from the SMD model; coordinates come only from the layout document.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


class RenderError(ValueError):
    """Raised when an SMD model and its layout cannot be rendered safely."""


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _box(value: dict, context: str) -> tuple[float, float, float, float]:
    if not isinstance(value, dict):
        raise RenderError(f"{context}: expected a bounds object")
    try:
        x, y = float(value["x"]), float(value["y"])
        w, h = float(value["width"]), float(value["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RenderError(f"{context}: bounds require numeric x, y, width and height") from exc
    if w <= 0 or h <= 0:
        raise RenderError(f"{context}: width and height must be positive")
    return x, y, w, h


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
        actual = set(layout.get(key, {}))
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
            _box(placement.get("bounds"), f"layout.{key}.{item_id}.bounds")
            if "labelBounds" in placement:
                _box(placement["labelBounds"], f"layout.{key}.{item_id}.labelBounds")
    for edge_id, placement in layout["edges"].items():
        points = placement.get("points")
        if not isinstance(points, list) or len(points) < 2:
            raise RenderError(f"layout.edges.{edge_id}.points must contain at least two points")
        for point in points:
            if not isinstance(point, dict) or not isinstance(point.get("x"), (int, float)) or not isinstance(point.get("y"), (int, float)):
                raise RenderError(f"layout.edges.{edge_id} contains an invalid point")
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

    def multiline(self, x: float, y: float, width: float, value: str, *,
                  size: float = 11, anchor: str = "middle", line_height: float = 14) -> None:
        # Preserve the original text while allowing explicit newlines.
        lines = str(value).splitlines() or [""]
        self.add(f'<text x="{x:g}" y="{y:g}" text-anchor="{anchor}" font-family="Inter,Segoe UI,Noto Sans TC,sans-serif" font-size="{size:g}" fill="#303840">')
        for i, line in enumerate(lines):
            dy = 0 if i == 0 else line_height
            self.add(f'<tspan x="{x:g}" dy="{dy:g}">{_esc(line)}</tspan>')
        self.add('</text>')

    def render_regions(self) -> None:
        # Region divider geometry is supplied by Layout. No label is invented.
        for region_id, region in self.regions.items():
            placement = self.layout["regions"][region_id]
            segments = placement.get("separatorSegments", [])
            for segment in segments:
                a, b = segment
                self.line(a["x"], a["y"], b["x"], b["y"], stroke="#68727d", sw=1.2, dash="6 5")
            name = region.get("displayName")
            if name:
                lb = placement.get("labelBounds")
                if lb:
                    x, y, w, h = _box(lb, f"region {region_id} label")
                else:
                    rx, ry, rw, rh = _box(placement["bounds"], f"region {region_id}.bounds")
                    w, h = max(36, len(name) * 7 + 12), 18
                    x, y = rx + (rw - w) / 2, ry - h / 2
                self.rect(x, y, w, h, fill="white", stroke="none", sw=0)
                self.text(x + w / 2, y + h * .72, name, size=11, weight="600")

    def _transition_label(self, edge: dict) -> str:
        # sourceText is the most faithful representation when supplied.
        if edge.get("sourceText"):
            return edge["sourceText"]
        trigger = ", ".join(edge.get("triggers", []))
        guard = f'[{edge["guard"]}]' if edge.get("guard") else ""
        effect = f'/ {edge["effect"]}' if edge.get("effect") else ""
        return " ".join(part for part in (trigger, guard, effect) if part)

    def render_edges(self) -> None:
        for edge_id, edge in self.transitions.items():
            placement = self.layout["edges"][edge_id]
            points = placement["points"]
            coords = " ".join(f'{float(p["x"]):g},{float(p["y"]):g}' for p in points)
            self.add(f'<polyline points="{coords}" fill="none" stroke="#303840" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#arrow)"/>')
            label = self._transition_label(edge)
            if label:
                lb = placement.get("labelBounds")
                if lb:
                    x, y, w, h = _box(lb, f"edge {edge_id} label")
                    cx, cy = x + w / 2, y + h / 2
                    self.rect(x, y, w, h, rx=3, fill="white", stroke="none", sw=0)
                    self.multiline(cx, cy - 2, w, label, size=10.5, line_height=12)
                else:
                    mid = points[len(points) // 2]
                    self.multiline(float(mid["x"]), float(mid["y"]) - 8, 240, label, size=10.5)

    def _behavior_lines(self, vertex: dict) -> list[str]:
        behaviors = vertex.get("behaviors", {})
        lines: list[str] = []
        for key in ("entry", "do", "exit", "defer", "invariant"):
            value = behaviors.get(key)
            if value is None:
                continue
            values = value if isinstance(value, list) else [value]
            prefix = {"entry": "entry / ", "do": "do / ", "exit": "exit / ",
                      "defer": "defer ", "invariant": "{ "} [key]
            suffix = " }" if key == "invariant" else ""
            for i, item in enumerate(values):
                lines.append((prefix if i == 0 else "  ") + str(item) + suffix)
        return lines

    def render_vertex(self, vertex_id: str) -> None:
        vertex = self.vertices[vertex_id]
        placement = self.layout["nodes"][vertex_id]
        x, y, w, h = _box(placement["bounds"], f"node {vertex_id}")
        kind = vertex["kind"]
        name = vertex.get("displayName")

        if kind == "pseudostate":
            subtype = vertex["pseudostateKind"]
            cx, cy = x + w / 2, y + h / 2
            if subtype == "initial":
                self.add(f'<circle cx="{cx:g}" cy="{cy:g}" r="{min(w,h)/2:g}" fill="#20252b" stroke="#20252b"/>')
            elif subtype == "choice":
                self.add(f'<path d="M {cx:g} {y:g} L {x+w:g} {cy:g} L {cx:g} {y+h:g} L {x:g} {cy:g} Z" fill="white" stroke="#20252b" stroke-width="1.5"/>')
            elif subtype == "junction":
                self.add(f'<circle cx="{cx:g}" cy="{cy:g}" r="{min(w,h)/2:g}" fill="white" stroke="#20252b" stroke-width="1.5"/>')
            elif subtype in ("fork", "join"):
                horizontal = w >= h
                if horizontal:
                    self.rect(x, cy - max(2, h * .12), w, max(4, h * .24), fill="#20252b", stroke="#20252b", sw=0)
                else:
                    self.rect(cx - max(2, w * .12), y, max(4, w * .24), h, fill="#20252b", stroke="#20252b", sw=0)
            elif subtype in ("shallowHistory", "deepHistory"):
                self.add(f'<circle cx="{cx:g}" cy="{cy:g}" r="{min(w,h)/2:g}" fill="white" stroke="#20252b" stroke-width="1.5"/>')
                self.text(cx, cy + 4, "H" if subtype == "shallowHistory" else "H*", size=11, weight="600")
            elif subtype in ("entryPoint", "exitPoint"):
                self.add(f'<circle cx="{cx:g}" cy="{cy:g}" r="{min(w,h)/2:g}" fill="white" stroke="#20252b" stroke-width="1.5"/>')
                self.text(cx, cy + 4, "E" if subtype == "entryPoint" else "X", size=10, weight="600")
            elif subtype == "terminate":
                self.add(f'<circle cx="{cx:g}" cy="{cy:g}" r="{min(w,h)/2:g}" fill="white" stroke="#20252b" stroke-width="1.5"/>')
                self.line(x+w*.28, y+h*.28, x+w*.72, y+h*.72, sw=1.8)
                self.line(x+w*.72, y+h*.28, x+w*.28, y+h*.72, sw=1.8)
            return

        if kind == "final":
            cx, cy = x + w / 2, y + h / 2
            self.add(f'<circle cx="{cx:g}" cy="{cy:g}" r="{min(w,h)*.48:g}" fill="white" stroke="#20252b" stroke-width="1.5"/>')
            self.add(f'<circle cx="{cx:g}" cy="{cy:g}" r="{min(w,h)*.31:g}" fill="#20252b"/>')
            return

        is_composite = kind == "composite"
        self.rect(x, y, w, h, rx=10 if is_composite else 9, fill="white", sw=1.5)
        behavior_lines = self._behavior_lines(vertex)
        if name:
            lb = placement.get("labelBounds")
            if lb:
                lx, ly, lw, lh = _box(lb, f"node {vertex_id} label")
                self.text(lx + lw/2, ly + lh*.72, name, size=12, weight="600")
            else:
                self.text(x+w/2, y+19, name, size=12, weight="600")
        if behavior_lines:
            divider_y = y + (28 if name else 8)
            self.line(x+1, divider_y, x+w-1, divider_y, stroke="#9aa2aa", sw=1)
            start_y = divider_y + 15
            for i, line in enumerate(behavior_lines):
                self.text(x+8, start_y+i*13, line, size=9.5, anchor="start")
        if is_composite:
            for child_region in vertex.get("regions", []):
                self.render_region_children(child_region)

    def render_region_children(self, region: dict) -> None:
        for vertex in region.get("vertices", []):
            self.render_vertex(vertex["id"])

    def render_nodes(self) -> None:
        # Model traversal order keeps parent composites before their descendants.
        # Start only at top-level regions; composite rendering recursively draws
        # descendants exactly once.
        for region in self.model.get("regions", []):
            for vertex in region.get("vertices", []):
                self.render_vertex(vertex["id"])

    def build(self) -> str:
        validate_pair(self.model, self.layout)
        vx, vy, vw, vh = _box(self.layout["viewport"], "layout.viewport")
        self.add('<?xml version="1.0" encoding="UTF-8"?>')
        self.add(f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="UML State Machine Diagram" viewBox="{vx:g} {vy:g} {vw:g} {vh:g}" width="{vw:g}" height="{vh:g}">')
        self.add('<title>UML State Machine Diagram</title><desc>Generated from an SMD model and layout data.</desc>')
        self.add('<defs><marker id="arrow" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L9,3.5 L0,7 Z" fill="#303840"/></marker></defs>')
        self.add('<rect x="0" y="0" width="100%" height="100%" fill="white"/>')
        self.render_edges()
        self.render_nodes()
        # Draw region separators after composite backgrounds and child vertices,
        # so nested white state containers cannot erase their divider lines.
        self.render_regions()
        self.add('</svg>')
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
