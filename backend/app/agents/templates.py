"""Agent template definitions and their versions (P-04 Stage 3).

A template is the only route to an agent: Stage 4's creation engine refuses to
build an agent from anything that is not a **published** template whose chosen
version carries a **valid** verdict. That makes this module the validation gate
the brief asks for, and it is a gate in code rather than in a prompt — nothing
here calls a model, so a verdict cannot be argued with.

Three rules shape the implementation.

**A version row is immutable.** Revising a template writes version *n+1*; it
never edits version *n*. An agent created from version 3 must remain explainable
by version 3 for as long as it exists, which is impossible if the document can
change underneath it. The single exception is the validation verdict, which is
evidence *about* a version rather than part of it, and is stored in its own
column.

**Validation is recorded, not merely returned.** A refusal that exists only in
an HTTP response cannot be audited later, so the verdict and its issues are
persisted next to the configuration, together with a hash of the exact document
that was judged. If the document ever differs from that hash, the verdict does
not apply to it.

**Status transitions are a closed graph.** `draft -> published -> deprecated`,
and `deprecated -> draft`. Publishing an unvalidated or invalid version is
refused; restoring a deprecated template returns it to `draft`, never straight
back to `published`, so a template that was withdrawn cannot resume governing
agent creation without a deliberate act.

Capability checks against the `agent_capabilities` catalog are **not** performed
here: that catalog is empty until Stage 5 populates and governs it, and a check
against an empty catalog would either refuse every template or pass every one.
Stage 3 validates structure and intent; Stage 5 adds the capability verdict.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from pydantic import ValidationError

from ..core.config import Settings
from ..core.exceptions import AppError, ConflictError, NotFoundError
from ..database.connection import Database
from ..database.repositories import AgentTemplateRepo
from ..permissions.models import canonical_payload_hash
from .schemas import TemplateConfiguration

__all__ = [
    "TEMPLATE_TRANSITIONS",
    "TemplateService",
    "TemplateTransitionError",
    "TemplateValidationError",
    "configuration_fingerprint",
    "diff_configurations",
]

#: Closed status graph for a template. Anything not listed is refused.
TEMPLATE_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"published", "deprecated"}),
    "published": frozenset({"deprecated"}),
    "deprecated": frozenset({"draft"}),
}

UNVALIDATED = "unvalidated"
VALID = "valid"
INVALID = "invalid"


class TemplateTransitionError(ConflictError):
    """A status change the template graph does not allow.

    Subclasses ``ConflictError`` so it keeps the 409 mapping and the existing
    error handler, but carries its own code: reusing ``InvalidTransitionError``
    would report ``invalid_task_transition`` for a template, a task-specific
    code that sends a reader looking in the wrong subsystem.
    """

    code = "invalid_template_transition"


class TemplateValidationError(AppError):
    """A configuration that cannot be stored at all.

    Distinct from an *invalid verdict*: this is a document that does not parse
    as a :class:`TemplateConfiguration`, so there is nothing to judge. It is an
    :class:`AppError` with a 422 so the application's existing error handler
    renders it in the standard envelope instead of falling through to the
    generic 500 handler.
    """

    status_code = 422
    code = "template_configuration_invalid"

    def __init__(self, message: str, issues: Sequence[str]) -> None:
        super().__init__(message, {"issues": list(issues)})
        self.issues = list(issues)


def configuration_fingerprint(template_id: str, configuration: dict[str, Any]) -> str:
    """Hash of the exact document a verdict was reached about.

    Reuses the approval subsystem's canonical hash so the project has one
    canonicalisation rather than two: the action names the operation, the
    resource names the template, and the configuration is the parameter set.
    """
    return canonical_payload_hash(
        "agent_template.validate", template_id, [], dict(configuration)
    )


def diff_configurations(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Field-level difference between two template configurations.

    Top-level keys only, and deterministic: the same two documents always
    produce the same diff, with no model involved. Nested values are compared
    as wholes, because a partial structural diff of an arbitrary JSON schema
    would be harder to read than the two values side by side.
    """
    added = sorted(k for k in right if k not in left)
    removed = sorted(k for k in left if k not in right)
    changed = {
        k: {"from": left[k], "to": right[k]}
        for k in sorted(set(left) & set(right))
        if json.dumps(left[k], sort_keys=True, default=str)
        != json.dumps(right[k], sort_keys=True, default=str)
    }
    return {"added": added, "removed": removed, "changed": changed,
            "identical": not (added or removed or changed)}


class TemplateService:
    """Templates and versions, with the validation gate that governs them."""

    def __init__(self, db: Database, settings: Settings, bus: Any = None) -> None:
        self.db = db
        self.settings = settings
        self.bus = bus

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    async def list_templates(self, *, status: str | None = None, category: str | None = None,
                             limit: int = 50, offset: int = 0) -> tuple[Sequence[Any], int]:
        async with self.db.session_factory() as session:
            repo = AgentTemplateRepo(session)
            rows = await repo.list(limit, offset, status=status, category=category)
            total = await repo.count(status=status, category=category)
        return rows, total

    async def get_template(self, template_id: str) -> Any:
        async with self.db.session_factory() as session:
            row = await AgentTemplateRepo(session).get(template_id)
        if row is None:
            raise NotFoundError("Agent template not found", {"template_id": template_id})
        return row

    async def list_versions(self, template_id: str) -> Sequence[Any]:
        await self.get_template(template_id)
        async with self.db.session_factory() as session:
            return await AgentTemplateRepo(session).list_versions(template_id)

    async def get_version(self, template_id: str, version: int) -> Any:
        await self.get_template(template_id)
        async with self.db.session_factory() as session:
            row = await AgentTemplateRepo(session).get_version(template_id, version)
        if row is None:
            raise NotFoundError("Template version not found",
                                {"template_id": template_id, "version": version})
        return row

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    async def create_template(self, *, name: str, category: str, description: str = "",
                              configuration: dict[str, Any],
                              created_by: str | None = None) -> dict[str, Any]:
        """Create a draft template holding its first version.

        The configuration must parse; a document that does not is refused
        outright rather than stored as an unjudgeable version. The new version
        starts ``unvalidated`` — creating a template does not validate it.
        """
        parsed = self._parse(configuration)
        async with self.db.session_factory() as session:
            repo = AgentTemplateRepo(session)
            if await repo.by_name(name) is not None:
                raise ConflictError("A template with that name already exists", {"name": name})
            template = await repo.create(name=name, category=category,
                                         description=description, status="draft")
            version = await repo.add_version(
                template_id=template.id, version=1, configuration=parsed,
                created_by=created_by)
            await repo.set_current_version(template.id, 1)
            await session.commit()
        await self._emit("AgentTemplateCreated", {
            "template_id": template.id, "name": template.name, "version": 1,
            "status": template.status,
        })
        return {"template": template, "version": version}

    async def revise(self, template_id: str, *, configuration: dict[str, Any],
                     created_by: str | None = None, reason: str = "") -> Any:
        """Append the next version. Never edits an existing one."""
        parsed = self._parse(configuration)
        async with self.db.session_factory() as session:
            repo = AgentTemplateRepo(session)
            template = await repo.get(template_id)
            if template is None:
                raise NotFoundError("Agent template not found", {"template_id": template_id})
            if template.status == "deprecated":
                raise ConflictError(
                    "A deprecated template cannot be revised; restore it to draft first",
                    {"template_id": template_id, "status": template.status})
            number = await repo.latest_version(template_id) + 1
            version = await repo.add_version(
                template_id=template_id, version=number, configuration=parsed,
                created_by=created_by)
            await session.commit()
        await self._emit("AgentTemplateRevised", {
            "template_id": template_id, "version": number,
            "reason": reason, "current_version": template.current_version,
        })
        return version

    async def validate(self, template_id: str, version: int | None = None) -> dict[str, Any]:
        """Judge a version and persist the verdict with its evidence.

        ``version`` defaults to the newest one. The verdict is written even when
        it is negative: an invalid template must be readable as invalid, with
        the reasons, rather than silently absent.
        """
        async with self.db.session_factory() as session:
            repo = AgentTemplateRepo(session)
            template = await repo.get(template_id)
            if template is None:
                raise NotFoundError("Agent template not found", {"template_id": template_id})
            number = version if version is not None else await repo.latest_version(template_id)
            row = await repo.get_version(template_id, number)
            if row is None:
                raise NotFoundError("Template version not found",
                                    {"template_id": template_id, "version": number})
            issues, warnings = self._policy_check(row.configuration_json or {})
            verdict = INVALID if issues else VALID
            details = {
                "issues": issues,
                "warnings": warnings,
                "configuration_fingerprint": configuration_fingerprint(
                    template_id, row.configuration_json or {}),
                "checks_performed": (
                    "structure", "intent", "output_contract", "capability_duplicates"
                ),
                "capability_catalog_checked": False,
                "capability_catalog_note": (
                    "the capability catalog is populated and governed in P-04 Stage 5; "
                    "until then no capability key is cross-checked against it"
                ),
            }
            await repo.set_validation(row.id, verdict, details)
            await session.commit()
        await self._emit("AgentTemplateValidated", {
            "template_id": template_id, "version": number, "validation_status": verdict,
            "issue_count": len(issues), "warning_count": len(warnings),
        })
        return {"template_id": template_id, "version": number,
                "validation_status": verdict, "details": details}

    async def publish(self, template_id: str, version: int | None = None) -> Any:
        """Publish a template at a version that has been judged valid."""
        async with self.db.session_factory() as session:
            repo = AgentTemplateRepo(session)
            template = await repo.get(template_id)
            if template is None:
                raise NotFoundError("Agent template not found", {"template_id": template_id})
            number = version if version is not None else await repo.latest_version(template_id)
            row = await repo.get_version(template_id, number)
            if row is None:
                raise NotFoundError("Template version not found",
                                    {"template_id": template_id, "version": number})
            if row.validation_status != VALID:
                raise ConflictError(
                    f"Only a version with a valid verdict can be published; "
                    f"version {number} is '{row.validation_status}'",
                    {"template_id": template_id, "version": number,
                     "validation_status": row.validation_status,
                     "issues": (row.validation_details_json or {}).get("issues", [])})
            self._assert_transition(template.status, "published")
            await repo.set_status(template_id, "published", current_version=number)
            await session.commit()
            template.status = "published"
            template.current_version = number
        await self._emit("AgentTemplatePublished", {
            "template_id": template_id, "version": number,
            "fingerprint": (row.validation_details_json or {}).get("configuration_fingerprint"),
        })
        return template

    async def deprecate(self, template_id: str, *, reason: str = "") -> Any:
        async with self.db.session_factory() as session:
            repo = AgentTemplateRepo(session)
            template = await repo.get(template_id)
            if template is None:
                raise NotFoundError("Agent template not found", {"template_id": template_id})
            self._assert_transition(template.status, "deprecated")
            await repo.set_status(template_id, "deprecated")
            await session.commit()
            template.status = "deprecated"
        await self._emit("AgentTemplateDeprecated", {
            "template_id": template_id, "reason": reason})
        return template

    async def restore(self, template_id: str) -> Any:
        """Bring a deprecated template back as a draft.

        Never straight back to ``published``: a template that was withdrawn
        governs agent creation, so resuming that authority takes a deliberate
        second act (validate, then publish).
        """
        async with self.db.session_factory() as session:
            repo = AgentTemplateRepo(session)
            template = await repo.get(template_id)
            if template is None:
                raise NotFoundError("Agent template not found", {"template_id": template_id})
            self._assert_transition(template.status, "draft")
            await repo.set_status(template_id, "draft")
            await session.commit()
            template.status = "draft"
        await self._emit("AgentTemplateRestored", {"template_id": template_id})
        return template

    async def clone(self, template_id: str, *, new_name: str, version: int | None = None,
                    created_by: str | None = None) -> dict[str, Any]:
        """Copy a version's configuration into a new draft template.

        The clone starts ``unvalidated`` even when the source was valid: the
        verdict is evidence about one document under one template id, and it is
        not transferable by assertion.
        """
        async with self.db.session_factory() as session:
            repo = AgentTemplateRepo(session)
            source = await repo.get(template_id)
            if source is None:
                raise NotFoundError("Agent template not found", {"template_id": template_id})
            number = version if version is not None else await repo.latest_version(template_id)
            row = await repo.get_version(template_id, number)
            if row is None:
                raise NotFoundError("Template version not found",
                                    {"template_id": template_id, "version": number})
            if await repo.by_name(new_name) is not None:
                raise ConflictError("A template with that name already exists",
                                    {"name": new_name})
            template = await repo.create(
                name=new_name, category=source.category,
                description=f"Cloned from {source.name} version {number}", status="draft")
            new_version = await repo.add_version(
                template_id=template.id, version=1,
                configuration=dict(row.configuration_json or {}), created_by=created_by)
            await repo.set_current_version(template.id, 1)
            await session.commit()
        await self._emit("AgentTemplateCreated", {
            "template_id": template.id, "name": template.name, "version": 1,
            "status": template.status, "cloned_from": {"template_id": template_id,
                                                       "version": number},
        })
        return {"template": template, "version": new_version,
                "cloned_from": {"template_id": template_id, "version": number}}

    async def compare(self, template_id: str, left: int, right: int) -> dict[str, Any]:
        """Deterministic field diff of two versions of one template."""
        a = await self.get_version(template_id, left)
        b = await self.get_version(template_id, right)
        diff = diff_configurations(a.configuration_json or {}, b.configuration_json or {})
        diff.update({"template_id": template_id, "left": left, "right": right,
                     "left_validation_status": a.validation_status,
                     "right_validation_status": b.validation_status})
        return diff

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _parse(self, configuration: dict[str, Any]) -> dict[str, Any]:
        """Store the *validated shape*, not whatever the caller sent.

        Round-tripping through the model drops unknown keys and applies the
        declared defaults, so two callers sending equivalent documents produce
        identical stored configuration — which is what makes the fingerprint
        meaningful.
        """
        try:
            parsed = TemplateConfiguration.model_validate(configuration)
        except ValidationError as exc:
            issues = [
                f"{'.'.join(str(p) for p in e['loc']) or 'configuration'}: {e['msg']}"
                for e in exc.errors()
            ]
            raise TemplateValidationError("Template configuration is not valid", issues) from exc
        return parsed.model_dump(mode="json")

    def _policy_check(self, configuration: dict[str, Any]) -> tuple[list[str], list[str]]:
        """Checks a parse cannot express. Returns (issues, warnings)."""
        issues: list[str] = []
        warnings: list[str] = []
        for field in ("role_definition", "mission", "system_instruction"):
            value = configuration.get(field)
            if not isinstance(value, str) or not value.strip():
                issues.append(f"{field} must be a non-empty string; a template that "
                              f"cannot describe its own role cannot be assigned work")
        output_schema = configuration.get("expected_output_schema")
        if not isinstance(output_schema, dict) or not output_schema:
            issues.append("expected_output_schema must be a non-empty object; assignment "
                          "enforcement validates results against it, so without it no "
                          "result can be checked")
        for field in ("allowed_capabilities", "restricted_capabilities"):
            keys = configuration.get(field) or []
            duplicates = sorted({k for k in keys if keys.count(k) > 1})
            if duplicates:
                issues.append(f"{field} lists duplicate keys: {', '.join(duplicates)}")
        if not (configuration.get("allowed_capabilities") or []):
            warnings.append("the template grants no capability, so it can only be "
                            "assigned work that requires none")
        return issues, warnings

    def _assert_transition(self, current: str, target: str) -> None:
        if target not in TEMPLATE_TRANSITIONS.get(current, frozenset()):
            raise TemplateTransitionError(
                f"A template cannot move from '{current}' to '{target}'",
                {"current": current, "target": target,
                 "allowed": sorted(TEMPLATE_TRANSITIONS.get(current, frozenset()))})

    async def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.bus is None:
            return
        await self.bus.publish_new(event_type, "agent_templates", payload)
