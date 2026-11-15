"""Workforce API schemas (Agentic Workforce Transformation)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class ObjectiveIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    department_codes: list[str] | None = None


class WorkOrderIn(BaseModel):
    objective_id: str
    employee_code: str
    objective: str = Field(min_length=1)
    instructions: str = ""
    expected_deliverable: str = ""
    priority: int = Field(default=5, ge=0, le=100)
    deadline: dt.datetime | None = None
    restricted: bool = False


class DeliverableIn(BaseModel):
    work_performed: str = Field(min_length=1)
    result: str = Field(min_length=1)
    evidence: list = Field(default_factory=list)
    limitations: str = ""
    outstanding_issues: str = ""


class ReviewIn(BaseModel):
    accept: bool
    quality_score: float | None = Field(default=None, ge=0, le=100)
    notes: str | None = None


class HandoffIn(BaseModel):
    from_code: str
    to_code: str
    objective: str = Field(min_length=1)
    task_ref: str = ""
    work_completed: str = ""
    next_actions: list = Field(default_factory=list)
