# Business Workspace Guide (P-06 §18)

## Layout

Every business gets a dedicated P-05 managed workspace:

```
execution_workspaces/businesses/<business-id>/
  blueprint/          blueprint.md (rendered §8 blueprint)
  product/            product_spec.md, manuscript_outline.md /
                      architecture.md / editorial_plan.md (per template)
  brand/              brand_guide.md
  marketing/          listing_copy.md (DRAFT — never sent anywhere)
  sales/              (reserved by the §18 structure)
  operations/         playbook.md
  customer_support/   faq.md
  financial_records/  (reserved; P-07 will own financial records)
  evidence/           (reserved for exported evidence bundles)
  reports/            (reserved for generated reports)
  website/            index.html (local package — NOT deployed)
  legal/              privacy_policy.md, terms.md (templates with
                      owner-completion placeholders)
```

Directories are created by the creation workflow's `mkdir` steps (the
§18 tree is template data), and every file is written by a P-05
execution request — P-06 services never touch the filesystem directly.

## Rules

- Workspaces are per-business and isolated (§28.1 — see
  `docs/security/BUSINESS_DATA_ISOLATION.md`). Never copy files between
  business workspaces by hand; cross-business access through the system
  is denied and recorded.
- File existence claims come from execution evidence (hashes), not from
  looking at the directory.
- Backups: the workspace is plain files under the data directory —
  include `execution_workspaces/businesses/` in the same backup as the
  database (see P-01 operations guidance). This procedure is documented
  but, like all Windows-side operations, **untested on Windows**.

## Windows setup (staging honesty)

The project targets the owner's Windows machine (Constitution lock).
On Windows: install Python 3.12+, create the venv
(`py -m venv .venv`), install `backend/requirements.txt`, set
`AUTONOMUS_DATA_DIR` (e.g. `C:\AUTONOMUS\data`), run
`alembic upgrade head`, and start
`.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
Workspace paths are handled through `pathlib` and the P-05 path
validator (Windows drive/reserved-name rules were built into P-05 and
are enforced on Linux too). **Windows execution remains unverified** —
it is carried as an open item since P-01 and is not claimed anywhere in
the P-06 gate.
