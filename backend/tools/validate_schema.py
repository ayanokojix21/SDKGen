"""
Schema Validator — Deterministic post-validation for the Architect's api_schema.

Runs after the Architect LLM produces its output. Catches structural issues
the LLM might miss and auto-fixes trivial ones (e.g. trailing slash on base_url,
missing full_url). Returns a report of what was validated, what was fixed,
and what is still broken.
"""

import re
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def validate_schema(schema: dict) -> dict:
    """
    Validate and auto-fix an api_schema dict.

    Returns:
        {
            "valid": bool,
            "schema": dict,       # the (possibly auto-fixed) schema
            "fixes": [str],       # descriptions of auto-applied fixes
            "errors": [str],      # unrecoverable errors
        }
    """
    fixes: list[str] = []
    errors: list[str] = []

    # ── Validate top-level fields ────────────────────────────────────────
    if not isinstance(schema, dict):
        return {"valid": False, "schema": schema, "fixes": [], "errors": ["Schema is not a dict"]}

    # base_url
    base_url = schema.get("base_url", "")
    if not base_url:
        errors.append("base_url is missing or empty")
    else:
        base_url = _fix_base_url(base_url, fixes)
        schema["base_url"] = base_url

    # auth
    auth = schema.get("auth")
    if auth is None:
        schema["auth"] = {"type": "none", "location": "none", "key_name": "", "example": ""}
        fixes.append("Added default auth block with type=none")
    elif not isinstance(auth, dict):
        errors.append(f"auth is not a dict: {type(auth).__name__}")
    else:
        auth_type = auth.get("type", "none")
        if auth_type not in ("none", "api_key", "bearer", "basic", "oauth2", "bearer_token"):
            fixes.append(f"Normalized unknown auth type '{auth_type}' → 'none'")
            auth["type"] = "none"
        # Normalize bearer_token → bearer
        if auth_type == "bearer_token":
            auth["type"] = "bearer"
            fixes.append("Normalized auth type 'bearer_token' → 'bearer'")

    # endpoints
    endpoints = schema.get("endpoints")
    if endpoints is None:
        schema["endpoints"] = []
        fixes.append("Added empty endpoints array (was missing)")
        endpoints = []
    elif not isinstance(endpoints, list):
        errors.append(f"endpoints is not a list: {type(endpoints).__name__}")
        return {"valid": False, "schema": schema, "fixes": fixes, "errors": errors}

    # ── Validate each endpoint ───────────────────────────────────────────
    seen_names: set[str] = set()
    valid_endpoints: list[dict] = []

    for i, ep in enumerate(endpoints):
        if not isinstance(ep, dict) or not ep:
            fixes.append(f"Removed empty/invalid endpoint at index {i}")
            continue

        ep_errors = _validate_endpoint(ep, i, base_url, seen_names, fixes)
        errors.extend(ep_errors)
        valid_endpoints.append(ep)

    schema["endpoints"] = valid_endpoints

    is_valid = len(errors) == 0
    if fixes:
        logger.info(f"Schema validation: {len(fixes)} auto-fixes applied")
    if errors:
        logger.warning(f"Schema validation: {len(errors)} errors found")

    return {
        "valid": is_valid,
        "schema": schema,
        "fixes": fixes,
        "errors": errors,
    }


def _fix_base_url(base_url: str, fixes: list[str]) -> str:
    """Normalize base_url: ensure scheme, strip trailing slash."""
    original = base_url

    # Add scheme if missing
    if not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url
        fixes.append(f"Added https:// scheme to base_url: '{original}' → '{base_url}'")

    # Strip trailing slash
    if base_url.endswith("/"):
        base_url = base_url.rstrip("/")
        fixes.append(f"Removed trailing slash from base_url")

    # Validate it parses as a URL
    parsed = urlparse(base_url)
    if not parsed.netloc:
        fixes.append(f"base_url has no netloc after parsing: '{base_url}'")

    return base_url


def _validate_endpoint(
    ep: dict,
    index: int,
    base_url: str,
    seen_names: set[str],
    fixes: list[str],
) -> list[str]:
    """Validate and auto-fix a single endpoint. Returns list of errors."""
    errors: list[str] = []
    prefix = f"endpoints[{index}]"

    # ── name ─────────────────────────────────────────────────────────────
    name = ep.get("name", "")
    if not name:
        # Try to generate from method + path
        method = ep.get("method", "GET").upper()
        path = ep.get("path", "")
        if path:
            name = _generate_name(method, path)
            ep["name"] = name
            fixes.append(f"{prefix}: Generated name '{name}' from {method} {path}")
        else:
            errors.append(f"{prefix}: Missing name and path — cannot generate name")

    if name in seen_names:
        errors.append(f"{prefix}: Duplicate endpoint name '{name}'")
    seen_names.add(name)

    # ── method ───────────────────────────────────────────────────────────
    method = ep.get("method", "")
    if not method:
        ep["method"] = "GET"
        fixes.append(f"{prefix}: Defaulted empty method to GET")
        method = "GET"
    else:
        upper = method.upper()
        if upper != method:
            ep["method"] = upper
            fixes.append(f"{prefix}: Uppercased method '{method}' → '{upper}'")
            method = upper
        if method not in VALID_METHODS:
            errors.append(f"{prefix}: Invalid method '{method}'")

    # ── path ─────────────────────────────────────────────────────────────
    path = ep.get("path", "")
    if not path:
        errors.append(f"{prefix}: Missing path")
    elif not path.startswith("/"):
        ep["path"] = "/" + path
        fixes.append(f"{prefix}: Prepended '/' to path: '{path}' → '/{path}'")
        path = "/" + path

    # ── full_url ─────────────────────────────────────────────────────────
    if base_url and path:
        expected_full_url = base_url + path
        current_full_url = ep.get("full_url", "")
        if current_full_url != expected_full_url:
            ep["full_url"] = expected_full_url
            if current_full_url:
                fixes.append(f"{prefix}: Fixed full_url: '{current_full_url}' → '{expected_full_url}'")
            else:
                fixes.append(f"{prefix}: Generated full_url: '{expected_full_url}'")

    # ── path_params vs path ──────────────────────────────────────────────
    path_param_pattern = re.compile(r"\{(\w+)\}")
    path_param_names_in_path = set(path_param_pattern.findall(path))

    path_params = ep.get("path_params") or []
    if not isinstance(path_params, list):
        path_params = []
        ep["path_params"] = path_params
        fixes.append(f"{prefix}: Reset path_params to empty array (was not a list)")

    declared_path_param_names = {p.get("name") for p in path_params if isinstance(p, dict)}

    # Check for path params in path that aren't declared
    for pp_name in path_param_names_in_path - declared_path_param_names:
        path_params.append({
            "name": pp_name,
            "type": "string",
            "required": True,
            "description": "",
        })
        fixes.append(f"{prefix}: Added missing path_param '{pp_name}' (found in path)")
    ep["path_params"] = path_params

    # Check for declared path params not in path
    for pp_name in declared_path_param_names - path_param_names_in_path:
        errors.append(f"{prefix}: path_param '{pp_name}' declared but not in path '{path}'")

    # ── Ensure all path_params are required=True ─────────────────────────
    for pp in path_params:
        if isinstance(pp, dict) and not pp.get("required", False):
            pp["required"] = True
            fixes.append(f"{prefix}: Set path_param '{pp.get('name')}' to required=True")

    # ── body on GET/DELETE ───────────────────────────────────────────────
    if method in ("GET", "DELETE") and ep.get("body") is not None:
        ep["body"] = None
        fixes.append(f"{prefix}: Removed body from {method} endpoint")

    # ── Ensure arrays exist ──────────────────────────────────────────────
    for field in ("headers", "query_params", "path_params"):
        if not isinstance(ep.get(field), list):
            ep[field] = ep.get(field) if isinstance(ep.get(field), list) else []

    return errors


def _generate_name(method: str, path: str) -> str:
    """
    Generate a snake_case function name from method + path.

    Examples:
        GET  /users           → get_users
        POST /users           → create_user
        GET  /users/{id}      → get_user_by_id
        PUT  /users/{id}      → update_user
        DELETE /users/{id}    → delete_user
    """
    # Strip path params for name generation
    clean_path = re.sub(r"/\{(\w+)\}", lambda m: f"_by_{m.group(1)}", path)

    # Remove leading slash, replace remaining slashes with underscores
    clean_path = clean_path.strip("/").replace("/", "_")

    # Remove any non-alphanumeric chars except underscores
    clean_path = re.sub(r"[^a-zA-Z0-9_]", "", clean_path)

    # Map method to prefix
    method_prefix = {
        "GET": "get",
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
    }
    prefix = method_prefix.get(method, method.lower())

    # Avoid names like "get_get_users"
    if clean_path.startswith(prefix + "_"):
        return clean_path

    return f"{prefix}_{clean_path}" if clean_path else prefix
