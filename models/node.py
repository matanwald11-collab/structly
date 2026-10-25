from dataclasses import dataclass, field
from enum import Enum
from typing import List


class SupportType(Enum):
    FREE = "FREE"
    PINNED = "PINNED"
    ROLLER_X = "ROLLER_X"   # Restrained in Y only  (slides along X)
    ROLLER_Y = "ROLLER_Y"   # Restrained in X only  (slides along Y)
    FIXED = "FIXED"


@dataclass
class NodeLoad:
    """A concentrated load / moment applied at a node. SI: kN, kN·m."""
    Fx: float = 0.0    # Horizontal force  (+ve → right)
    Fy: float = 0.0    # Vertical force    (+ve → up)
    Mz: float = 0.0    # Moment            (+ve → CCW)
    case: str = "LC1"


@dataclass
class Node:
    """Structural node with world coordinates (m), support, and nodal loads."""
    id: str
    x: float                            # World X  (m)
    y: float                            # World Y  (m)
    support: SupportType = SupportType.FREE
    loads: List[NodeLoad] = field(default_factory=list)

    def support_dofs(self) -> tuple[bool, bool, bool]:
        """Return (DX, DY, RZ) restraint flags for PyNite def_support."""
        mapping = {
            SupportType.FREE:     (False, False, False),
            SupportType.PINNED:   (True,  True,  False),
            SupportType.ROLLER_X: (False, True,  False),
            SupportType.ROLLER_Y: (True,  False, False),
            SupportType.FIXED:    (True,  True,  True),
        }
        return mapping[self.support]
