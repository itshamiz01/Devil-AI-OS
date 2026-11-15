"""Shared helpers for the workforce test files."""
from __future__ import annotations

from sqlalchemy import select

from app.database.models.workforce import WorkforceProfile
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER


def seed(application):
    svc = application.workforce
    result = svc.seed_workforce(OWNER)
    return svc, result


def agent_id_for(application, code: str) -> str:
    session = application.session_factory()
    try:
        prof = session.scalar(select(WorkforceProfile).where(
            WorkforceProfile.employee_code == code))
        assert prof is not None, f"no profile for {code}"
        return prof.agent_id
    finally:
        session.close()


def principal_for(application, code: str) -> Principal:
    return Principal(PrincipalType.AGENT, agent_id_for(application, code))
