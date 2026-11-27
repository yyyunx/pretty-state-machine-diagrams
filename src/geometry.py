"""Geometry and text measurements shared by SVG, layout and quality checks."""

import math
import textwrap
import unicodedata

SIDES = ("left", "right", "top", "bottom")
NORMALS = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}
FONT = "Inter, Segoe UI, Noto Sans TC, sans-serif"


def box(x, y, width, height):
    return dict(x=x, y=y, width=width, height=height)


def point(x, y):
    return dict(x=x, y=y)


def rect(bounds):
    x, y = bounds["x"], bounds["y"]
    return x, y, x + bounds["width"], y + bounds["height"]


def bar_bounds(bounds):
    x, y, r, b = rect(bounds)
    w, h = r - x, b - y
    if w >= h:
        thickness = min(h, max(4, h * .24))
        return box(x, (y + b - thickness) / 2, w, thickness)
    thickness = min(w, max(4, w * .24))
    return box((x + r - thickness) / 2, y, thickness, h)


def corner_radius(bounds, composite=False):
    return min(10 if composite else 9, bounds["width"] / 2, bounds["height"] / 2)


def symbol(vertex):
    return vertex.get("pseudostateKind", vertex["kind"])


def anchor(vertex, bounds, side, fraction=.5):
    """Intersection of an axis-aligned approach with the drawn outline."""
    kind = symbol(vertex)
    x, y, r, b = rect(bounds)
    w, h = r - x, b - y
    cx, cy = (x + r) / 2, (y + b) / 2
    horizontal = side in ("left", "right")
    direction = -1 if side in ("left", "top") else 1
    if kind in ("fork", "join"):
        bx, by, br, bb = rect(bar_bounds(bounds))
        return ((bx if direction < 0 else br), cy) if horizontal else (cx, by if direction < 0 else bb)
    if kind == "terminate":
        return cx, cy  # the diagonals meet at the center
    if kind in ("state", "composite"):
        radius = corner_radius(bounds, kind == "composite")
        minor = h if horizontal else w
        offset = min(minor / 2, abs(fraction - .5) * minor)
        rounded = max(0, offset - (minor / 2 - radius))
        trim = radius - math.sqrt(max(0, radius * radius - rounded * rounded))
        if horizontal:
            return (x + trim if direction < 0 else r - trim), y + fraction * h
        return x + fraction * w, (y + trim if direction < 0 else b - trim)
    if kind == "choice":
        if horizontal:
            return cx + direction * w * (.5 - abs(fraction - .5)), y + fraction * h
        return x + fraction * w, cy + direction * h * (.5 - abs(fraction - .5))
    radius = min(w, h) * (.48 if kind == "final" else .5)
    # Clamp to the drawn circle when a fixture provides a non-square box.
    if horizontal:
        yy = cy + (fraction - .5) * 2 * radius
        return cx + direction * math.sqrt(max(0, radius**2 - (yy-cy)**2)), yy
    xx = cx + (fraction - .5) * 2 * radius
    return xx, cy + direction * math.sqrt(max(0, radius**2 - (xx-cx)**2))


def text_lines(value, limit=68):
    wrapper = textwrap.TextWrapper(width=limit, drop_whitespace=False,
                                   replace_whitespace=False, break_on_hyphens=False)
    return [piece for line in value.split("\n") for piece in (wrapper.wrap(line) or [""])]


def text_width(text, size=12):
    return sum(size if unicodedata.east_asian_width(c) in "WF" else size * .62
               for c in text if not unicodedata.combining(c))


def behavior_lines(vertex):
    behaviors = vertex.get("behaviors", {})
    lines = []
    for key, (prefix, suffix) in {
        "entry": ("entry / ", ""), "do": ("do / ", ""), "exit": ("exit / ", ""),
        "defer": ("defer ", ""), "invariant": ("{ ", " }"),
    }.items():
        if key not in behaviors:
            continue
        value = behaviors[key]
        for index, item in enumerate(value if isinstance(value, list) else [value]):
            lines.extend(text_lines((prefix if index == 0 else "  ") + item + suffix))
    return lines


def transition_text(edge):
    if "sourceText" in edge:
        return edge["sourceText"]
    guard = f'[{edge["guard"]}]' if "guard" in edge else ""
    effect = f'/ {edge["effect"]}' if "effect" in edge else ""
    return " ".join(part for part in (", ".join(edge.get("triggers", [])), guard, effect) if part)
