"""Convert an OpenAPI 3.x spec (as produced by FastAPI) into structured Markdown.

Pure Python with no Streamlit dependency, so it can be tested or used from a CLI.

Covers: tags (grouped), path-level + operation parameters, `$ref` parameters /
responses / request bodies, nested inline objects, allOf / anyOf / oneOf,
enums, constraints, formats, defaults, security schemes (http, apiKey, oauth2,
openIdConnect), webhooks, deprecated operations and generated examples.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterator

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

_CONSTRAINT_LABELS = {
    "minLength": "Min length",
    "maxLength": "Max length",
    "minimum": "Min",
    "maximum": "Max",
    "exclusiveMinimum": "Greater than",
    "exclusiveMaximum": "Less than",
    "multipleOf": "Multiple of",
    "minItems": "Min items",
    "maxItems": "Max items",
    "uniqueItems": "Unique items",
    "pattern": "Pattern",
}

_PRIMITIVE_EXAMPLES = {"string": "string", "integer": 1, "number": 0.0, "boolean": True}


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #
def slugify(text: str) -> str:
    """GitHub-style heading anchor."""
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def _cell(text: Any) -> str:
    """Make text safe for a Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", "<br>")


def _num(value: Any) -> Any:
    return int(value) if isinstance(value, float) and value.is_integer() else value


def _walk(schema: dict) -> Iterator[dict]:
    """Yield a schema and every inline sub-schema in anyOf / oneOf / allOf."""
    yield schema
    for key in ("anyOf", "oneOf", "allOf"):
        for sub in schema.get(key, []):
            if isinstance(sub, dict):
                yield from _walk(sub)


def _resolve(spec: dict, ref: str) -> dict:
    node: Any = spec
    for part in ref.lstrip("#").strip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, dict) else {}


def deref(spec: dict, obj: Any) -> Any:
    """Follow `$ref` chains (parameters, responses, request bodies, ...)."""
    seen: set[str] = set()
    while isinstance(obj, dict) and "$ref" in obj and obj["$ref"] not in seen:
        seen.add(obj["$ref"])
        obj = _resolve(spec, obj["$ref"])
    return obj


def _ref_link(ref: str) -> str:
    name = ref.rsplit("/", 1)[-1]
    return f"[`{name}`](#{slugify(name)})"


# --------------------------------------------------------------------------- #
# Schema -> text
# --------------------------------------------------------------------------- #
def type_label(schema: dict | None) -> str:
    """Markdown-formatted, human-friendly type for a schema."""
    if not schema:
        return "`any`"
    if "$ref" in schema:
        return _ref_link(schema["$ref"])
    label = _base_label(schema)
    if schema.get("nullable") and "`null`" not in label:
        label += " or `null`"
    return label


def _base_label(schema: dict) -> str:
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return " or ".join(type_label(s) for s in schema[key])
    if "allOf" in schema:
        return " & ".join(type_label(s) for s in schema["allOf"])

    t = schema.get("type")
    if isinstance(t, list):
        return " or ".join(f"`{x}`" for x in t)

    fmt = schema.get("format")
    if not fmt and schema.get("contentMediaType"):  # OpenAPI 3.1 file uploads
        media = schema["contentMediaType"]
        fmt = "binary" if media == "application/octet-stream" else media
    if t == "array":
        if "prefixItems" in schema:
            inner = ", ".join(type_label(s) for s in schema["prefixItems"])
            return f"`tuple` of ({inner})"
        return f"`array` of {type_label(schema.get('items'))}"
    if t == "object":
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict) and not schema.get("properties"):
            return f"`map` of {type_label(extra)}"
    if t:
        return f"`{t}<{fmt}>`" if fmt else f"`{t}`"
    if "properties" in schema:
        return "`object`"
    if "const" in schema:
        return f"`{type(schema['const']).__name__}`"
    if "enum" in schema:
        return "`enum`"
    return "`any`"


def constraints(schema: dict) -> list[str]:
    """Enum values, validation constraints and flags (also inside anyOf)."""
    notes: list[str] = []
    for node in _walk(schema):
        if "enum" in node:
            notes.append("One of: " + ", ".join(f"`{json.dumps(v)}`" for v in node["enum"]))
        if "const" in node:
            notes.append(f"Constant: `{json.dumps(node['const'])}`")
        for key, label in _CONSTRAINT_LABELS.items():
            if key in node:
                notes.append(f"{label}: `{_num(node[key])}`")
        if isinstance(node.get("discriminator"), dict):
            notes.append(f"Discriminator: `{node['discriminator'].get('propertyName', '')}`")
        if node.get("readOnly"):
            notes.append("Read-only")
        if node.get("writeOnly"):
            notes.append("Write-only")
        if node.get("deprecated"):
            notes.append("⚠️ Deprecated")
    return list(dict.fromkeys(notes))


def describe(schema: dict) -> str:
    parts = [schema.get("description", "")] + constraints(schema)
    return "<br>".join(p for p in parts if p) or "-"


def example_value(
    spec: dict, schema: dict | None, depth: int = 0, seen: tuple[str, ...] = ()
) -> Any:
    """Build a sample JSON value from a schema (cycle-safe)."""
    if not schema or depth > 8:
        return None
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in seen:
            return None
        return example_value(spec, _resolve(spec, ref), depth, seen + (ref,))
    if "example" in schema:
        return schema["example"]
    if isinstance(schema.get("examples"), list) and schema["examples"]:
        return schema["examples"][0]
    if "const" in schema:
        return schema["const"]
    if schema.get("default") is not None:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [s for s in schema[key] if s.get("type") != "null"]
            return example_value(spec, options[0] if options else None, depth, seen)
    if "allOf" in schema:
        merged: dict = {}
        for sub in schema["allOf"]:
            val = example_value(spec, sub, depth, seen)
            if isinstance(val, dict):
                merged.update(val)
            elif not merged:
                return val
        return merged

    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), None)
    if t == "array":
        return [example_value(spec, schema.get("items"), depth + 1, seen)]
    if t == "object" or "properties" in schema:
        props = schema.get("properties", {})
        if not props and isinstance(schema.get("additionalProperties"), dict):
            return {"key": example_value(spec, schema["additionalProperties"], depth + 1, seen)}
        return {n: example_value(spec, p, depth + 1, seen) for n, p in props.items()}
    return _PRIMITIVE_EXAMPLES.get(t)


def _media_example(spec: dict, media: dict) -> Any:
    if "example" in media:
        return media["example"]
    examples = media.get("examples")
    if isinstance(examples, dict) and examples:
        first = deref(spec, next(iter(examples.values())))
        if isinstance(first, dict) and "value" in first:
            return first["value"]
    return example_value(spec, media.get("schema"))


# --------------------------------------------------------------------------- #
# Field tables (supports nested inline objects)
# --------------------------------------------------------------------------- #
def _inline_object(info: dict) -> tuple[dict, str] | None:
    """Find an inline nested object (directly, in anyOf, or as array items)."""
    for node in _walk(info):
        if "$ref" in node:
            continue
        if node.get("properties"):
            return node, ""
        if node.get("type") == "array":
            for sub in _walk(node.get("items") or {}):
                if sub.get("properties"):
                    return sub, "[]"
    return None


def _field_rows(props: dict, required: set[str], prefix: str = "", depth: int = 0) -> list[str]:
    rows: list[str] = []
    for name, info in props.items():
        full = f"{prefix}{name}"
        default = f"`{json.dumps(info['default'])}`" if "default" in info else "-"
        rows.append(
            f"| **{_cell(full)}** | {_cell(type_label(info))} "
            f"| {'**Yes**' if name in required else 'No'} | {_cell(default)} | {_cell(describe(info))} |"
        )
        nested = _inline_object(info) if depth < 5 else None
        if nested:
            obj, suffix = nested
            rows += _field_rows(
                obj["properties"], set(obj.get("required", [])), f"{full}{suffix}.", depth + 1
            )
    return rows


def _fields_table(props: dict, required: set[str]) -> list[str]:
    return [
        "| Field | Type | Required | Default | Description |",
        "| --- | --- | --- | --- | --- |",
        *_field_rows(props, required),
        "",
    ]


# --------------------------------------------------------------------------- #
# Document header, security, overview
# --------------------------------------------------------------------------- #
def _header(spec: dict) -> list[str]:
    info = spec.get("info", {})
    lines = [f"# {info.get('title', 'API Documentation')}", ""]

    meta = []
    if info.get("version"):
        meta.append(f"**Version:** `{info['version']}`")
    if spec.get("openapi"):
        meta.append(f"**OpenAPI:** `{spec['openapi']}`")
    if meta:
        lines += [" · ".join(meta), ""]
    if info.get("summary"):
        lines += [f"_{info['summary']}_", ""]
    if info.get("description"):
        lines += [info["description"], ""]

    extras = []
    contact = info.get("contact", {})
    if contact:
        bits = [contact.get("name"), contact.get("email"), contact.get("url")]
        extras.append("* **Contact:** " + " · ".join(b for b in bits if b))
    lic = info.get("license", {})
    if lic:
        extras.append(
            f"* **License:** [{lic.get('name', '')}]({lic['url']})" if lic.get("url")
            else f"* **License:** {lic.get('name', '')}"
        )
    if info.get("termsOfService"):
        extras.append(f"* **Terms of service:** {info['termsOfService']}")
    ext = spec.get("externalDocs", {})
    if ext.get("url"):
        extras.append(f"* **External docs:** [{ext.get('description') or ext['url']}]({ext['url']})")
    if extras:
        lines += extras + [""]

    servers = spec.get("servers", [])
    if servers:
        lines += ["**Servers**", ""]
        lines += [f"* `{s.get('url', '')}` {s.get('description', '')}".rstrip() for s in servers]
        lines.append("")
    return lines


def _effective_security(spec: dict, op: dict) -> list[dict]:
    reqs = op["security"] if "security" in op else spec.get("security", [])
    return [r for r in reqs if r]  # empty requirement object = optional auth


def _security_label(reqs: list[dict]) -> str:
    alts = []
    for req in reqs:
        parts = []
        for name, scopes in req.items():
            parts.append(f"`{name}`" + (f" (scopes: {', '.join(scopes)})" if scopes else ""))
        alts.append(" + ".join(parts))
    return " **or** ".join(alts)


def _auth_section(spec: dict) -> list[str]:
    schemes = spec.get("components", {}).get("securitySchemes", {})
    if not schemes:
        return []
    lines = ["## Authentication", "", "| Scheme | Type | Details |", "| --- | --- | --- |"]
    for name, s in schemes.items():
        details: list[str] = []
        if s.get("description"):
            details.append(s["description"])
        for key in ("scheme", "bearerFormat", "in", "name", "openIdConnectUrl"):
            if key in s:
                details.append(f"{key}: `{s[key]}`")
        for flow_name, flow in (s.get("flows") or {}).items():
            bits = [f"{flow_name}"]
            for key in ("authorizationUrl", "tokenUrl", "refreshUrl"):
                if key in flow:
                    bits.append(f"{key}: `{flow[key]}`")
            if flow.get("scopes"):
                bits.append("scopes: " + ", ".join(f"`{k}`" for k in flow["scopes"]))
            details.append("flow " + " · ".join(bits))
        lines.append(
            f"| **{_cell(name)}** | `{s.get('type', '')}` | {_cell('<br>'.join(details) or '-')} |"
        )
    return lines + [""]


# --------------------------------------------------------------------------- #
# Operations
# --------------------------------------------------------------------------- #
def iter_operations(spec: dict, key: str = "paths") -> Iterator[tuple[str, str, dict, dict]]:
    """Yield (METHOD, path, operation, path_item) for paths or webhooks."""
    for path, item in spec.get(key, {}).items():
        item = deref(spec, item)
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() in HTTP_METHODS and isinstance(op, dict):
                yield method.upper(), path, op, item


def _merged_params(spec: dict, path_item: dict, op: dict) -> list[dict]:
    merged: dict[tuple, dict] = {}
    for raw in [*path_item.get("parameters", []), *op.get("parameters", [])]:
        p = deref(spec, raw)
        if isinstance(p, dict):
            merged[(p.get("name"), p.get("in"))] = p  # operation overrides path level
    return list(merged.values())


def _params_section(spec: dict, params: list[dict]) -> list[str]:
    lines = [
        "##### Parameters",
        "",
        "| Name | In | Required | Type | Description |",
        "| --- | --- | --- | --- | --- |",
    ]
    for p in params:
        schema = p.get("schema") or {}
        notes = [p.get("description") or schema.get("description", "")]
        notes += constraints(schema)
        if p.get("deprecated"):
            notes.append("⚠️ Deprecated")
        if "example" in p:
            notes.append(f"Example: `{json.dumps(p['example'])}`")
        if "default" in schema:
            notes.append(f"Default: `{json.dumps(schema['default'])}`")
        required = p.get("required") or p.get("in") == "path"
        lines.append(
            f"| **{_cell(p.get('name', ''))}** | {p.get('in', '')} | {'Yes' if required else 'No'} "
            f"| {_cell(type_label(schema))} | {_cell('<br>'.join(dict.fromkeys(n for n in notes if n)) or '-')} |"
        )
    return lines + [""]


def _json_block(value: Any) -> list[str]:
    return ["```json", json.dumps(value, indent=2, ensure_ascii=False), "```", ""]


def _body_section(spec: dict, body: dict) -> list[str]:
    body = deref(spec, body)
    lines = ["##### Request Body" + (" *(required)*" if body.get("required") else ""), ""]
    if body.get("description"):
        lines += [body["description"], ""]
    for content_type, media in body.get("content", {}).items():
        schema = media.get("schema") or {}
        lines += [f"**`{content_type}`** → {type_label(schema)}", ""]
        inline = schema if schema.get("properties") else None
        if inline:
            lines += _fields_table(inline["properties"], set(inline.get("required", [])))
        if "json" in content_type or "xml" in content_type or schema.get("properties"):
            lines += ["Example:", ""] + _json_block(_media_example(spec, media))
    return lines


def _responses_section(spec: dict, responses: dict) -> list[str]:
    lines = [
        "##### Responses",
        "",
        "| Code | Description | Content-Type | Schema |",
        "| --- | --- | --- | --- |",
    ]
    example: tuple[str, dict] | None = None
    header_notes: list[str] = []
    for code, raw in responses.items():
        resp = deref(spec, raw)
        desc = _cell(resp.get("description", ""))
        for hname, h in (resp.get("headers") or {}).items():
            h = deref(spec, h)
            header_notes.append(
                f"* `{code}` header `{hname}` — {type_label(h.get('schema'))}"
                + (f": {h['description']}" if h.get("description") else "")
            )
        content = resp.get("content", {})
        if not content:
            lines.append(f"| **{code}** | {desc} | - | - |")
            continue
        for ct, media in content.items():
            schema = media.get("schema") or {}
            lines.append(f"| **{code}** | {desc} | `{ct}` | {_cell(type_label(schema))} |")
            if (
                example is None
                and str(code).startswith("2")
                and "json" in ct
                and (schema or "example" in media or "examples" in media)
            ):
                example = (str(code), media)
    lines.append("")
    if header_notes:
        lines += ["**Response headers**", "", *header_notes, ""]
    if example:
        code, media = example
        lines += [f"Example `{code}` response:", ""] + _json_block(_media_example(spec, media))
    return lines


def _operation(
    spec: dict, method: str, path: str, op: dict, item: dict, heading: str
) -> list[str]:
    lines = [f"#### `{heading}`", ""]
    if op.get("deprecated"):
        lines += ["⚠️ **Deprecated**", ""]
    if op.get("summary"):
        lines += [f"**{op['summary']}**", ""]
    if op.get("description"):
        lines += [op["description"], ""]

    meta = []
    if op.get("tags"):
        meta.append("* **Tags:** " + ", ".join(f"`{t}`" for t in op["tags"]))
    if op.get("operationId"):
        meta.append(f"* **Operation ID:** `{op['operationId']}`")
    reqs = _effective_security(spec, op)
    if reqs:
        meta.append(f"* **Security:** {_security_label(reqs)}")
    if op.get("externalDocs", {}).get("url"):
        meta.append(f"* **Docs:** {op['externalDocs']['url']}")
    if meta:
        lines += meta + [""]

    params = _merged_params(spec, item, op)
    if params:
        lines += _params_section(spec, params)
    if op.get("requestBody"):
        lines += _body_section(spec, op["requestBody"])
    if op.get("responses"):
        lines += _responses_section(spec, op["responses"])
    return lines + ["---", ""]


def _grouped(spec: dict) -> dict[str, list[tuple[str, str, dict, dict]]]:
    groups: dict[str, list] = {t["name"]: [] for t in spec.get("tags", []) if "name" in t}
    for method, path, op, item in iter_operations(spec):
        groups.setdefault((op.get("tags") or ["default"])[0], []).append((method, path, op, item))
    return {k: v for k, v in groups.items() if v}


def _overview(spec: dict) -> list[str]:
    groups = _grouped(spec)
    if not groups:
        return []
    lines = [
        "## Endpoint Overview",
        "",
        "| Method | Path | Summary | Tags | Auth |",
        "| --- | --- | --- | --- | --- |",
    ]
    for ops in groups.values():
        for method, path, op, _ in ops:
            tags = ", ".join(f"`{t}`" for t in op.get("tags", [])) or "-"
            auth = "🔒" if _effective_security(spec, op) else "-"
            dep = " ⚠️" if op.get("deprecated") else ""
            link = f"[`{path}`](#{slugify(f'{method} {path}')})"
            lines.append(
                f"| **{method}** | {_cell(link)} | {_cell(op.get('summary', '-'))}{dep} | {tags} | {auth} |"
            )
    return lines + [""]


def _endpoints(spec: dict) -> list[str]:
    groups = _grouped(spec)
    if not groups:
        return []
    tag_meta = {t["name"]: t for t in spec.get("tags", []) if "name" in t}
    lines = ["## Endpoints", ""]
    for tag, ops in groups.items():
        lines += [f"### {tag}", ""]
        meta = tag_meta.get(tag, {})
        if meta.get("description"):
            lines += [meta["description"], ""]
        if meta.get("externalDocs", {}).get("url"):
            lines += [f"Docs: {meta['externalDocs']['url']}", ""]
        for method, path, op, item in ops:
            lines += _operation(spec, method, path, op, item, f"{method} {path}")
    return lines


def _webhooks(spec: dict) -> list[str]:
    ops = list(iter_operations(spec, "webhooks"))
    if not ops:
        return []
    lines = ["## Webhooks", ""]
    for method, name, op, item in ops:
        lines += _operation(spec, method, name, op, item, f"{method} {name}")
    return lines


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
def _schemas(spec: dict) -> list[str]:
    schemas = spec.get("components", {}).get("schemas", {})
    if not schemas:
        return []
    lines = ["## Schemas", ""]
    for name, schema in schemas.items():
        lines += [f"### `{name}`", ""]
        if schema.get("description"):
            lines += [schema["description"], ""]
        if schema.get("deprecated"):
            lines += ["⚠️ **Deprecated**", ""]

        if "enum" in schema:
            values = ", ".join(f"`{json.dumps(v)}`" for v in schema["enum"])
            lines += [f"**Type:** `{schema.get('type', 'string')}` · **Values:** {values}", ""]
            continue

        # Merge properties from allOf (inheritance / composition)
        props = dict(schema.get("properties", {}))
        required = set(schema.get("required", []))
        parents = []
        for sub in schema.get("allOf", []):
            if "$ref" in sub:
                parents.append(_ref_link(sub["$ref"]))
            else:
                props.update(sub.get("properties", {}))
                required |= set(sub.get("required", []))
        if parents:
            lines += ["**Extends:** " + ", ".join(parents), ""]

        if props:
            lines += _fields_table(props, required)
        else:
            lines += [f"**Type:** {type_label(schema)}", ""]
            notes = constraints(schema)
            if notes:
                lines += ["* " + n for n in notes] + [""]
    return lines


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def validate_spec(spec: Any) -> str | None:
    """Return an error message if `spec` isn't an OpenAPI 3.x document, else None."""
    if not isinstance(spec, dict):
        return "The JSON root must be an object."
    version = str(spec.get("openapi", ""))
    if not version:
        return "Missing `openapi` field, so this doesn't look like an OpenAPI spec."
    if not version.startswith("3"):
        return f"OpenAPI {version} is not supported. FastAPI generates OpenAPI 3.x."
    if "paths" not in spec:
        return "Missing `paths` section."
    return None


def spec_stats(spec: dict) -> dict[str, Any]:
    info = spec.get("info", {})
    return {
        "title": info.get("title", "-"),
        "version": info.get("version", "-"),
        "openapi": spec.get("openapi", "-"),
        "endpoints": sum(1 for _ in iter_operations(spec)),
        "schemas": len(spec.get("components", {}).get("schemas", {})),
    }


def endpoint_rows(spec: dict) -> list[dict[str, str]]:
    """Flat rows for a UI table."""
    return [
        {
            "Method": method,
            "Path": path,
            "Summary": op.get("summary", ""),
            "Tags": ", ".join(op.get("tags", [])),
            "Auth": "🔒" if _effective_security(spec, op) else "",
            "Deprecated": "⚠️" if op.get("deprecated") else "",
        }
        for method, path, op, _ in iter_operations(spec)
    ]


def openapi_to_markdown(spec: dict) -> str:
    lines: list[str] = []
    lines += _header(spec)
    lines += ["---", ""]
    lines += _overview(spec)
    lines += _auth_section(spec)
    lines += _endpoints(spec)
    lines += _webhooks(spec)
    lines += _schemas(spec)
    return "\n".join(lines).rstrip() + "\n"
