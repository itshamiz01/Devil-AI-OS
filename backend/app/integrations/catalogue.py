"""The machine-readable API contract catalogue (Expansion F02).

Built from the live FastAPI application. This is the fix for two of
the Gate 2 review's §2 findings:

1. **Permission names were invisible in OpenAPI.** ``require_permission``
   now records the permission on its dependency closure
   (``__permission__``); :func:`describe_route_auth` reads it back,
   ``create_app`` publishes it as the ``x-required-permission``
   OpenAPI extension on every operation, and this catalogue exposes
   it as data.
3. **Two authorization depths existed invisibly.** Every operation
   is labelled with its depth: ``route`` (a permission is declared
   at the route), ``authenticated`` (a principal is required but no
   route permission is declared — authorization, if any, happens
   in the service layer), or ``public`` (no principal required).
   The catalogue states the depth honestly instead of letting a
   consumer assume route metadata describes access.

Enumeration note: this FastAPI version defers router inclusion —
``app.routes`` holds ``_IncludedRouter`` entries whose
``effective_candidates()`` yields the materialised route contexts
(full prefixed path, dependant, openapi_extra). The helpers below
walk those; plain routes (docs, the SPA mount) are handled too.
"""
from __future__ import annotations


def iter_effective_routes(app):
    """Yield route-like objects (path, methods, dependant, tags,
    openapi_extra) for every route the application serves."""
    for entry in app.routes:
        if hasattr(entry, "effective_candidates"):
            yield from entry.effective_candidates()
        else:
            yield entry


def _walk_dependencies(dependant) -> list:
    found = []
    for dep in getattr(dependant, "dependencies", []) or []:
        call = getattr(dep, "call", None)
        if call is not None:
            found.append(call)
        found.extend(_walk_dependencies(dep))
    return found


def describe_route_auth(route) -> tuple[str | None, str]:
    """(required_permission | None, authorization_depth) for a route."""
    from ..api.dependencies import get_principal

    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return None, "public"
    calls = _walk_dependencies(dependant)
    for call in calls:
        permission = getattr(call, "__permission__", None)
        if permission is not None:
            return str(permission), "route"
    if any(call is get_principal for call in calls):
        return None, "authenticated"
    return None, "public"


def build_catalogue(app) -> dict:
    """The full operation catalogue for a FastAPI app instance."""
    operations = []
    for route in iter_effective_routes(app):
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path or not path.startswith("/api/"):
            continue
        permission, depth = describe_route_auth(route)
        for method in sorted(methods):
            if method in ("HEAD", "OPTIONS"):
                continue
            operations.append({
                "path": path, "method": method,
                "required_permission": permission,
                "authorization_depth": depth,
                "tags": list(getattr(route, "tags", []) or []),
            })
    operations.sort(key=lambda op: (op["path"], op["method"]))
    by_depth: dict[str, int] = {}
    for op in operations:
        by_depth[op["authorization_depth"]] = by_depth.get(op["authorization_depth"], 0) + 1
    return {
        "operations": operations,
        "count": len(operations),
        "by_authorization_depth": by_depth,
        "note": ("required_permission is the P-01 permission declared "
                 "at the route (published in OpenAPI as "
                 "x-required-permission). 'authenticated' operations "
                 "declare no route permission — authorization, if "
                 "any, is enforced in the service layer (review §2 "
                 "finding 3, dispositioned: depths are now "
                 "machine-readable rather than assumed)."),
    }


def decorate_openapi(app) -> None:
    """Publish permission + depth metadata on every operation's
    OpenAPI entry (additive extensions; no behaviour change)."""
    for route in iter_effective_routes(app):
        methods = getattr(route, "methods", None)
        if not methods or not getattr(route, "path", "").startswith("/api/"):
            continue
        permission, depth = describe_route_auth(route)
        extra = dict(getattr(route, "openapi_extra", None) or {})
        if permission is not None:
            extra["x-required-permission"] = permission
        extra["x-authorization-depth"] = depth
        route.openapi_extra = extra
