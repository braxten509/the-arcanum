# Persistent memory boundary

Never save anything about Arcanum tomes to Codex or any other provider's persistent memory. This
includes specific-tome facts and generalized lessons derived from tome authoring, validation,
review, phases, sections, runs, costs, or outcomes. Do not create or update memory notes, skills,
profiles, or global instructions from tome work. Keep that state only in authorized repository and
harness artifacts for the current job.

# Completion structure gate

Before finishing any task that changes repository code, run
`python3 tools/validate_code.py` from the repository root. Fix every file-size,
directory-crowding, and architecture-policy finding before stopping. Split code
along functional seams; do not silence, bypass, weaken, or special-case the
gate. If an external blocker makes the gate impossible to complete, report that
blocker explicitly instead of claiming the task is finished.
