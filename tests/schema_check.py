"""A tiny JSON Schema subset validator so the tests need no third-party packages."""

import json
import re
from pathlib import Path

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "schema" / "ga4_event.schema.json").read_text())

_TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool, "null": type(None),
    "integer": int, "number": (int, float),
}


def _is(value, name):
    if name in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[name])


def errors(value, schema=SCHEMA, path="$"):
    out = []
    if "const" in schema and value != schema["const"]:
        return [f"{path}: expected {schema['const']!r}"]
    types = schema.get("type")
    if types:
        types = [types] if isinstance(types, str) else types
        if not any(_is(value, t) for t in types):
            return [f"{path}: {type(value).__name__} is not {types}"]
    if isinstance(value, dict) and "properties" in schema:
        for key in schema.get("required", []):
            if key not in value:
                out.append(f"{path}.{key}: missing")
        for key, sub in value.items():
            if key not in schema["properties"]:
                if schema.get("additionalProperties") is False:
                    out.append(f"{path}.{key}: unexpected")
                continue
            out += errors(sub, schema["properties"][key], f"{path}.{key}")
    if isinstance(value, list) and "items" in schema:
        for i, sub in enumerate(value):
            out += errors(sub, schema["items"], f"{path}[{i}]")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        out.append(f"{path}: does not match {schema['pattern']}")
    return out
