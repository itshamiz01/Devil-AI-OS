# Filesystem Security (P-10)

The P-10 `FilesystemGuard` is a deterministic decision layer that
composes P-05's lexical path normalization with three policies.
It does not perform I/O; P-05 remains the executor.

## Rules (in order)

1. **Normalize** — Windows-lexical normalization (P-05): `.`/`..`
   segments resolved lexically, UNC and drive-relative forms
   handled. A path that escapes via traversal is decided on its
   normalized form (Scenario: `businesses/b1/../../credentials`
   resolves into the protected root and is denied).
2. **Protected roots** — `credentials`, `secrets`, `.ssh`, `.aws`,
   `governance`, `config/security` (plus owner additions in
   `security.settings.protected_roots`): non-owner access denied
   for every operation. This is the Article-0 wall around
   governance material at the filesystem layer.
3. **Classification** — paths classified at level 4–5
   (`security_data_classifications`) deny write/delete/move for
   non-owners and require a valid approval for destructive
   operations even then.
4. **Mode** — in safe_mode, writes are denied for non-owners
   regardless of classification.

## Honest limits

Lexical checks decide on the path *as written*. Symlink and
junction resolution at execution time is the executor's concern;
P-05's executor applies its own root policy. The combination is
defence in depth, not a formally verified boundary, and no doc
claims otherwise.
