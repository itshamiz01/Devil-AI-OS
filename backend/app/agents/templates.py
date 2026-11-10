"""Agent template system (§6): CRUD over versioned templates.

Rules enforced here:
- Configurations are IMMUTABLE per version. An update writes a NEW draft
  version; it never edits a written version in place.
- Publishing requires validation to pass. An invalid template can never
  be published, and an unpublished template can never produce an agent.
- Agents pin (template_id, published_version). Publishing a newer version
  changes nothing for existing agents; a controlled per-agent update is
  the only way an agent moves (see the factory service, §13).
- Restore writes a NEW version whose configuration copies an older one —
  history is append-only, never rewritten.
"""
from __future__ import annotations

import copy

from ..database.models.agents import AgentTemplate, AgentTemplateVersion
from ..database.models.base import utcnow
from ..database.repositories.agents import CapabilityRepository, TemplateRepository
from ..database.repositories.intelligence import ModelProfileRepository
from ..permissions.models import Principal
from .errors import TemplateInvalidError
from .validation import validate_template_configuration


class TemplateService:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    # ------------------------------------------------------------- helpers
    def _ceilings(self, settings: dict) -> dict:
        return {
            "max_concurrent_tasks_per_agent": settings["max_concurrent_tasks_per_agent"],
            "max_template_task_seconds": settings["max_template_task_seconds"],
            "max_template_memory_budget_mb": settings["max_template_memory_budget_mb"],
        }

    def _run_validation(self, session, config: dict, settings: dict) -> list[str]:
        levels = {c.name: c.approval_level for c in CapabilityRepository(session).list()}
        profiles = {p.name for p in ModelProfileRepository(session).list()}
        return validate_template_configuration(
            config, capability_levels=levels, model_profile_names=profiles,
            ceilings=self._ceilings(settings))

    # ---------------------------------------------------------------- CRUD
    def create(self, principal: Principal, *, name: str, category: str,
               description: str | None, configuration: dict, settings: dict) -> AgentTemplate:
        session = self._session_factory()
        try:
            repo = TemplateRepository(session)
            if repo.get_by_name(name) is not None:
                raise TemplateInvalidError(
                    f"template name '{name}' already exists",
                    details={"error_category": "TEMPLATE_INVALID"})
            template = AgentTemplate(
                name=name, category=category, description=description, status="draft",
                current_version=1, published_version=None,
                created_by_type=principal.type.value, created_by_id=principal.id)
            repo.add(template)
            errors = self._run_validation(session, configuration, settings)
            version = AgentTemplateVersion(
                template_id=template.id, version=1,
                configuration=copy.deepcopy(configuration),
                validation_status="valid" if not errors else "invalid",
                validation_errors=errors,
                created_by_type=principal.type.value, created_by_id=principal.id)
            TemplateRepository(session).add(version)
            return template
        finally:
            session.close()

    def get(self, template_id: str) -> AgentTemplate:
        session = self._session_factory()
        try:
            template = TemplateRepository(session).get(template_id)
            if template is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"template {template_id} not found")
            return template
        finally:
            session.close()

    def list(self, limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            return TemplateRepository(session).list(limit, offset)
        finally:
            session.close()

    def get_version(self, template_id: str, version: int) -> AgentTemplateVersion:
        session = self._session_factory()
        try:
            row = TemplateRepository(session).version(template_id, version)
            if row is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"template {template_id} version {version} not found")
            return row
        finally:
            session.close()

    def list_versions(self, template_id: str) -> list[AgentTemplateVersion]:
        session = self._session_factory()
        try:
            return TemplateRepository(session).versions(template_id)
        finally:
            session.close()

    def update(self, principal: Principal, template_id: str, *,
               configuration: dict | None = None, description: str | None = None,
               settings: dict) -> AgentTemplate:
        """Write a new DRAFT version (existing versions are immutable and
        existing agents stay pinned to their published version)."""
        session = self._session_factory()
        try:
            repo = TemplateRepository(session)
            template = repo.get(template_id)
            if template is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"template {template_id} not found")
            if template.status == "deprecated":
                raise TemplateInvalidError(
                    "a deprecated template cannot be updated; clone it instead",
                    details={"error_category": "TEMPLATE_INVALID"})
            base = repo.version(template_id, template.current_version)
            new_config = copy.deepcopy(configuration if configuration is not None
                                       else (base.configuration if base else {}))
            new_version_number = template.current_version + 1
            errors = self._run_validation(session, new_config, settings)
            repo.add(AgentTemplateVersion(
                template_id=template.id, version=new_version_number,
                configuration=new_config,
                validation_status="valid" if not errors else "invalid",
                validation_errors=errors,
                created_by_type=principal.type.value, created_by_id=principal.id))
            template.current_version = new_version_number
            if description is not None:
                template.description = description
            if template.status == "published":
                template.status = "published"  # published_version unchanged; draft ahead
            return repo.save(template)
        finally:
            session.close()

    def clone(self, principal: Principal, template_id: str, *, new_name: str,
              settings: dict) -> AgentTemplate:
        session = self._session_factory()
        try:
            repo = TemplateRepository(session)
            source = repo.get(template_id)
            if source is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"template {template_id} not found")
            if repo.get_by_name(new_name) is not None:
                raise TemplateInvalidError(f"template name '{new_name}' already exists",
                                           details={"error_category": "TEMPLATE_INVALID"})
            base = repo.version(template_id, source.current_version)
            config = copy.deepcopy(base.configuration) if base else {}
            template = AgentTemplate(
                name=new_name, category=source.category,
                description=source.description, status="draft", current_version=1,
                published_version=None,
                created_by_type=principal.type.value, created_by_id=principal.id)
            repo.add(template)
            errors = self._run_validation(session, config, settings)
            repo.add(AgentTemplateVersion(
                template_id=template.id, version=1, configuration=config,
                validation_status="valid" if not errors else "invalid",
                validation_errors=errors,
                created_by_type=principal.type.value, created_by_id=principal.id))
            return template
        finally:
            session.close()

    def validate(self, template_id: str, *, version: int | None = None,
                 settings: dict) -> AgentTemplateVersion:
        session = self._session_factory()
        try:
            repo = TemplateRepository(session)
            template = repo.get(template_id)
            if template is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"template {template_id} not found")
            row = repo.version(template_id, version or template.current_version)
            if row is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError("template version not found")
            errors = self._run_validation(session, row.configuration, settings)
            row.validation_status = "valid" if not errors else "invalid"
            row.validation_errors = errors
            return repo.save(row)
        finally:
            session.close()

    def publish(self, principal: Principal, template_id: str, *,
                version: int | None = None) -> AgentTemplate:
        session = self._session_factory()
        try:
            repo = TemplateRepository(session)
            template = repo.get(template_id)
            if template is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"template {template_id} not found")
            target = version or template.current_version
            row = repo.version(template_id, target)
            if row is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError("template version not found")
            if row.validation_status != "valid":
                raise TemplateInvalidError(
                    "only a version whose validation_status is 'valid' can be published",
                    details={"error_category": "TEMPLATE_INVALID",
                             "validation_errors": row.validation_errors})
            template.published_version = target
            template.status = "published"
            return repo.save(template)
        finally:
            session.close()

    def deprecate(self, principal: Principal, template_id: str) -> AgentTemplate:
        session = self._session_factory()
        try:
            repo = TemplateRepository(session)
            template = repo.get(template_id)
            if template is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"template {template_id} not found")
            template.status = "deprecated"
            return repo.save(template)
        finally:
            session.close()

    def restore(self, principal: Principal, template_id: str, *, version: int,
                settings: dict) -> AgentTemplate:
        """Restore an earlier version's configuration AS A NEW draft
        version (history is never rewritten)."""
        session = self._session_factory()
        try:
            repo = TemplateRepository(session)
            template = repo.get(template_id)
            if template is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"template {template_id} not found")
            source = repo.version(template_id, version)
            if source is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"template version {version} not found")
            config = copy.deepcopy(source.configuration)
            new_version_number = template.current_version + 1
            errors = self._run_validation(session, config, settings)
            repo.add(AgentTemplateVersion(
                template_id=template.id, version=new_version_number,
                configuration=config,
                validation_status="valid" if not errors else "invalid",
                validation_errors=errors,
                created_by_type=principal.type.value, created_by_id=principal.id))
            template.current_version = new_version_number
            return repo.save(template)
        finally:
            session.close()

    @staticmethod
    def compare(config_a: dict, config_b: dict) -> dict:
        """Field-level diff of two template configurations (§6 compare)."""
        keys = sorted(set(config_a) | set(config_b))
        changes = []
        for key in keys:
            if config_a.get(key) != config_b.get(key):
                changes.append({"field": key, "from": config_a.get(key),
                                "to": config_b.get(key)})
        return {"changed_fields": [c["field"] for c in changes], "changes": changes}
