"""Prototype adapter boundary for pre-resolved Converter output."""

from dataclasses import dataclass
from typing import Protocol

from .model import Diagnostic, InternalIdGenerator, Model, ModelError, PathParts, build_model

INTERACTION_FIELDS = ("sourceInteractionId", "triggers", "guard", "effect", "sourceText")
UNRESOLVED_KINDS = ("alt", "par", "seq", "ref", "loop", ">>", "0", "◉", "C", "©")


class ConverterAdapter(Protocol):
    def adapt(self, source: object) -> Model:
        """Return an explicit model draft, or raise ModelError for an unresolved input."""
        ...


def transform_model(source: object, adapter: ConverterAdapter) -> Model:
    """Build a validated model from a Converter adapter's explicit draft."""
    return build_model(adapter.adapt(source))


def _object(value, path: PathParts, *, required=(), optional=()) -> Model:
    if not isinstance(value, dict):
        raise ModelError(Diagnostic.at("invalid-input", path, "Expected an object."))
    allowed = set(required) | set(optional)
    for field in value:
        if field not in allowed:
            raise ModelError(Diagnostic.at(
                "unsupported-field", (*path, str(field)), f"Mock adapter cannot represent {field!r}."
            ))
    for field in required:
        if field not in value:
            raise ModelError(Diagnostic.at("missing-field", (*path, field), f"Required property {field!r} is absent."))
    return value


def _items(value, path: PathParts, minimum: int) -> list:
    if not isinstance(value, list) or len(value) < minimum:
        raise ModelError(Diagnostic.at("invalid-input", path, f"Expected an array with at least {minimum} item(s)."))
    return value


def _state(value, path: PathParts, state_id: str) -> Model:
    state = _object(value, path, optional=("kind", "displayName", "behaviors"))
    if state.get("kind", "state") != "state":
        raise ModelError(Diagnostic.at("invalid-input", (*path, "kind"), "Expected an ordinary state."))
    return {"kind": "state", "id": state_id, **state}


def _interaction(value, path: PathParts) -> Model:
    return _object(value, path, optional=INTERACTION_FIELDS)


def _unresolved(path: PathParts, operator: object, source_text: object) -> ModelError:
    raw = source_text if isinstance(source_text, str) else None
    source = f" Source: {raw!r}." if raw is not None else ""
    return ModelError(Diagnostic.at(
        "unresolved-semantic", path, f"No confirmed lowering for {operator!r}.{source}", source_text=raw
    ))


def _linear(source: Model, ids: InternalIdGenerator) -> tuple[list[Model], list[Model]]:
    _object(source, (), required=("kind", "steps", "terminal"), optional=("id", "sourceText"))
    steps = _items(source["steps"], ("steps",), 1)
    terminal = _object(source["terminal"], ("terminal",), required=("token",), optional=("resolvedKind",))
    if terminal["token"] != "◉" or terminal.get("resolvedKind") != "final":
        raise _unresolved(("terminal", "token"), terminal["token"], source.get("sourceText"))

    states, interactions = [], []
    for index, raw_step in enumerate(steps):
        path = ("steps", index)
        step = _object(raw_step, path, required=("interaction",), optional=("sourceState",))
        states.append(_state(step.get("sourceState", {}), (*path, "sourceState"), ids.allocate("vertex")))
        interactions.append(_interaction(step["interaction"], (*path, "interaction")))
    states.append({"kind": "final", "id": ids.allocate("vertex")})
    edges = [
        {"sourceId": start["id"], "targetId": end["id"], **interaction}
        for start, end, interaction in zip(states[:-1], states[1:], interactions, strict=True)
    ]
    return states, edges


def _resolved_branch(source: Model, ids: InternalIdGenerator) -> tuple[list[Model], list[Model]]:
    _object(source, (), required=("kind", "sourceState", "alternatives"), optional=("id", "sourceText"))
    start = _state(source["sourceState"], ("sourceState",), ids.allocate("vertex"))
    states, edges = [start], []
    for index, raw_branch in enumerate(_items(source["alternatives"], ("alternatives",), 2)):
        path = ("alternatives", index)
        branch = _object(raw_branch, path, required=("targetState", "interaction"))
        target = _state(branch["targetState"], (*path, "targetState"), ids.allocate("vertex"))
        interaction = _interaction(branch["interaction"], (*path, "interaction"))
        states.append(target)
        edges.append({"sourceId": start["id"], "targetId": target["id"], **interaction})
    return states, edges


class MockConverterAdapter:
    """Adapt the original fixtures and explicitly resolved recursive behavior."""

    def adapt(self, source: object) -> Model:
        if not isinstance(source, dict):
            raise ModelError(Diagnostic.at("invalid-input", (), "Expected structured Mock Converter output."))
        if "sourceText" in source and not isinstance(source["sourceText"], str):
            raise ModelError(Diagnostic.at("invalid-input", ("sourceText",), "Expected source text."))
        kind = source.get("kind")
        if kind == "unresolved":
            _object(source, (), required=("kind", "operator"), optional=("sourceText",))
            raise _unresolved(("operator",), source["operator"], source.get("sourceText"))
        if kind in UNRESOLVED_KINDS:
            raise _unresolved(("kind",), kind, source.get("sourceText"))
        if kind == "resolvedBehavior":
            return _ResolvedBehavior(source).draft()
        if kind not in ("linear", "resolvedBranch"):
            raise ModelError(Diagnostic.at("unsupported-input", ("kind",), f"Unsupported Mock Converter kind {kind!r}."))

        model_id = source.get("id", f"mock-{kind}")
        ids = InternalIdGenerator([model_id] if isinstance(model_id, str) else [])
        initial = {"kind": "pseudostate", "pseudostateKind": "initial", "id": ids.allocate("vertex")}
        states, edges = _linear(source, ids) if kind == "linear" else _resolved_branch(source, ids)
        entry = {"sourceId": initial["id"], "targetId": states[0]["id"]}
        return {
            "id": model_id,
            "regions": [{"vertices": [initial, *states], "transitions": [entry, *edges]}],
        }


@dataclass(frozen=True)
class _Reference:
    key: str
    path: PathParts
    source_text: str | None


@dataclass(frozen=True)
class _Fragment:
    entry: str | _Reference
    exit: str | _Reference | None

    def tail(self, path: PathParts, source_text: str | None) -> str | _Reference:
        if self.exit is None:
            raise ModelError(Diagnostic.at(
                "ambiguous-continuation", path, "This behavior has no single explicit continuation.",
                source_text=source_text,
            ))
        return self.exit


class _ResolvedBehavior:
    """Lower explicit behavior to regions and resolve references after traversal."""

    def __init__(self, source: Model):
        self.source = _object(
            source, (), required=("kind", "regions"), optional=("id", "displayName", "sourceText")
        )
        self.model_id = source.get("id", "mock-resolvedBehavior")
        self.ids = InternalIdGenerator([self.model_id] if isinstance(self.model_id, str) else [])
        self.symbols: dict[str, tuple[str, PathParts]] = {}
        self.edges: list[Model] = []
        self.references: list[_Reference] = []

    def draft(self) -> Model:
        regions = [
            self.region(value, ("regions", index), self.source.get("sourceText"))
            for index, value in enumerate(_items(self.source["regions"], ("regions",), 1))
        ]
        missing = [
            Diagnostic.at(
                "unresolved-reference", ref.path, f"Unknown vertex key {ref.key!r}.", source_text=ref.source_text,
            )
            for ref in self.references if ref.key not in self.symbols
        ]
        if missing:
            raise ModelError(*dict.fromkeys(missing))
        for edge in self.edges:
            for field in ("sourceId", "targetId"):
                ref = edge[field]
                if isinstance(ref, _Reference):
                    edge[field] = self.symbols[ref.key][0]
        return {
            "id": self.model_id, "regions": regions,
            **{name: self.source[name] for name in ("displayName",) if name in self.source},
        }

    def region(self, value, path: PathParts, source_text: str | None) -> Model:
        data = _object(value, path, required=("body",), optional=("displayName", "links", "sourceText"))
        source_text = self.source_text(data, path, source_text)
        region = {"vertices": [], "transitions": []}
        if "displayName" in data:
            region["displayName"] = data["displayName"]
        for index, child in enumerate(_items(data["body"], (*path, "body"), 0)):
            self.behavior(child, (*path, "body", index), region, source_text)
        for index, link in enumerate(_items(data.get("links", []), (*path, "links"), 0)):
            link_path = (*path, "links", index)
            link = _object(link, link_path, required=("from", "to", "interaction"), optional=("sourceText",))
            raw = self.source_text(link, link_path, source_text)
            start = self.reference(link["from"], (*link_path, "from"), raw)
            end = self.reference(link["to"], (*link_path, "to"), raw)
            self.references.extend((start, end))
            self.edge(region, start, end, link["interaction"], (*link_path, "interaction"))
        return region

    @staticmethod
    def source_text(data: Model, path: PathParts, inherited: str | None) -> str | None:
        raw = data.get("sourceText", inherited)
        if "sourceText" in data and not isinstance(raw, str):
            raise ModelError(Diagnostic.at("invalid-input", (*path, "sourceText"), "Expected source text."))
        return raw

    @staticmethod
    def reference(key, path: PathParts, source_text: str | None) -> _Reference:
        if not isinstance(key, str) or not key.strip():
            raise ModelError(Diagnostic.at("invalid-input", path, "Expected a non-empty vertex key."))
        return _Reference(key, path, source_text)

    def edge(self, region: Model, start, end, value, path: PathParts) -> None:
        interaction = _interaction(value, path)
        edge = {"sourceId": start, "targetId": end, **interaction}
        region["transitions"].append(edge)
        self.edges.append(edge)

    def behavior(self, value, path: PathParts, region: Model, inherited: str | None) -> _Fragment:
        if not isinstance(value, dict):
            raise ModelError(Diagnostic.at("invalid-input", path, "Expected a behavior object."))
        raw = self.source_text(value, path, inherited)
        kind = value.get("kind")
        if kind == "unresolved":
            _object(value, path, required=("kind", "operator"), optional=("sourceText",))
            raise _unresolved((*path, "operator"), value["operator"], raw)
        if kind in UNRESOLVED_KINDS:
            raise _unresolved((*path, "kind"), kind, raw)
        if kind == "reference":
            _object(value, path, required=("kind", "target"), optional=("sourceText",))
            ref = self.reference(value["target"], (*path, "target"), raw)
            # Collect references even when the fragment has no incident transition.
            self.references.append(ref)
            return _Fragment(ref, ref)
        if kind == "sequence":
            return self.sequence(value, path, region, raw)
        if kind == "branch":
            return self.branch(value, path, region, raw)
        if kind == "repeat":
            _object(value, path, required=("kind", "body", "backInteraction"), optional=("sourceText",))
            body = self.behavior(value["body"], (*path, "body"), region, raw)
            self.edge(
                region, body.tail((*path, "body"), raw), body.entry,
                value["backInteraction"], (*path, "backInteraction"),
            )
            return body
        if kind in ("state", "composite", "pseudostate", "final"):
            return self.vertex(value, path, region, raw)
        raise ModelError(Diagnostic.at(
            "unsupported-input", (*path, "kind"), f"Unsupported behavior kind {kind!r}.", source_text=raw,
        ))

    def vertex(self, value: Model, path: PathParts, region: Model, raw: str | None) -> _Fragment:
        kind = value["kind"]
        required = {"composite": ("regions",), "pseudostate": ("pseudostateKind",)}.get(kind, ())
        optional = ("key", "displayName", "sourceText")
        if kind in ("state", "composite"):
            optional += ("behaviors",)
        _object(value, path, required=("kind", *required), optional=optional)
        vertex_id = self.ids.allocate("vertex")
        if "key" in value:
            ref = self.reference(value["key"], (*path, "key"), raw)
            if ref.key in self.symbols:
                earlier = Diagnostic.at("duplicate-vertex-key", self.symbols[ref.key][1], "").path
                raise ModelError(Diagnostic.at(
                    "duplicate-vertex-key", ref.path, f"Vertex key {ref.key!r} already occurs at {earlier}.",
                    source_text=raw,
                ))
            self.symbols[ref.key] = (vertex_id, ref.path)
        fields = ("displayName", "behaviors", "pseudostateKind")
        vertex = {"kind": kind, "id": vertex_id, **{field: value[field] for field in fields if field in value}}
        region["vertices"].append(vertex)
        if kind == "composite":
            vertex["regions"] = [
                self.region(child, (*path, "regions", index), raw)
                for index, child in enumerate(_items(value["regions"], (*path, "regions"), 1))
            ]
        return _Fragment(vertex_id, vertex_id)

    def sequence(self, value: Model, path: PathParts, region: Model, raw: str | None) -> _Fragment:
        _object(value, path, required=("kind", "parts", "connect"), optional=("sourceText",))
        parts = _items(value["parts"], (*path, "parts"), 1)
        connect = _items(value["connect"], (*path, "connect"), 0)
        if len(connect) != len(parts) - 1:
            raise ModelError(Diagnostic.at(
                "invalid-input", (*path, "connect"), "Give one interaction between adjacent parts.",
                source_text=raw,
            ))
        first = previous = self.behavior(parts[0], (*path, "parts", 0), region, raw)
        for index, (part, interaction) in enumerate(zip(parts[1:], connect, strict=True)):
            tail = previous.tail((*path, "parts", index), raw)
            following = self.behavior(part, (*path, "parts", index + 1), region, raw)
            self.edge(region, tail, following.entry, interaction, (*path, "connect", index))
            previous = following
        return _Fragment(first.entry, previous.exit)

    def branch(self, value: Model, path: PathParts, region: Model, raw: str | None) -> _Fragment:
        _object(value, path, required=("kind", "source", "alternatives"), optional=("exit", "sourceText"))
        source = self.behavior(value["source"], (*path, "source"), region, raw)
        tail = source.tail((*path, "source"), raw)
        has_exit = "exit" in value
        branches = []
        alternatives = _items(value["alternatives"], (*path, "alternatives"), 2)
        for index, entry in enumerate(alternatives):
            branch_path = (*path, "alternatives", index)
            required = ("body", "interaction", "toExit") if has_exit else ("body", "interaction")
            branch = _object(entry, branch_path, required=required)
            body = self.behavior(branch["body"], (*branch_path, "body"), region, raw)
            self.edge(region, tail, body.entry, branch["interaction"], (*branch_path, "interaction"))
            branches.append(body)
        if not has_exit:
            return _Fragment(source.entry, None)
        end = self.behavior(value["exit"], (*path, "exit"), region, raw)
        for index, (branch, body) in enumerate(zip(alternatives, branches, strict=True)):
            branch_path = (*path, "alternatives", index)
            self.edge(
                region, body.tail((*branch_path, "body"), raw), end.entry, branch["toExit"],
                (*branch_path, "toExit"),
            )
        return _Fragment(source.entry, end.exit)
