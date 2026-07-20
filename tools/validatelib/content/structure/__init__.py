"""Structural checks: the file-layout contract, placeholder sweep, badge bank,
and the meta/runtime/narrative/economy/shop tables."""
from .badges import check_badges
from .economy import check_economy
from .layout import check_layout
from .meta import check_meta
from .narrative import check_narrative
from .placeholders import check_placeholders
from .runtime import check_runtime
from .shop import check_shop

__all__ = ["check_badges", "check_economy", "check_layout", "check_meta",
           "check_narrative", "check_placeholders", "check_runtime", "check_shop"]
