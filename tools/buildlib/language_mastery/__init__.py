"""Machine-owned, level-calibrated language-mastery contract for Bindery maps.

The package entry preserves the original public API while phase planning, map
validation, and authored evidence live in focused modules.
"""
from .authored import authored_mastery_problems
from .map_contract import validate_map_contract
from .phase1 import phase1_contract_problems, seed_contract
from .practice import (practice_allocations,
                       required_by_plan as practice_required_by_plan,
                       seeded_practice_problems)
from .shared import capability_spine, performance_specs, required_by_plan

__all__ = [
    "authored_mastery_problems", "capability_spine", "performance_specs",
    "phase1_contract_problems", "practice_allocations", "practice_required_by_plan",
    "required_by_plan", "seed_contract", "seeded_practice_problems", "validate_map_contract",
]
