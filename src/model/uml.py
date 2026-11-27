"""UML 2.5.1 state machine checks for information represented in the SMD schema."""

from collections import defaultdict
from itertools import combinations

from .model import Diagnostic, Model, PathParts

HISTORY = ("shallowHistory", "deepHistory")
STATE_KINDS = ("state", "composite", "final")


def _region_chain(path: PathParts) -> tuple[PathParts, ...]:
    return tuple(path[:index + 2] for index, part in enumerate(path) if part == "regions")


def _orthogonal_siblings(left: tuple[PathParts, ...], right: tuple[PathParts, ...]) -> bool:
    for first, second in zip(left, right):
        if first != second:
            # A nonempty prefix identifies the same composite State container.
            return bool(first[:-2]) and first[:-2] == second[:-2]
    return False


def uml_diagnostics(elements: list[tuple[str, PathParts, Model]]) -> tuple[Diagnostic, ...]:
    """Apply chapter 14 constraints after schema and endpoint validation."""
    vertices = {value["id"]: (path, value) for role, path, value in elements if role == "vertex"}
    regions = {vertex_id: _region_chain(path) for vertex_id, (path, _) in vertices.items()}
    incoming: dict[str, list[Model]] = defaultdict(list)
    outgoing: dict[str, list[Model]] = defaultdict(list)
    diagnostics: list[Diagnostic] = []

    for role, path, edge in elements:
        if role != "transition":
            continue
        start, end = edge["sourceId"], edge["targetId"]
        incoming[end].append(edge)
        outgoing[start].append(edge)
        _, source = vertices[start]
        _, target = vertices[end]
        source_pseudo = source.get("pseudostateKind")
        target_pseudo = target.get("pseudostateKind")
        # §§14.5.6.7, 14.5.11.8
        if source_pseudo and "triggers" in edge:
            diagnostics.append(Diagnostic.at(
                "uml-pseudostate-trigger", (*path, "triggers"), "Outgoing pseudostate segments cannot have triggers.",
            ))
        elif target_pseudo == "join" and "triggers" in edge:
            diagnostics.append(Diagnostic.at(
                "uml-join-trigger", (*path, "triggers"), "Incoming join segments cannot have triggers.",
            ))
        if "guard" in edge and (source_pseudo in ("initial", "fork") or target_pseudo == "join"):
            diagnostics.append(Diagnostic.at(
                "uml-segment-guard", (*path, "guard"), "Initial, outgoing fork and incoming join segments cannot have guards.",
            ))
        if source_pseudo == "fork" and target["kind"] not in STATE_KINDS:
            diagnostics.append(Diagnostic.at(
                "uml-fork-target", (*path, "targetId"), "An outgoing fork segment must target a State.",
            ))
        if target_pseudo == "join" and source["kind"] not in STATE_KINDS:
            diagnostics.append(Diagnostic.at(
                "uml-join-source", (*path, "sourceId"), "An incoming join segment must originate from a State.",
            ))

        # §14.2.3.8.5 recommends, but does not require, the innermost containing Region.
        common = [first for first, second in zip(regions[start], regions[end]) if first == second]
        if common and common[-1] != path[:-2]:
            diagnostics.append(Diagnostic.at(
                "uml-region-owner", path, "Prefer the innermost Region containing both endpoints.",
                severity="warning",
            ))
        elif not common:
            diagnostics.append(Diagnostic.at(
                "uml-cross-root-region", path,
                "Endpoints lie in different top-level Regions. Review ownership when assigning UML transition kinds.",
                severity="warning",
            ))
        if source_pseudo in HISTORY and regions[start][-1] not in regions[end]:
            diagnostics.append(Diagnostic.at(
                "uml-history-default-region", (*path, "targetId"),
                "Review a default history destination outside its history Region.", severity="warning",
            ))

    singletons = set()
    for vertex_id, (path, vertex) in vertices.items():
        entering, leaving = incoming[vertex_id], outgoing[vertex_id]
        kind = vertex.get("pseudostateKind")
        if kind in ("initial", *HISTORY):
            # §14.5.8.6 allows at most one vertex of each of these kinds per Region.
            position = (regions[vertex_id][-1], kind)
            if position in singletons:
                diagnostics.append(Diagnostic.at(
                    "uml-duplicate-region-pseudostate", path, f"Region already has a '{kind}' vertex.",
                ))
            singletons.add(position)
            if len(leaving) > 1:
                diagnostics.append(Diagnostic.at(
                    "uml-pseudostate-outgoing", path, f"'{kind}' can have at most one outgoing transition.",
                ))
        if vertex["kind"] == "final" and leaving:
            diagnostics.append(Diagnostic.at(
                "uml-final-outgoing", path, "A FinalState cannot have outgoing transitions.",
            ))
        if kind not in ("fork", "join"):
            continue

        singleton = entering if kind == "fork" else leaving
        segments = leaving if kind == "fork" else entering
        endpoint = "targetId" if kind == "fork" else "sourceId"
        if len(singleton) > 1:
            diagnostics.append(Diagnostic.at(
                f"uml-{kind}-cardinality", path, f"A '{kind}' has only one transition on its unbranched side.",
            ))
        if not singleton or len(segments) < 2:
            diagnostics.append(Diagnostic.at(
                f"uml-{kind}-incomplete", path,
                f"A complete '{kind}' needs one unbranched transition and at least two branches.", severity="warning",
            ))
        if any(
            not _orthogonal_siblings(regions[first[endpoint]], regions[second[endpoint]])
            for first, second in combinations(segments, 2)
        ):
            diagnostics.append(Diagnostic.at(
                f"uml-{kind}-orthogonal-regions", path,
                f"Each pair of '{kind}' branches must touch distinct Regions of an orthogonal State.",
            ))
    return tuple(diagnostics)
