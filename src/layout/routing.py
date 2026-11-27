"""Shape-aware orthogonal routing with deterministic obstacle-aware fallback."""

import heapq
from itertools import pairwise

from src.geometry import NORMALS, SIDES, anchor, point, rect, text_lines, text_width

EPSILON = 1e-7


class RoutingError(ValueError):
    pass


def overlap(a, b):
    x, y, r, t = rect(a)
    u, v, s, w = rect(b)
    return x < s - EPSILON and u < r - EPSILON and y < w - EPSILON and v < t - EPSILON


def inside_box(p, bounds):
    x, y, r, b = bounds
    return x + EPSILON < p[0] < r - EPSILON and y + EPSILON < p[1] < b - EPSILON


def hits_box(a, b, bounds):
    left, top, right, bottom = bounds
    x1, y1 = a
    x2, y2 = b
    if abs(x1 - x2) <= EPSILON:
        return (left + EPSILON < x1 < right - EPSILON and
                min(y1, y2) < bottom - EPSILON and max(y1, y2) > top + EPSILON)
    if abs(y1 - y2) <= EPSILON:
        return (top + EPSILON < y1 < bottom - EPSILON and
                min(x1, x2) < right - EPSILON and max(x1, x2) > left + EPSILON)
    return False  # routing callers use axis-aligned segments


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def orientation(a, b):
    return 1 if a[0] == b[0] else 2


def segment_conflict(a, b, c, d):
    """Proper crossings and positive shared length; endpoint-only contact is free."""
    first, second = orientation(a, b), orientation(c, d)
    if first == second:
        axis = 1 if first == 1 else 0
        if abs(a[1-axis] - c[1-axis]) > EPSILON:
            return 0, 0.0
        lo = max(min(a[axis], b[axis]), min(c[axis], d[axis]))
        hi = min(max(a[axis], b[axis]), max(c[axis], d[axis]))
        return 0, max(0.0, hi - lo)
    if first != 1:
        a, b, c, d = c, d, a, b
    x, y = a[0], c[1]
    if (min(c[0], d[0]) + EPSILON < x < max(c[0], d[0]) - EPSILON and
            min(a[1], b[1]) + EPSILON < y < max(a[1], b[1]) - EPSILON):
        return 1, 0.0
    return 0, 0.0


def simplify(path):
    result = []
    for p in path:
        if result and p == result[-1]:
            continue
        if len(result) > 1:
            a, b = result[-2:]
            if ((a[0] == b[0] == p[0] and min(a[1], p[1]) <= b[1] <= max(a[1], p[1])) or
                    (a[1] == b[1] == p[1] and min(a[0], p[0]) <= b[0] <= max(a[0], p[0]))):
                result.pop()
        result.append(p)
    return result


def _grow(bounds, padding):
    x, y, r, b = bounds
    return x-padding, y-padding, r+padding, b+padding


def _ports(vertex, bounds, clearance, lane, inward):
    fractions = (.5, .34, .66, .22, .78, .42, .58)
    fraction = fractions[lane % len(fractions)]
    x, y, r, b = rect(bounds)
    for side in SIDES:
        ax, ay = anchor(vertex, bounds, side, fraction)
        dx, dy = NORMALS[side]
        if inward:
            lead = (ax - dx*clearance, ay - dy*clearance)
        else:
            lead = (x-clearance if dx < 0 else r+clearance if dx > 0 else ax,
                    y-clearance if dy < 0 else b+clearance if dy > 0 else ay)
        yield side, (ax, ay), lead


def _grid_route(start, goal, blocks, segment_cost, bend_penalty, start_axis, goal_axis):
    xs = sorted({start[0], goal[0], *(q for x, _, r, _ in blocks for q in (x, r))})
    ys = sorted({start[1], goal[1], *(q for _, y, _, b in blocks for q in (y, b))})
    if len(xs) * len(ys) > 45000:
        return None
    xi, yi = {x: i for i, x in enumerate(xs)}, {y: i for i, y in enumerate(ys)}
    initial = (xi[start[0]], yi[start[1]], start_axis)
    queue, distance, prev = [(manhattan(start, goal), 0, initial)], {initial: 0}, {}
    best, result = float("inf"), None
    while queue:
        estimate, value, state = heapq.heappop(queue)
        if estimate >= best:
            break
        if distance[state] != value:
            continue
        ix, iy, axis = state
        p = xs[ix], ys[iy]
        if p == goal:
            best = value + bend_penalty * (axis != goal_axis)
            result = state
            continue
        for jx, jy, direction in ((ix, iy-1, 1), (ix, iy+1, 1), (ix-1, iy, 2), (ix+1, iy, 2)):
            if not 0 <= jx < len(xs) or not 0 <= jy < len(ys):
                continue
            q = xs[jx], ys[jy]
            if any(hits_box(p, q, box) for box in blocks):
                continue
            next_state = jx, jy, direction
            alt = value + segment_cost(p, q) + bend_penalty * (axis != direction)
            if alt < distance.get(next_state, float("inf")):
                distance[next_state], prev[next_state] = alt, state
                heapq.heappush(queue, (alt+manhattan(q, goal), alt, next_state))
    if result is None:
        return None
    path = []
    while result in prev:
        path.append((xs[result[0]], ys[result[1]]))
        result = prev[result]
    return [start, *reversed(path)]


def route(source, target, a, b, obstacles, *, clearance, bend_penalty, crossing_penalty,
          lane=0, self_loop=False, inward=(False, False), used=()):
    """Return a valid polyline or raise RoutingError rather than draw through a node."""
    padded = [_grow(rect(box), clearance) for box in obstacles]
    exact = [rect(box) for box in obstacles]
    endpoint_blocks = [rect(bounds) for bounds, skip in zip((a, b), inward) if not skip]

    def segment_cost(p, q):
        value = manhattan(p, q)
        for v, w in used:
            cross, shared = segment_conflict(p, q, v, w)
            value += cross * crossing_penalty + shared * .8
        return value

    def clear(path, blocks):
        return all(p == q or not any(hits_box(p, q, block) for block in blocks) for p, q in pairwise(path))

    for obstacles in (padded, exact):
        blocks = [*obstacles, *endpoint_blocks]
        alternatives, fallback = [], []
        for side, actual, start in _ports(source, a, clearance, lane, inward[0]):
            if not clear((actual, start), obstacles):
                continue
            for end_side, end_actual, end in _ports(target, b, clearance, lane, inward[1]):
                if (self_loop and side == end_side) or not clear((end, end_actual), obstacles):
                    continue
                if any(inside_box(start, block) or inside_box(end, block) for block in blocks):
                    continue
                fallback.append((manhattan(start, end), actual, start, end, end_actual))
                sx, sy = start
                ex, ey = end
                dx = (sx + ex) / 2
                dy = (sy + ey) / 2
                candidates = [(start, (sx, ey), end), (start, (ex, sy), end),
                              (start, (dx, sy), (dx, ey), end),
                              (start, (sx, dy), (ex, dy), end)]
                if blocks:
                    for xx in (min(box[0] for box in blocks), max(box[2] for box in blocks)):
                        candidates.append((start, (xx, sy), (xx, ey), end))
                    for yy in (min(box[1] for box in blocks), max(box[3] for box in blocks)):
                        candidates.append((start, (sx, yy), (ex, yy), end))
                for candidate in candidates:
                    path = simplify([actual, *candidate, end_actual])
                    if len(path) < 2 or not clear(candidate, blocks):
                        continue
                    cost = sum(segment_cost(p, q) for p, q in pairwise(path)) + bend_penalty * (len(path) - 2)
                    alternatives.append((cost, path))
        if alternatives:
            return [point(*p) for p in min(alternatives)[1]]
        for _, actual, start, end, end_actual in sorted(fallback):
            path = _grid_route(start, end, blocks, segment_cost, bend_penalty,
                               orientation(actual, start), orientation(end, end_actual))
            if path is not None:
                return [point(*p) for p in simplify([actual, *path, end_actual])]
    raise RoutingError("No obstacle-free orthogonal route between the selected vertex outlines")


def label_position(points, text, obstacles, clearance):
    lines = text_lines(text)
    w, h = max(20, max(text_width(line, 10.5) for line in lines) + 10), 12 * len(lines) + 6
    segments = sorted(pairwise(points), key=lambda pair: -manhattan(
        (pair[0]["x"], pair[0]["y"]), (pair[1]["x"], pair[1]["y"])))
    for offset in (clearance, clearance + 12, clearance + 24, clearance + 48, clearance + 80):
        for a, b in segments:
            x, y = (a["x"]+b["x"])/2, (a["y"]+b["y"])/2
            for lx, ly in ((x-w/2, y-h-offset), (x-w/2, y+offset),
                           (x+offset, y-h/2), (x-w-offset, y-h/2)):
                candidate = dict(x=lx, y=ly, width=w, height=h)
                if not any(overlap(candidate, obstacle) for obstacle in obstacles):
                    return candidate
    bottom = max((box["y"]+box["height"] for box in obstacles), default=0)
    return dict(x=points[0]["x"], y=bottom+clearance, width=w, height=h)
