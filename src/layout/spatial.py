"""Bounding-box queries for routing and geometry measurements."""

from collections import defaultdict
from math import floor


class SpatialIndex:
    def __init__(self, cell=128, max_cells=96):
        self.cell, self.max_cells = cell, max_cells
        self.cells = defaultdict(list)
        self.large, self.entries = [], []

    def _range(self, box):
        x, y, r, b = (floor(value / self.cell) for value in box)
        if (r-x+1)*(b-y+1) > self.max_cells:
            return None
        return range(x,r+1), range(y,b+1)

    def add(self, bounds, value):
        index = len(self.entries)
        self.entries.append((bounds, value))
        cells = self._range(bounds)
        if cells is None:
            self.large.append(index)
        else:
            for x in cells[0]:
                for y in cells[1]:
                    self.cells[x,y].append(index)

    def query(self, bounds):
        x,y,r,b = bounds
        cells = self._range(bounds)
        if cells is None:
            entries = range(len(self.entries))
        else:
            entries = set(self.large)
            for i in cells[0]:
                for j in cells[1]:
                    entries.update(self.cells.get((i,j), ()))
        for index in sorted(entries) if isinstance(entries,set) else entries:
            (u,v,s,t), value = self.entries[index]
            if x <= s and u <= r and y <= t and v <= b:
                yield value


def segment_bounds(a,b, pad=0):
    return (min(a[0],b[0])-pad, min(a[1],b[1])-pad,
            max(a[0],b[0])+pad, max(a[1],b[1])+pad)


class Occupancy:
    def __init__(self):
        self.index = SpatialIndex()
        self.paths = {}

    def add(self, key, segments):
        self.paths[key] = tuple(segments)
        for segment in self.paths[key]:
            self.index.add(segment_bounds(*segment), (key, self.paths[key], segment))

    def nearby(self, a, b, *, ignore=None):
        yield from self.in_box(segment_bounds(a,b,1e-7),ignore=ignore)

    def in_box(self, bounds, *, ignore=None):
        # Old index entries are tombstones; a bounded number of edges are rerouted.
        for key, path, segment in self.index.query(bounds):
            if key != ignore and self.paths.get(key) is path:
                yield segment
