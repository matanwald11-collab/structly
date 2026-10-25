"""
ui/loads_dialog.py
==================
Modal dialog for defining and editing structural loads.

Tabs:
  1. Point / Moment  — nodal concentrated load / moment
  2. Distributed     — linearly varying UDL along a member
  3. Point on Member — concentrated load at exact position x from i-node

All values in SI units: kN, m, kN·m.
"""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout,
    QLabel, QComboBox, QDoubleSpinBox,
    QDialogButtonBox, QTabWidget, QWidget,
    QFrame,
)

from models.project import Project
from models.node import NodeLoad
from models.member import DistLoad, PointLoad


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

_DIALOG_STYLE = """
    QDialog   { background:#1a1b26; color:#c0caf5; }
    QGroupBox { color:#7aa2f7; border:1px solid #2a2d4a;
                border-radius:6px; margin-top:8px; padding-top:6px; }
    QGroupBox::title { subcontrol-origin:margin; left:8px; }
    QDoubleSpinBox, QComboBox, QSlider {
        background:#16161e; color:#c0caf5;
        border:1px solid #2a2d4a; border-radius:4px; padding:3px 6px; }
    QLabel { color:#c0caf5; }
    QTabWidget::pane { border:1px solid #2a2d4a; background:#1a1b26; }
"""


def _spin(lo: float = -1e6, hi: float = 1e6,
          suffix: str = "", decimals: int = 3,
          value: float = 0.0) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setDecimals(decimals)
    sb.setValue(value)
    if suffix:
        sb.setSuffix(f"  {suffix}")
    return sb


def _header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color:#7aa2f7; font-weight:bold; font-size:11px; padding: 6px 0 2px 0;")
    return lbl


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color:#565f89; font-size:9px; padding-top:4px;")
    lbl.setWordWrap(True)
    return lbl


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Nodal load / moment
# ─────────────────────────────────────────────────────────────────────────────

class _NodalTab(QWidget):
    """Concentrated load / moment at a node."""

    def __init__(self, project: Project, presel_node: str = ""):
        super().__init__()
        self.project = project
        lo = QVBoxLayout(self)
        lo.setSpacing(10)
        lo.setContentsMargins(14, 14, 14, 14)

        lo.addWidget(_header("Target node"))
        self._node_cb = QComboBox()
        self._node_cb.setToolTip("Select the node to receive this load")
        self._refresh_nodes()
        if presel_node:
            idx = self._node_cb.findData(presel_node)
            if idx >= 0:
                self._node_cb.setCurrentIndex(idx)
        lo.addWidget(self._node_cb)

        lo.addWidget(_header("Force components  (kN)"))
        frm = QFormLayout()
        frm.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        frm.setSpacing(8)
        self._fx = _spin(suffix="kN")
        self._fy = _spin(suffix="kN")
        frm.addRow("Fx  (→ right):", self._fx)
        frm.addRow("Fy  (↑ up):",    self._fy)

        lo.addWidget(_header("Moment  (kN·m)"))
        self._mz = _spin(suffix="kN·m")
        frm.addRow("Mz  (↺ CCW):",   self._mz)
        lo.addLayout(frm)

        lo.addWidget(_hint(
            "Positive Fx → right.  Positive Fy → up.  "
            "Positive Mz → anti-clockwise.  "
            "Set all to 0 to remove the load."))
        lo.addStretch()

    def _refresh_nodes(self):
        self._node_cb.clear()
        for nid, n in self.project.nodes.items():
            self._node_cb.addItem(f"{nid}  ({n.x:.2f}, {n.y:.2f} m)", nid)

    def load_from_node(self, node_id: str) -> None:
        node = self.project.nodes.get(node_id)
        if node and node.loads:
            ld = node.loads[0]
            self._fx.setValue(ld.Fx)
            self._fy.setValue(ld.Fy)
            self._mz.setValue(ld.Mz)

    def get_values(self) -> dict:
        return {
            "node_id": self._node_cb.currentData(),
            "Fx": self._fx.value(),
            "Fy": self._fy.value(),
            "Mz": self._mz.value(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Distributed load on member
# ─────────────────────────────────────────────────────────────────────────────

class _DistribTab(QWidget):
    """Linearly-varying distributed load along (or part of) a member."""

    def __init__(self, project: Project, presel_member: str = ""):
        super().__init__()
        self.project = project
        lo = QVBoxLayout(self)
        lo.setSpacing(10)
        lo.setContentsMargins(14, 14, 14, 14)

        lo.addWidget(_header("Target member"))
        self._mem_cb = QComboBox()
        self._refresh_members()
        if presel_member:
            idx = self._mem_cb.findData(presel_member)
            if idx >= 0:
                self._mem_cb.setCurrentIndex(idx)
        lo.addWidget(self._mem_cb)

        lo.addWidget(_header("Load direction"))
        self._dir_cb = QComboBox()
        for txt, val in [("Fy  — transverse, local (gravity)", "Fy"),
                         ("Fx  — axial, local",                "Fx"),
                         ("FY  — global vertical",             "FY"),
                         ("FX  — global horizontal",           "FX")]:
            self._dir_cb.addItem(txt, val)
        lo.addWidget(self._dir_cb)

        lo.addWidget(_header("Intensity"))
        frm = QFormLayout()
        frm.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        frm.setSpacing(8)
        self._w1 = _spin(suffix="kN/m")
        self._w2 = _spin(suffix="kN/m")
        frm.addRow("w₁  (at i-node):", self._w1)
        frm.addRow("w₂  (at j-node):", self._w2)
        lo.addLayout(frm)

        lo.addWidget(_header("Extent  (leave 0/0 for full span)"))
        frm2 = QFormLayout()
        frm2.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._x1 = _spin(lo=0, hi=1e4, suffix="m")
        self._x2 = _spin(lo=0, hi=1e4, suffix="m")
        frm2.addRow("x₁  (from i-node):", self._x1)
        frm2.addRow("x₂  (from i-node):", self._x2)
        lo.addLayout(frm2)

        lo.addWidget(_hint(
            "Negative Fy = downward gravity.  w₁ at start, w₂ at end → tapered load.  "
            "x₂ = 0 means 'extend to j-node'."))
        lo.addStretch()

    def _refresh_members(self):
        self._mem_cb.clear()
        for mid, m in self.project.members.items():
            self._mem_cb.addItem(
                f"{mid}  ({m.start_node_id} → {m.end_node_id})", mid)

    def get_values(self) -> dict:
        x2v = self._x2.value()
        return {
            "member_id": self._mem_cb.currentData(),
            "direction": self._dir_cb.currentData(),
            "w_start":   self._w1.value(),
            "w_end":     self._w2.value(),
            "x1":        self._x1.value(),
            "x2":        x2v if x2v > 0 else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 — Point load on member at exact x-position
# ─────────────────────────────────────────────────────────────────────────────

class _MemberPtTab(QWidget):
    """Concentrated load applied at exact distance x from the i-node."""

    def __init__(self, project: Project, presel_member: str = ""):
        super().__init__()
        self.project = project
        lo = QVBoxLayout(self)
        lo.setSpacing(10)
        lo.setContentsMargins(14, 14, 14, 14)

        lo.addWidget(_header("Target member"))
        self._mem_cb = QComboBox()
        # NOTE: signal connected AFTER self._x is created (see below)
        self._refresh_members()
        if presel_member:
            idx = self._mem_cb.findData(presel_member)
            if idx >= 0:
                self._mem_cb.setCurrentIndex(idx)
        lo.addWidget(self._mem_cb)

        # Position
        lo.addWidget(_header("Position along member"))

        frm = QFormLayout()
        frm.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        frm.setSpacing(8)
        self._x = _spin(lo=0.0, hi=1e4, suffix="m", decimals=3, value=0.0)
        self._x_lbl = QLabel("")     # shows fraction of span
        self._x_lbl.setStyleSheet("color:#565f89; font-size:9px;")
        self._x.valueChanged.connect(self._update_x_label)
        frm.addRow("x  (from i-node):", self._x)
        frm.addRow("",                  self._x_lbl)
        lo.addLayout(frm)

        # Load direction + magnitude
        lo.addWidget(_header("Load direction"))
        self._dir_cb = QComboBox()
        for txt, val in [("Fy  — transverse, local (gravity)", "Fy"),
                         ("Fx  — axial, local",                "Fx"),
                         ("FY  — global vertical",             "FY"),
                         ("FX  — global horizontal",           "FX"),
                         ("Mz  — moment",                      "Mz")]:
            self._dir_cb.addItem(txt, val)
        lo.addWidget(self._dir_cb)

        lo.addWidget(_header("Magnitude"))
        frm2 = QFormLayout()
        frm2.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._mag = _spin(suffix="kN  (kN·m for Mz)")
        frm2.addRow("P:", self._mag)
        lo.addLayout(frm2)

        lo.addWidget(_hint(
            "Negative Fy = downward.  x must be between 0 and member length.  "
            "Multiple point loads on the same member are accumulated."))
        lo.addStretch()

        # Connect AFTER self._x exists so _on_member_changed is safe to call
        self._mem_cb.currentIndexChanged.connect(self._on_member_changed)
        self._update_x_label()

    def _refresh_members(self):
        self._mem_cb.clear()
        for mid, m in self.project.members.items():
            L = self._member_length(m)
            self._mem_cb.addItem(
                f"{mid}  ({m.start_node_id}→{m.end_node_id})  L={L:.2f} m", mid)

    def _member_length(self, m) -> float:
        ni = self.project.nodes.get(m.start_node_id)
        nj = self.project.nodes.get(m.end_node_id)
        if ni and nj:
            return math.hypot(nj.x - ni.x, nj.y - ni.y)
        return 0.0

    def _current_length(self) -> float:
        mid = self._mem_cb.currentData()
        if mid and mid in self.project.members:
            return self._member_length(self.project.members[mid])
        return 0.0

    def _on_member_changed(self, _):
        L = self._current_length()
        self._x.setRange(0.0, max(L, 1e-6))
        self._update_x_label()

    def _update_x_label(self):
        L = self._current_length()
        x = self._x.value()
        if L > 0:
            pct = x / L * 100
            self._x_lbl.setText(f"= {pct:.1f}% of span  (L = {L:.3f} m)")
        else:
            self._x_lbl.setText("")

    def get_values(self) -> dict:
        return {
            "member_id": self._mem_cb.currentData(),
            "direction": self._dir_cb.currentData(),
            "magnitude": self._mag.value(),
            "x":         self._x.value(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Main Dialog
# ─────────────────────────────────────────────────────────────────────────────

class LoadsDialog(QDialog):
    """
    Modal dialog to define structural loads.

    Usage::

        dlg = LoadsDialog(project, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply()
    """

    def __init__(self, project: Project,
                 presel_node: str = "",
                 presel_member: str = "",
                 parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Loads Manager")
        self.setMinimumSize(480, 520)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # Title row
        title = QLabel("⬇  Define Loads")
        title.setStyleSheet(
            "color:#c0caf5; font-size:15px; font-weight:bold; padding:4px 0;")
        root.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#2a2d4a;")
        root.addWidget(sep)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabBar::tab { background:#24253a; color:#c0caf5;"
            " padding:6px 16px; border-radius:4px 4px 0 0; min-width:80px; }"
            "QTabBar::tab:selected { background:#364a82; color:#7aa2f7; }"
            "QTabBar::tab:hover    { background:#2e3155; }"
        )

        self._nodal_tab    = _NodalTab(project, presel_node)
        self._distrib_tab  = _DistribTab(project, presel_member)
        self._mem_pt_tab   = _MemberPtTab(project, presel_member)

        self._tabs.addTab(self._nodal_tab,   "Node Load")
        self._tabs.addTab(self._distrib_tab, "Distributed")
        self._tabs.addTab(self._mem_pt_tab,  "Point on Member")

        # Smart tab pre-selection
        if presel_member and not presel_node:
            self._tabs.setCurrentIndex(2)   # default to point-on-member
        root.addWidget(self._tabs)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("Apply Load")
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            "background:#364a82; color:#c0caf5; border-radius:5px; padding:6px 18px;")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            "background:#24253a; color:#c0caf5; border-radius:5px; padding:6px 18px;")
        root.addWidget(btn_box)

        self.setStyleSheet(_DIALOG_STYLE)

    # ── Public API ────────────────────────────────────────────────────────────

    def apply(self) -> None:
        """Apply the entered load to the project and emit signals."""
        tab = self._tabs.currentIndex()
        if tab == 0:
            self._apply_nodal()
        elif tab == 1:
            self._apply_distrib()
        else:
            self._apply_member_pt()

    # ── Apply helpers ─────────────────────────────────────────────────────────

    def _apply_nodal(self) -> None:
        vals    = self._nodal_tab.get_values()
        node_id = vals["node_id"]
        if not node_id:
            return
        node = self.project.nodes.get(node_id)
        if not node:
            return
        load = NodeLoad(Fx=vals["Fx"], Fy=vals["Fy"], Mz=vals["Mz"])
        node.loads = [load] if any([load.Fx, load.Fy, load.Mz]) else []
        self.project.node_changed.emit(node)

    def _apply_distrib(self) -> None:
        vals   = self._distrib_tab.get_values()
        mem_id = vals["member_id"]
        if not mem_id:
            return
        member = self.project.members.get(mem_id)
        if not member:
            return
        dl = DistLoad(
            direction=vals["direction"],
            w_start=vals["w_start"],
            w_end=vals["w_end"],
            x1=vals["x1"],
            x2=vals["x2"],
        )
        # Replace existing same-direction load
        member.dist_loads = [
            d for d in member.dist_loads if d.direction != dl.direction
        ]
        if dl.w_start != 0 or dl.w_end != 0:
            member.dist_loads.append(dl)
        self.project.member_changed.emit(member)

    def _apply_member_pt(self) -> None:
        vals   = self._mem_pt_tab.get_values()
        mem_id = vals["member_id"]
        if not mem_id:
            return
        member = self.project.members.get(mem_id)
        if not member:
            return
        if vals["magnitude"] == 0:
            return
        pl = PointLoad(
            direction=vals["direction"],
            magnitude=vals["magnitude"],
            x=vals["x"],
        )
        member.pt_loads.append(pl)
        self.project.member_changed.emit(member)
