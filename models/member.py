from dataclasses import dataclass, field
from typing import List, Optional
from .section import CrossSection


@dataclass
class Releases:
    """Per-DOF end-release flags. True = released (free to rotate/translate)."""
    Fx: bool = False   # Axial force release
    Fy: bool = False   # Shear force release
    Mz: bool = False   # Moment release → hinge


@dataclass
class DistLoad:
    """Linearly varying (or uniform) distributed load along a member. SI: kN/m."""
    direction: str        # 'Fy' local or 'FY' global  (use 'Fy' for gravity loads)
    w_start: float        # Intensity at i-node  (kN/m)
    w_end: float          # Intensity at j-node  (kN/m)
    x1: float = 0.0       # Start position from i-node (m); 0 = full length
    x2: Optional[float] = None  # End position (None = full length to j-node)
    case: str = "LC1"
    local: bool = True    # True = member local axes, False = global axes


@dataclass
class PointLoad:
    """
    Concentrated load applied at a specific position along a member.

    direction : 'Fy' (transverse local), 'Fx' (axial local),
                'FY'/'FX' (global), 'Mz' (moment)
    magnitude : signed load value in kN (or kN·m for moments)
    x         : distance from i-node (m); must be 0 < x < member length
    """
    direction: str
    magnitude: float
    x: float = 0.0          # distance from i-node  (m)
    case: str = "LC1"
    local: bool = True       # True = local axes


@dataclass
class Member:
    """Structural member connecting two nodes."""
    id: str
    start_node_id: str
    end_node_id: str
    section: CrossSection
    releases_start: Releases = field(default_factory=Releases)
    releases_end:   Releases = field(default_factory=Releases)
    dist_loads:  List[DistLoad]  = field(default_factory=list)
    pt_loads:    List[PointLoad] = field(default_factory=list)

    def has_releases(self) -> bool:
        r, s = self.releases_start, self.releases_end
        return any([r.Fx, r.Fy, r.Mz, s.Fx, s.Fy, s.Mz])

    def has_dist_loads(self) -> bool:
        return bool(self.dist_loads)

    def has_pt_loads(self) -> bool:
        return bool(self.pt_loads)
