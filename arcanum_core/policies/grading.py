"""Server-authoritative deterministic and qualitative score composition."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class GradeResult:
    total: int
    grade: str
    essential_passed: bool
    scores: tuple[dict, ...]


def letter_grade(total: int, exceptional: bool = False) -> str:
    if exceptional and total == 100:
        return "S"
    if total >= 90:
        return "A"
    if total >= 80:
        return "B"
    if total >= 70:
        return "C"
    if total >= 60:
        return "D"
    return "F"


def compose_grade(criteria: Iterable[dict], returned_scores: Iterable[dict],
                  essential_passed: bool) -> GradeResult:
    criteria = tuple(criteria)
    returned = tuple(returned_scores)
    ids = [str(item.get("id") or "") for item in criteria]
    by_id = {str(item.get("id") or ""): item for item in returned}
    if not ids or len(ids) != len(set(ids)) or set(ids) != set(by_id):
        raise ValueError("returned criterion IDs must exactly match the rubric")
    if sum(int(item.get("weight") or 0) for item in criteria) != 100:
        raise ValueError("rubric weights must total 100")
    normalized = []
    for criterion in criteria:
        item = by_id[criterion["id"]]
        raw = item.get("score")
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise ValueError(f"criterion {criterion['id']} score must be numeric")
        score = max(0.0, min(10.0, float(raw)))
        normalized.append({"id": criterion["id"], "criterion": criterion.get("criterion", ""),
                           "score": score, "comment": str(item.get("comment") or ""),
                           "weight": int(criterion["weight"]), "kind": criterion.get("kind", "")})
    total = round(sum(row["score"] / 10 * row["weight"] for row in normalized))
    return GradeResult(total, letter_grade(total) if essential_passed else "INCOMPLETE",
                       essential_passed, tuple(normalized))
