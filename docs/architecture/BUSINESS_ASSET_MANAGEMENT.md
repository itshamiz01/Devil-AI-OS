# Business Asset Management (P-06 §13/§22)

## Registration

Assets exist as rows in `business_assets` only after the creation
workflow has produced the file **and** an execution-engine hash read has
verified it. Each row records: type, name, storage reference
(`business:<id>:<path>`), version, creation method
(`p05_execution_workflow`), creator agent, approval status (draft),
usage-rights status, quality status (`verified` when a digest exists,
else `missing`), the SHA-256 content hash, and the associated product.

## Rights and quality (§13.3/§20C)

Generated assets are `original_work` (deterministic templating over the
owner's own opportunity data). An asset whose rights are `uncertain`
or `restricted_unresolved` blocks readiness dimension C until resolved
(security test 13). No asset may contain fake testimonials, fake
reviews, invented company registrations, addresses, licences or
certifications — the templates contain none, and the quality review
checks the property (§12).

## Legal assets

Privacy/terms files are **structural templates**: they carry
"NOT A LEGAL DOCUMENT" headers, `[OWNER TO COMPLETE: …]` placeholders
and a professional-review requirement. They are readiness *inputs*
(dimension G checks they are prepared), never compliance claims
(security test 12).

## Evidence vs assets (§22)

Assets are what the business *has*; evidence is what *supports a
claim*. Business evidence rows carry provenance (source, source type),
reliability, retrieval time, freshness status, the associated decision
and limitations. Platform-gate outcomes and publish attempts are
recorded as evidence. Generated reasoning/documents are recorded as
`internal_generation` with reliability `low`; submitting
`llm_reasoning`/`model_output` as an evidence source type is rejected
by the API — generated reasoning is never independent evidence.
