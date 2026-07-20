"""The [economy] table: rank thresholds and titles."""
from ... import warn


def check_economy(m, label):
    econ = m.get("economy", {})
    if not isinstance(econ, dict):
        return
    ranks = econ.get("ranks")
    if ranks is None:
        return
    if not isinstance(ranks, list) or not ranks:
        warn(label, "[economy] ranks should be a non-empty array of [threshold, title] pairs",
             phase=5)
        return
    ok = True
    for r in ranks:
        if (not isinstance(r, list) or len(r) != 2
                or not isinstance(r[0], (int, float)) or not isinstance(r[1], str)):
            ok = False
    if not ok:
        warn(label, "[economy] ranks entries should each be [threshold(number), title(string)]",
             phase=5)
    elif ranks[0][0] != 0:
        warn(label, "[economy] ranks: the first title should start at threshold 0", phase=5)
