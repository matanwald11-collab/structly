"""
engine/solver.py
================
Bridge between Project data model and PyNiteFEA v2.x.

Units: kN, m, kN·m throughout.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

try:
    from Pynite import FEModel3D
except ImportError as exc:
    raise ImportError(
        "PyNiteFEA is required. Install with:  pip install PyNiteFEA"
    ) from exc

from models.project import Project


class SolverError(RuntimeError):
    """Raised when analysis cannot be completed."""


# ─── Result containers ───────────────────────────────────────────────────────

@dataclass
class MemberResult:
    id: str
    length: float
    positions: List[float]     # m along member (0 → L)
    bmd: List[float]           # Bending moment (kN·m)
    sfd: List[float]           # Shear force    (kN)
    afd: List[float]           # Axial force    (kN)


@dataclass
class NodeResult:
    id: str
    dx: float       # X displacement (m)
    dy: float       # Y displacement (m)
    rz: float       # Z rotation (rad)
    rxn_fx: float   # X reaction (kN)
    rxn_fy: float   # Y reaction (kN)
    rxn_mz: float   # Z reaction moment (kN·m)


@dataclass
class Results:
    combo: str = "LC1"
    nodes:   Dict[str, NodeResult]   = field(default_factory=dict)
    members: Dict[str, MemberResult] = field(default_factory=dict)
    warnings: List[str]              = field(default_factory=list)

    def max_moment(self) -> float:
        vals = [abs(v) for mr in self.members.values() for v in mr.bmd]
        return max(vals) if vals else 1.0

    def max_shear(self) -> float:
        vals = [abs(v) for mr in self.members.values() for v in mr.sfd]
        return max(vals) if vals else 1.0

    def max_axial(self) -> float:
        vals = [abs(v) for mr in self.members.values() for v in mr.afd]
        return max(vals) if vals else 1.0

    def max_displacement(self) -> float:
        vals = [max(abs(nr.dx), abs(nr.dy)) for nr in self.nodes.values()]
        return max(vals) if vals else 1.0


@dataclass
class InfluenceLineResult:
    """Result of an Influence Line Diagram computation."""
    target_member_id: str    # member containing the target point
    target_x: float          # position of target point from i-node (m)
    force_type: str          # 'M', 'T', or 'N'
    positions: List[float]   # cumulative load positions along path (m)
    values: List[float]      # influence ordinate at each position
    path_member_ids: List[str]   # which member the load sits on at each point
    member_local_xs: List[float] # local x within that member


# ─── Solver ──────────────────────────────────────────────────────────────────

class Solver:
    """Translates a Project into a PyNiteFEA model, runs analysis, returns Results."""

    N_POINTS = 51   # sampling points along each member

    # ── Shared model builder ─────────────────────────────────────────────────

    def _build_base_model(self, project: Project, combo: str = "LC1"):
        """
        Build a FEModel3D with geometry, sections, supports and releases —
        but NO loads.  Returns (model, combo) ready for load application.
        """
        model = FEModel3D()

        # Materials + sections (one per unique name)
        seen: set[str] = set()
        for mem in project.members.values():
            sec = mem.section
            mat_name = f"MAT_{sec.name}"
            sec_name = f"SEC_{sec.name}"
            if sec_name not in seen:
                seen.add(sec_name)
                nu = sec.E / (2 * sec.G) - 1
                model.add_material(mat_name, E=sec.E, G=sec.G, nu=nu, rho=78.5)
                model.add_section(sec_name, A=sec.A, Iz=sec.Iz, Iy=sec.Iy, J=sec.J)

        # Nodes + supports
        for n in project.nodes.values():
            model.add_node(n.id, n.x, n.y, 0.0)
            dx, dy, rz = n.support_dofs()
            model.def_support(n.id,
                              support_DX=dx,   support_DY=dy,   support_DZ=True,
                              support_RX=True,  support_RY=True,  support_RZ=rz)

        # Members + releases
        for m in project.members.values():
            sec = m.section
            model.add_member(m.id,
                             m.start_node_id, m.end_node_id,
                             f"MAT_{sec.name}", f"SEC_{sec.name}")
            rs, re = m.releases_start, m.releases_end
            if m.has_releases():
                model.def_releases(m.id,
                                   Dxi=rs.Fx, Dyi=rs.Fy, Dzi=False,
                                   Rxi=False,  Ryi=False,  Rzi=rs.Mz,
                                   Dxj=re.Fx, Dyj=re.Fy, Dzj=False,
                                   Rxj=False,  Ryj=False,  Rzj=re.Mz)
        return model, combo

    # ── Primary analysis ─────────────────────────────────────────────────────

    def run(self, project: Project) -> Results:
        errors = project.validate()
        if errors:
            raise SolverError("\n".join(errors))

        model, combo = self._build_base_model(project)

        # ── Loads ─────────────────────────────────────────────────────────────
        has_loads = False
        for m in project.members.values():
            for dl in m.dist_loads:
                model.add_member_dist_load(m.id, dl.direction,
                                           w1=dl.w_start, w2=dl.w_end,
                                           x1=dl.x1, x2=dl.x2,
                                           case=combo)
                has_loads = True
            for pl in m.pt_loads:
                model.add_member_pt_load(m.id, pl.direction,
                                         pl.magnitude, x=pl.x, case=combo)
                has_loads = True

        for n in project.nodes.values():
            for load in n.loads:
                if load.Fx != 0:
                    model.add_node_load(n.id, 'FX', load.Fx, case=combo)
                    has_loads = True
                if load.Fy != 0:
                    model.add_node_load(n.id, 'FY', load.Fy, case=combo)
                    has_loads = True
                if load.Mz != 0:
                    model.add_node_load(n.id, 'MZ', load.Mz, case=combo)
                    has_loads = True

        if not has_loads:
            raise SolverError("No loads are defined on the structure.")

        model.add_load_combo(combo, {combo: 1.0})
        try:
            model.analyze(log=False, check_statics=False, check_stability=False)
        except Exception as exc:
            raise SolverError(f"PyNite analysis failed: {exc}") from exc

        # ── Extract results ────────────────────────────────────────────────────
        results = Results(combo=combo)

        for nid, pn in model.nodes.items():
            results.nodes[nid] = NodeResult(
                id=nid,
                dx=_g(pn.DX,    combo),
                dy=_g(pn.DY,    combo),
                rz=_g(pn.RZ,    combo),
                rxn_fx=_g(pn.RxnFX, combo),
                rxn_fy=_g(pn.RxnFY, combo),
                rxn_mz=_g(pn.RxnMZ, combo),
            )

        for mid, pm in model.members.items():
            L  = pm.L()
            xs = list(np.linspace(0.0, L, self.N_POINTS))
            results.members[mid] = MemberResult(
                id=mid, length=L,
                positions=xs,
                bmd=[pm.moment('Mz', x, combo) for x in xs],
                sfd=[pm.shear('Fy',  x, combo) for x in xs],
                afd=[pm.axial(x, combo)          for x in xs],
            )

        return results

    # ── Influence Line Diagram ────────────────────────────────────────────────

    def compute_influence_line(self,
                               project: Project,
                               target_member_id: str,
                               target_x: float,
                               force_type: str,
                               path_member_ids: List[str]) -> InfluenceLineResult:
        """
        Sweep a −1 kN unit load along *path_member_ids* at 1 000 evenly-spaced
        positions plus all Points of Interest (POIs: member endpoints / joints)
        to guarantee a smooth, exact ILD.

        force_type : 'M' (bending moment), 'T' (shear), 'N' (axial)
        """
        _N_SEGS = 1000   # hardcoded high-fidelity discretisation

        errors = project.validate()
        if errors:
            raise SolverError("\n".join(errors))

        if target_member_id not in project.members:
            raise SolverError(f"Target member '{target_member_id}' not found.")

        def _world_len(mid: str) -> float:
            m  = project.members[mid]
            ni = project.nodes[m.start_node_id]
            nj = project.nodes[m.end_node_id]
            return math.hypot(nj.x - ni.x, nj.y - ni.y)

        path_lengths = [_world_len(mid) for mid in path_member_ids]
        total_length = sum(path_lengths) or 1.0

        # ── Build raw (mid, local_x, cum_pos) tuples ─────────────────────────
        raw: list[tuple[str, float, float]] = []
        cumpos = 0.0
        for mid, L in zip(path_member_ids, path_lengths):
            n_seg = max(1, round(_N_SEGS * L / total_length))
            # Regular grid
            for j in range(n_seg + 1):
                local_x = min(j / n_seg * L, L)
                raw.append((mid, local_x, cumpos + local_x))
            # POI: joint at start of next member (same cumulative position as L)
            cumpos += L

        # Deduplicate by cumulative position (keep insertion order)
        seen_cum: set = set()
        load_points: list[tuple[str, float, float]] = []
        for pt in raw:
            key = round(pt[2], 8)
            if key not in seen_cum:
                seen_cum.add(key)
                load_points.append(pt)

        positions:      list[float] = []
        values:         list[float] = []
        out_member_ids: list[str]   = []
        out_local_xs:   list[float] = []

        for (load_mid, local_x, cum) in load_points:
            model, combo = self._build_base_model(project, combo="IL1")
            model.add_load_combo(combo, {combo: 1.0})

            L_mid   = _world_len(load_mid)
            safe_x  = max(1e-4, min(local_x, L_mid - 1e-4)) if L_mid > 2e-4 else local_x
            model.add_member_pt_load(load_mid, "Fy", -1.0, x=safe_x, case=combo)

            try:
                model.analyze(log=False, check_statics=False, check_stability=False)
            except Exception:
                values.append(float("nan"))
                positions.append(cum)
                out_member_ids.append(load_mid)
                out_local_xs.append(local_x)
                continue

            pm = model.members.get(target_member_id)
            if pm is None:
                values.append(0.0)
            else:
                tgt_L  = pm.L()
                safe_tx = max(0.0, min(target_x, tgt_L))
                if force_type == "M":
                    val = pm.moment("Mz", safe_tx, combo)
                elif force_type == "T":
                    val = pm.shear("Fy", safe_tx, combo)
                else:
                    val = pm.axial(safe_tx, combo)
                values.append(float(val))

            positions.append(cum)
            out_member_ids.append(load_mid)
            out_local_xs.append(local_x)

        return InfluenceLineResult(
            target_member_id=target_member_id,
            target_x=target_x,
            force_type=force_type,
            positions=positions,
            values=values,
            path_member_ids=out_member_ids,
            member_local_xs=out_local_xs,
        )



def _g(attr, combo: str, default: float = 0.0) -> float:
    """Safely retrieve a value from a PyNite result dict."""
    if isinstance(attr, dict):
        v = attr.get(combo, default)
        return float(v) if v is not None else default
    return default
