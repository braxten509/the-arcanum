"""ARCANUM server package. Module map:
- config      paths, constants, shared job registry
- tomes       tome discovery/assembly, save/workspace paths
- models      AI model census + one-shot CLI calls
- forge       tome-forge build jobs, Pushover, resume bookkeeping
- grader      freestyle grading + the oracle
- amender     the Binder (amend a tome)
- routes_get  GET /api/* + static files
- routes_post POST /api/*
server.py at the repo root is the entry point."""
