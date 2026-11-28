"""Stable SCC condensation, longest-path ranks and barycentric ordering."""

from collections import defaultdict, deque
from heapq import heappop, heappush
from math import ceil, sqrt
from statistics import median


def connected_components(ids, edges):
    """Return deterministic SCCs, ownership and adjacency for these vertices."""
    index = {node: position for position, node in enumerate(ids)}
    successors = {node: [] for node in ids}
    predecessors = {node: [] for node in ids}
    for start, end in dict.fromkeys(edges):
        if start != end:
            successors[start].append(end)
            predecessors[end].append(start)

    # Iterative Kosaraju avoids Python recursion limits on long chains.
    finished, seen = [], set()
    for node in ids:
        if node in seen:
            continue
        seen.add(node)
        stack = [(node, iter(successors[node]))]
        while stack:
            top, children = stack[-1]
            child = next(children, None)
            if child is None:
                stack.pop()
                finished.append(top)
            elif child not in seen:
                seen.add(child)
                stack.append((child, iter(successors[child])))

    components, owner = [], {}
    for node in reversed(finished):
        if node in owner:
            continue
        component = []
        owner[node] = len(components)
        queue = [node]
        while queue:
            item = queue.pop()
            component.append(item)
            for parent in predecessors[item]:
                if parent not in owner:
                    owner[parent] = len(components)
                    queue.append(parent)
        components.append(sorted(component, key=index.get))
    return components, owner, successors, predecessors


def layers(ids, edges, *, order="mean", split_cycles=False, reverse_sweep=False):
    index = {node:position for position,node in enumerate(ids)}
    components,owner,successors,predecessors = connected_components(ids,edges)

    outgoing = [set() for _ in components]
    indegree = [0] * len(components)
    for start, ends in successors.items():
        for end in ends:
            a, b = owner[start], owner[end]
            if a != b and b not in outgoing[a]:
                outgoing[a].add(b)
                indegree[b] += 1
    offsets = dict.fromkeys(ids, 0)
    widths = [1] * len(components)
    if split_cycles:
        for component, nodes in enumerate(components):
            if len(nodes) < 3:
                continue
            # Spread a strongly connected component along the directed BFS order.
            # Back edges remain directed exactly as in the model.
            gate = min(nodes, key=lambda node: (
                -sum(owner[p] != component for p in predecessors[node]), index[node]))
            queue = deque([gate])
            visited = {gate}
            order_in_component = []
            while queue:
                current = queue.popleft()
                order_in_component.append(current)
                for child in successors[current]:
                    if owner[child] == component and child not in visited:
                        visited.add(child)
                        queue.append(child)
            capacity = ceil(sqrt(len(nodes)))
            for position,node in enumerate(order_in_component):
                offsets[node] = position // capacity
            widths[component] = ceil(len(nodes) / capacity)
    pending, rank = [], [0] * len(components)
    for component, count in enumerate(indegree):
        if not count:
            heappush(pending, component)
    while pending:
        component = heappop(pending)
        for target in sorted(outgoing[component]):
            rank[target] = max(rank[target], rank[component] + widths[component])
            indegree[target] -= 1
            if indegree[target] == 0:
                heappush(pending, target)
    columns = defaultdict(list)
    node_rank = {node:rank[owner[node]]+offsets[node] for node in ids}
    for node in ids:
        columns[node_rank[node]].append(node)

    ranks = sorted(columns)
    for sweep in range(4):
        inbound = (sweep % 2 == 0) != reverse_sweep
        neighbors = predecessors if inbound else successors
        positions = {node: index for column in columns.values() for index, node in enumerate(column)}
        for level in ranks if inbound else reversed(ranks):
            column = columns[level]

            def score(node):
                adjacent = [positions[other] for other in neighbors[node]
                            if (node_rank[other] < level if inbound else node_rank[other] > level)]
                if not adjacent:
                    return positions[node], index[node]
                return (median(adjacent) if order=="median" else sum(adjacent)/len(adjacent), index[node])

            column.sort(key=score)
            positions.update({node: i for i, node in enumerate(column)})
    return [columns[i] for i in ranks]
