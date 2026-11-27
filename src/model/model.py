"""Build, validate, and serialize models using the shared SMD JSON schema."""

import json
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

SCHEMA_VERSION = "0.1.0-draft"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "smd-model.schema.json"
Model = dict[str, Any]
PathParts = tuple[str | int, ...]

CHILDREN = {
    "model": (("regions", "region"),),
    "region": (("vertices", "vertex"), ("transitions", "transition")),
    "vertex": (("regions", "region"),),
    "transition": (),
}


@dataclass(frozen=True)
class Diagnostic:
    code: str
    path: str
    message: str

    @classmethod
    def at(cls, code: str, path: PathParts, message: str) -> "Diagnostic":
        pointer = "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in path)
        return cls(code, pointer, message)


class ModelError(ValueError):
    def __init__(self, *diagnostics: Diagnostic):
        self.diagnostics = diagnostics
        super().__init__("\n".join(
            f"{item.code} at {item.path or '<root>'}: {item.message}" for item in diagnostics
        ))


class InternalIdGenerator:
    """Allocate IDs in traversal order, reserving supplied IDs up front."""

    def __init__(self, reserved: Iterable[str] = ()):
        self._reserved = set(reserved)
        self._counts: dict[str, int] = defaultdict(int)

    def allocate(self, role: str) -> str:
        while True:
            self._counts[role] += 1
            candidate = f"{role}-{self._counts[role]}"
            if candidate not in self._reserved:
                self._reserved.add(candidate)
                return candidate


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def _elements(
    value: object,
    role: str = "model",
    path: PathParts = (),
    ancestors: frozenset[int] = frozenset(),
):
    """Walk recognized containers. The schema validator reports malformed shapes."""
    if not isinstance(value, dict):
        return
    if id(value) in ancestors:
        raise ModelError(Diagnostic.at("invalid-hierarchy", path, "Circular model containment."))
    yield role, path, value
    ancestors = ancestors | {id(value)}
    for field, child_role in CHILDREN[role]:
        children = value.get(field)
        if isinstance(children, list):
            for index, child in enumerate(children):
                yield from _elements(child, child_role, (*path, field, index), ancestors)


def _shape_error(path: PathParts, message: str) -> Diagnostic:
    field = path[-1] if path else None
    code = {
        "regions": "invalid-hierarchy",
        "vertices": "invalid-hierarchy",
        "transitions": "invalid-hierarchy",
        "kind": "invalid-node-kind",
        "pseudostateKind": "invalid-node-kind",
        "displayName": "invalid-display-name",
        "id": "invalid-id",
    }.get(field, "invalid-schema")
    return Diagnostic.at(code, path, message)


def _schema_diagnostics(error):
    path = tuple(error.absolute_path)
    if error.validator == "oneOf" and isinstance(error.instance, dict):
        # Report errors for the declared vertex kind instead of errors from every alternative.
        kind = error.instance.get("kind")
        for index, variant in enumerate(error.validator_value):
            if variant["properties"]["kind"]["const"] == kind:
                for field, rule in variant["properties"].items():
                    if rule is False and field in error.instance:
                        yield _shape_error(
                            (*path, field),
                            f"Property {field!r} is incompatible with vertex kind {kind!r}.",
                        )
                for cause in error.context:
                    if cause.schema_path[0] == index and cause.schema is not False:
                        yield from _schema_diagnostics(cause)
                return
        return  # The enum and required properties already report an absent or invalid kind.
    if error.validator == "required":
        for field in error.validator_value:
            if field not in error.instance:
                yield Diagnostic.at("missing-field", (*path, field), f"Required property {field!r} is absent.")
        return
    if error.validator == "additionalProperties":
        for field in error.instance:
            if field not in error.schema["properties"]:
                yield Diagnostic.at("unknown-field", (*path, str(field)), f"Unexpected property {field!r}.")
        return
    yield _shape_error(path, error.message)


def _validate(model: object, elements) -> None:
    diagnostics = dict.fromkeys(
        item for error in _validator().iter_errors(model) for item in _schema_diagnostics(error)
    )
    if diagnostics:
        raise ModelError(*diagnostics)

    ids: dict[str, PathParts] = {}
    vertex_ids: set[str] = set()
    for role, path, element in elements:
        element_id = element["id"]
        id_path = (*path, "id")
        if element_id in ids:
            earlier = Diagnostic.at("duplicate-id", ids[element_id], "").path
            diagnostics[Diagnostic.at(
                "duplicate-id", id_path, f"ID {element_id!r} already occurs at {earlier}."
            )] = None
        else:
            ids[element_id] = id_path
        if role == "vertex":
            vertex_ids.add(element_id)

    for role, path, element in elements:
        if role == "transition":
            for field in ("sourceId", "targetId"):
                target = element[field]
                if target not in vertex_ids:
                    diagnostics[Diagnostic.at(
                        "invalid-endpoint", (*path, field),
                        f"Transition endpoint {target!r} does not identify a vertex in this model.",
                    )] = None
    if diagnostics:
        raise ModelError(*diagnostics)


def validate_model(model: object) -> None:
    """Raise ModelError with schema or graph diagnostics for an invalid model."""
    try:
        _validate(model, list(_elements(model)))
    except RecursionError as error:
        raise ModelError(Diagnostic.at("invalid-hierarchy", (), "Model nesting exceeds Python's limit.")) from error


def build_model(draft: object) -> Model:
    """Copy an authored draft, assign missing IDs, and return the validated model.

    Transition endpoints refer to explicitly supplied vertex IDs. Reserving
    endpoint text avoids binding a misspelled endpoint to a generated ID.
    """
    try:
        model = deepcopy(draft)
        if not isinstance(model, dict):
            validate_model(model)
        model.setdefault("schemaVersion", SCHEMA_VERSION)
        elements = list(_elements(model))

        reserved = {obj["id"] for _, _, obj in elements if isinstance(obj.get("id"), str)}
        reserved.update(
            obj[field]
            for role, _, obj in elements if role == "transition"
            for field in ("sourceId", "targetId") if isinstance(obj.get(field), str)
        )
        ids = InternalIdGenerator(reserved)
        for role, _, element in elements:
            if "id" not in element:
                element["id"] = ids.allocate(role)
        _validate(model, elements)
        return model
    except RecursionError as error:
        raise ModelError(Diagnostic.at("invalid-hierarchy", (), "Model nesting exceeds Python's limit.")) from error


def serialize_model(model: object) -> str:
    """Validate and return reproducible UTF-8 JSON text with a final newline."""
    validate_model(model)
    try:
        text = json.dumps(model, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ModelError(Diagnostic.at("invalid-json", (), str(error))) from error
    return text + "\n"
