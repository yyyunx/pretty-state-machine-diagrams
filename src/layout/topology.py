"""Stable SCC condensation, longest-path ranks and barycentric ordering."""

from collections import defaultdict
from heapq import heappop, heappush


def layers(ids, edges):
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

    outgoing = [set() for _ in components]
    indegree = [0] * len(components)
    for start, ends in successors.items():
        for end in ends:
            a, b = owner[start], owner[end]
            if a != b and b not in outgoing[a]:
                outgoing[a].add(b)
                indegree[b] += 1
    pending, rank = [], [0] * len(components)
    for component, count in enumerate(indegree):
        if not count:
            heappush(pending, component)
    while pending:
        component = heappop(pending)
        for target in sorted(outgoing[component]):
            rank[target] = max(rank[target], rank[component] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                heappush(pending, target)
    columns = defaultdict(list)
    for node in ids:
        columns[rank[owner[node]]].append(node)

    ranks = sorted(columns)
    for sweep in range(4):
        inbound = sweep % 2 == 0
        neighbors = predecessors if inbound else successors
        positions = {node: index for column in columns.values() for index, node in enumerate(column)}
        for level in ranks if inbound else reversed(ranks):
            column = columns[level]

            def score(node):
                adjacent = [positions[other] for other in neighbors[node]
                            if (rank[owner[other]] < level if inbound else rank[owner[other]] > level)]
                return (sum(adjacent) / len(adjacent) if adjacent else positions[node], index[node])

            column.sort(key=score)
            positions.update({node: i for i, node in enumerate(column)})
    return [columns[i] for i in ranks]
