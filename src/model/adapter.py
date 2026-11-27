"""Prototype adapter boundary for pre-resolved Converter output."""

from typing import Protocol

from .model import Diagnostic, InternalIdGenerator, Model, ModelError, PathParts, build_model

INTERACTION_FIELDS = ("sourceInteractionId", "triggers", "guard", "effect", "sourceText")


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
    source = f" Source: {source_text!r}." if isinstance(source_text, str) else ""
    return ModelError(Diagnostic.at(
        "unresolved-semantic", path, f"No confirmed lowering for {operator!r}.{source}"
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
    """Adapt the repository's resolved linear and branch fixtures."""

    def adapt(self, source: object) -> Model:
        if not isinstance(source, dict):
            raise ModelError(Diagnostic.at("invalid-input", (), "Expected structured Mock Converter output."))
        if "sourceText" in source and not isinstance(source["sourceText"], str):
            raise ModelError(Diagnostic.at("invalid-input", ("sourceText",), "Expected source text."))
        kind = source.get("kind")
        if kind == "unresolved":
            _object(source, (), required=("kind", "operator"), optional=("sourceText",))
            raise _unresolved(("operator",), source["operator"], source.get("sourceText"))
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
