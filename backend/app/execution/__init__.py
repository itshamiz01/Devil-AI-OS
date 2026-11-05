"""P-05 Universal Digital Execution Engine.

Deliberately import-light. `app.database.models` imports the vocabularies from
:mod:`app.execution.schemas`, so a package `__init__` that pulled in the services
would close a cycle through the models — the same trap P-04's `app.agents`
documents. Import the modules, not the package.
"""
