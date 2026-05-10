from canslim.patterns.ascending_triangle import AscendingTriangle
from canslim.patterns.base import ChartPattern, detect_all
from canslim.patterns.consolidation import Consolidation
from canslim.patterns.cup_handle import CupWithHandle
from canslim.patterns.double_bottom import DoubleBottom
from canslim.patterns.flat_base import FlatBase
from canslim.patterns.high_tight_flag import HighTightFlag
from canslim.patterns.saucer import Saucer
from canslim.patterns.three_weeks_tight import ThreeWeeksTight


def default_patterns() -> list[ChartPattern]:
    """All ChartPattern detectors shipped by default, roughly ordered by O'Neil priority."""
    return [
        CupWithHandle(),
        HighTightFlag(),
        DoubleBottom(),
        Saucer(),
        AscendingTriangle(),
        FlatBase(),
        Consolidation(),
        ThreeWeeksTight(),
    ]


__all__ = [
    "AscendingTriangle",
    "ChartPattern",
    "Consolidation",
    "CupWithHandle",
    "DoubleBottom",
    "FlatBase",
    "HighTightFlag",
    "Saucer",
    "ThreeWeeksTight",
    "default_patterns",
    "detect_all",
]
