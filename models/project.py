from __future__ import annotations

import json
from typing import Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from .section import CrossSection
from .node import Node, SupportType, NodeLoad
from .member import Member, Releases, DistLoad, PointLoad


class Project(QObject):
    """Central data model. Emits Qt signals on every mutation for reactive UI."""

    node_added    = pyqtSignal(object)  # Node
    node_removed  = pyqtSignal(str)     # node_id
    node_changed  = pyqtSignal(object)  # Node

    member_added   = pyqtSignal(object)  # Member
    member_removed = pyqtSignal(str)     # member_id
    member_changed = pyqtSignal(object)  # Member

    project_reset = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.nodes:   Dict[str, Node]   = {}
        self.members: Dict[str, Member] = {}
        self._node_ctr   = 0
        self._member_ctr = 0
        self.default_section = CrossSection.default_steel()

    # ── Node Management ──────────────────────────────────────────────────────

    def _next_node_id(self) -> str:
        self._node_ctr += 1
        return f"N{self._node_ctr}"

    def add_node(self, x: float, y: float) -> Node:
        node = Node(id=self._next_node_id(), x=x, y=y)
        self.nodes[node.id] = node
        self.node_added.emit(node)
        return node

    def delete_node(self, node_id: str) -> None:
        # Remove all connected members first
        for mid in [m for m, mb in self.members.items()
                    if mb.start_node_id == node_id or mb.end_node_id == node_id]:
            self.delete_member(mid)
        if node_id in self.nodes:
            del self.nodes[node_id]
            self.node_removed.emit(node_id)

    def update_node(self, node: Node) -> None:
        self.nodes[node.id] = node
        self.node_changed.emit(node)

    # ── Member Management ────────────────────────────────────────────────────

    def _next_member_id(self) -> str:
        self._member_ctr += 1
        return f"M{self._member_ctr}"

    def add_member(self, start_id: str, end_id: str,
                   section: Optional[CrossSection] = None) -> Member:
        sec = section or CrossSection.default_steel()
        member = Member(id=self._next_member_id(),
                        start_node_id=start_id,
                        end_node_id=end_id,
                        section=sec)
        self.members[member.id] = member
        self.member_added.emit(member)
        return member

    def delete_member(self, member_id: str) -> None:
        if member_id in self.members:
            del self.members[member_id]
            self.member_removed.emit(member_id)

    def update_member(self, member: Member) -> None:
        self.members[member.id] = member
        self.member_changed.emit(member)

    def clear(self) -> None:
        self.nodes.clear()
        self.members.clear()
        self._node_ctr   = 0
        self._member_ctr = 0
        self.project_reset.emit()

    # ── Validation ───────────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Return a list of error strings. Empty list → project is solvable."""
        errors: list[str] = []
        if len(self.nodes) < 2:
            errors.append("Need at least 2 nodes.")
        if not self.members:
            errors.append("Need at least one member.")
        supported = [n for n in self.nodes.values() if n.support.name != "FREE"]
        if not supported:
            errors.append("No supports defined – structure is unsupported.")
        return errors

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        def _sec(s: CrossSection):
            return {"name": s.name, "E": s.E, "G": s.G,
                    "A": s.A, "Iz": s.Iz, "J": s.J}
        def _rel(r: Releases):
            return {"Fx": r.Fx, "Fy": r.Fy, "Mz": r.Mz}

        return {
            "_node_ctr":   self._node_ctr,
            "_member_ctr": self._member_ctr,
            "nodes": [
                {"id": n.id, "x": n.x, "y": n.y,
                 "support": n.support.value,
                 "loads": [{"Fx": l.Fx, "Fy": l.Fy, "Mz": l.Mz, "case": l.case}
                            for l in n.loads]}
                for n in self.nodes.values()
            ],
            "members": [
                {"id": m.id,
                 "start_node_id": m.start_node_id,
                 "end_node_id":   m.end_node_id,
                 "section": _sec(m.section),
                 "releases_start": _rel(m.releases_start),
                 "releases_end":   _rel(m.releases_end),
                 "dist_loads": [
                     {"direction": d.direction, "w_start": d.w_start,
                      "w_end": d.w_end, "x1": d.x1, "x2": d.x2,
                      "case": d.case, "local": d.local}
                     for d in m.dist_loads
                 ],
                 "pt_loads": [
                     {"direction": p.direction, "magnitude": p.magnitude,
                      "x": p.x, "case": p.case, "local": p.local}
                     for p in m.pt_loads
                 ]}
                for m in self.members.values()
            ],
        }

    def from_dict(self, data: dict) -> None:
        self.nodes.clear()
        self.members.clear()
        self._node_ctr   = data.get("_node_ctr",   0)
        self._member_ctr = data.get("_member_ctr", 0)

        for nd in data.get("nodes", []):
            node = Node(
                id=nd["id"], x=nd["x"], y=nd["y"],
                support=SupportType(nd["support"]),
                loads=[NodeLoad(**l) for l in nd.get("loads", [])],
            )
            self.nodes[node.id] = node

        for md in data.get("members", []):
            s = md["section"]
            member = Member(
                id=md["id"],
                start_node_id=md["start_node_id"],
                end_node_id=md["end_node_id"],
                section=CrossSection(**{k: s[k] for k in ("name","E","G","A","Iz","J")}),
                releases_start=Releases(**md["releases_start"]),
                releases_end=Releases(**md["releases_end"]),
                dist_loads=[DistLoad(**d) for d in md.get("dist_loads", [])],
                pt_loads=[PointLoad(**p) for p in md.get("pt_loads", [])],
            )
            self.members[member.id] = member

        self.project_reset.emit()

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def load(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            self.from_dict(json.load(f))
