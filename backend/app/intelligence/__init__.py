"""Master Intelligence Engine (P-02).

Deterministic-first planning on top of the P-01 Core OS: missions become
typed plans (data, never code) whose steps reference ONLY handlers in the
P-01 HandlerRegistry; execution happens exclusively through
``TaskManager.submit``; every CIO decision is written to decision_records
and explanations are assembled from those records.
"""
