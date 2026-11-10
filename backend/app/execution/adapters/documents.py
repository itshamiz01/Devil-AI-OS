"""Document & data adapter (§14) — stdlib only.

Text/Markdown/CSV creation, reading, transformation and deterministic
summaries, all inside managed workspaces with the same path validation
as the filesystem adapter. PDF reading/extraction and presentation
formats are DEFERRED: no existing project dependency supports them and
P-05 adds none (audit §3). Bounded processing: reads are capped by the
configured output ceiling; CSV transforms stream row by row.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from ..errors import PathValidationError
from ..paths import resolve_within_workspace
from ..workspaces import WorkspaceManager
from .base import AdapterContext, AdapterResult
from .filesystem import atomic_write, sha256_bytes, sha256_file


class DocumentsAdapter:
    adapter_type = "documents"

    def __init__(self, workspaces: WorkspaceManager):
        self._workspaces = workspaces

    def health(self) -> dict:
        return {"status": "available", "health_status": "healthy",
                "details": {"formats": ["text", "markdown", "csv"],
                            "deferred": ["pdf", "presentation", "spreadsheet-binary"],
                            "libraries": "python stdlib only"}}

    def _resolve(self, params):
        workspace = self._workspaces.get_workspace(str(params.get("workspace") or ""))
        validated = resolve_within_workspace(Path(workspace.root_path), params.get("path", ""))
        return workspace, validated

    async def execute(self, action: str, parameters: dict,
                      context: AdapterContext) -> AdapterResult:
        handler = getattr(self, f"_do_{action}", None)
        if handler is None:
            return AdapterResult(False, error_category="ACTION_UNKNOWN",
                                 summary=f"documents adapter has no action '{action}'")
        try:
            return handler(parameters, context)
        except PathValidationError as exc:
            return AdapterResult(False, error_category="PATH_TRAVERSAL",
                                 summary=f"path rejected: {exc.message}")
        except Exception as exc:
            category = getattr(exc, "code", None) or type(exc).__name__
            return AdapterResult(False, error_category=str(category),
                                 summary=f"{type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ reads
    def _do_read_text(self, params, context):
        workspace, validated = self._resolve(params)
        target = validated.absolute
        if not target.is_file():
            return AdapterResult(False, error_category="NOT_FOUND",
                                 summary=f"'{validated.relative}' is not a file")
        cap = int(context.settings.get("max_output_bytes", 1_000_000))
        data = target.read_bytes()
        return AdapterResult(
            True, output={"content": data[:cap].decode("utf-8", errors="replace"),
                          "size": len(data), "sha256": sha256_bytes(data),
                          "truncated": len(data) > cap},
            summary=f"read text {workspace.name}:{validated.relative}")

    @staticmethod
    def _read_csv_rows(target: Path, cap_rows: int = 10_000):
        with open(target, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = []
            for index, row in enumerate(reader):
                if index >= cap_rows:
                    break
                rows.append(row)
            return reader.fieldnames or [], rows

    def _do_read_csv(self, params, context):
        workspace, validated = self._resolve(params)
        target = validated.absolute
        if not target.is_file():
            return AdapterResult(False, error_category="NOT_FOUND",
                                 summary=f"'{validated.relative}' is not a file")
        headers, rows = self._read_csv_rows(target)
        return AdapterResult(
            True, output={"headers": headers, "rows": rows, "row_count": len(rows),
                          "sha256": sha256_file(target)},
            summary=f"read CSV {workspace.name}:{validated.relative} ({len(rows)} rows)")

    def _do_summarize_csv(self, params, context):
        workspace, validated = self._resolve(params)
        target = validated.absolute
        if not target.is_file():
            return AdapterResult(False, error_category="NOT_FOUND",
                                 summary=f"'{validated.relative}' is not a file")
        headers, rows = self._read_csv_rows(target, cap_rows=100_000)
        columns = {}
        for header in headers:
            values = [row.get(header) for row in rows]
            non_empty = [v for v in values if v not in (None, "")]
            numeric = 0
            for value in non_empty:
                try:
                    float(str(value).replace(",", ""))
                    numeric += 1
                except ValueError:
                    pass
            columns[header] = {
                "non_empty": len(non_empty),
                "type_guess": "number" if non_empty and numeric == len(non_empty) else "text",
            }
        return AdapterResult(
            True, output={"headers": headers, "row_count": len(rows), "columns": columns,
                          "sha256": sha256_file(target)},
            summary=f"CSV summary {workspace.name}:{validated.relative}: "
                    f"{len(rows)} rows, {len(headers)} columns (deterministic, measured)")

    # ----------------------------------------------------------------- writes
    def _do_create_text(self, params, context):
        workspace, validated = self._resolve(params)
        target = validated.absolute
        if target.exists():
            return AdapterResult(False, error_category="FILE_EXISTS",
                                 summary=f"'{validated.relative}' already exists")
        data = str(params.get("content") or "").encode("utf-8")
        atomic_write(target, data)
        digest = sha256_bytes(data)
        return AdapterResult(
            True, output={"path": validated.relative, "size": len(data), "sha256": digest},
            summary=f"created document {workspace.name}:{validated.relative} ({len(data)} bytes)",
            evidence=[{"type": "file", "reference": f"{workspace.name}:{validated.relative}",
                       "content_hash": digest,
                       "details": {"operation": "create_text", "workspace": workspace.name,
                                   "path": validated.relative}}])

    def _do_create_csv(self, params, context):
        workspace, validated = self._resolve(params)
        target = validated.absolute
        if target.exists():
            return AdapterResult(False, error_category="FILE_EXISTS",
                                 summary=f"'{validated.relative}' already exists")
        headers = list(params.get("headers") or [])
        rows = list(params.get("rows") or [])
        if not headers:
            return AdapterResult(False, error_category="VALIDATION",
                                 summary="create_csv requires headers")
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in headers})
        data = buffer.getvalue().encode("utf-8")
        atomic_write(target, data)
        digest = sha256_bytes(data)
        return AdapterResult(
            True, output={"path": validated.relative, "size": len(data), "sha256": digest,
                          "row_count": len(rows)},
            summary=f"created CSV {workspace.name}:{validated.relative} ({len(rows)} rows)",
            evidence=[{"type": "file", "reference": f"{workspace.name}:{validated.relative}",
                       "content_hash": digest,
                       "details": {"operation": "create_csv", "workspace": workspace.name,
                                   "path": validated.relative}}])

    def _do_transform_csv(self, params, context):
        workspace = self._workspaces.get_workspace(str(params.get("workspace") or ""))
        source = resolve_within_workspace(Path(workspace.root_path), params.get("source_path", ""))
        dest = resolve_within_workspace(Path(workspace.root_path), params.get("dest_path", ""))
        if not source.absolute.is_file():
            return AdapterResult(False, error_category="NOT_FOUND",
                                 summary=f"source '{source.relative}' is not a file")
        if dest.absolute.exists():
            return AdapterResult(False, error_category="FILE_EXISTS",
                                 summary=f"destination '{dest.relative}' already exists")
        headers, rows = self._read_csv_rows(source.absolute, cap_rows=100_000)
        columns = list(params.get("columns") or headers)
        unknown = [c for c in columns if c not in headers]
        if unknown:
            return AdapterResult(False, error_category="VALIDATION",
                                 summary=f"unknown columns requested: {', '.join(unknown)}")
        filters = dict(params.get("filters") or {})
        kept = [row for row in rows
                if all(str(row.get(k, "")) == str(v) for k, v in filters.items())]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        for row in kept:
            writer.writerow({c: row.get(c, "") for c in columns})
        data = buffer.getvalue().encode("utf-8")
        atomic_write(dest.absolute, data)
        digest = sha256_bytes(data)
        return AdapterResult(
            True, output={"path": dest.relative, "row_count": len(kept),
                          "source_row_count": len(rows), "sha256": digest},
            summary=f"transformed CSV {source.relative} -> {dest.relative} "
                    f"({len(rows)} -> {len(kept)} rows)",
            evidence=[{"type": "file", "reference": f"{workspace.name}:{dest.relative}",
                       "content_hash": digest,
                       "details": {"operation": "transform_csv", "workspace": workspace.name,
                                   "path": dest.relative, "source": source.relative}}])
