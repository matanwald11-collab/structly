"""
ui/influence_dialog.py
======================
Dialog for configuring and launching an Influence Line Diagram (ILD) computation.

Usage
-----
    dlg = InfluenceLineDialog(project, target_member_id, target_x, parent=self)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        cfg = dlg.get_config()
        # cfg = {"target_member_id", "target_x", "force_type", "path_member_ids", "n_points"}
"""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QSpinBox, QDoubleSpinBox,
    QDialogButtonBox, QGroupBox, QListWidget,
    QListWidgetItem, QAbstractItemView, QFrame,
)

from models.project import Project


_STYLE = """
    QDialog   { background:#1a1b26; color:#c0caf5; }
    QGroupBox { color:#7aa2f7; border:1px solid #2a2d4a;
                border-radius:6px; margin-top:8px; padding-top:6px; }
    QGroupBox::title { subcontrol-origin:margin; left:8px; }
    QDoubleSpinBox, QSpinBox, QComboBox {
        background:#16161e; color:#c0caf5;
        border:1px solid #2a2d4a; border-radius:4px; padding:3px 6px; }
    QListWidget {
        background:#16161e; color:#c0caf5;
        border:1px solid #2a2d4a; border-radius:4px; }
    QListWidget::item:selected { background:#364a82; }
    QLabel { color:#c0caf5; }
"""


class InfluenceLineDialog(QDialog):
    """
    Configure influence line target and load path.

    Parameters
    ----------
    project           : active Project
    target_member_id  : pre-selected target member (from canvas click)
    target_x          : pre-filled position along target member (m)
    """

    def __init__(self, project: Project,
                 target_member_id: str = "",
                 target_x: float = 0.0,
                 parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Influence Line Diagram")
        self.setMinimumWidth(440)
        self.setModal(True)
        self.setStyleSheet(_STYLE)

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Title ──────────────────────────────────────────────────────────
        title = QLabel("📈  Influence Line Diagram Setup")
        title.setStyleSheet(
            "color:#c0caf5; font-size:14px; font-weight:bold; padding:4px 0;")
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#2a2d4a;")
        root.addWidget(sep)

        # ── Target point ───────────────────────────────────────────────────
        tgt_grp = QGroupBox("Target Point  (where force is measured)")
        tf = QFormLayout(tgt_grp)
        tf.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._tgt_member = QComboBox()
        for mid in project.members:
            m = project.members[mid]
            L = self._member_length(mid)
            self._tgt_member.addItem(
                f"{mid}  ({m.start_node_id}→{m.end_node_id})  L={L:.2f} m", mid)
        if target_member_id:
            idx = self._tgt_member.findData(target_member_id)
            if idx >= 0:
                self._tgt_member.setCurrentIndex(idx)
        tf.addRow("Target member:", self._tgt_member)

        self._tgt_x = QDoubleSpinBox()
        self._tgt_x.setRange(0.0, 1e4)
        self._tgt_x.setDecimals(3)
        self._tgt_x.setSuffix("  m")
        self._tgt_x.setValue(target_x)
        tf.addRow("Position x:", self._tgt_x)

        self._tgt_x_lbl = QLabel("")
        self._tgt_x_lbl.setStyleSheet("color:#565f89; font-size:9px;")
        tf.addRow("", self._tgt_x_lbl)
        root.addWidget(tgt_grp)

        # ── Force type ─────────────────────────────────────────────────────
        ft_grp = QGroupBox("Internal Force  (influence ordinate)")
        ff = QFormLayout(ft_grp)
        self._force_cb = QComboBox()
        for lbl, val in [("M — Bending Moment  (kN·m)", "M"),
                         ("T — Shear Force  (kN)",      "T"),
                         ("N — Axial Force  (kN)",      "N")]:
            self._force_cb.addItem(lbl, val)
        ff.addRow("Force type:", self._force_cb)
        root.addWidget(ft_grp)

        # ── Load path ──────────────────────────────────────────────────────
        path_grp = QGroupBox("Load Path  (Ctrl+click = multi-select)")
        pl = QVBoxLayout(path_grp)
        path_hint = QLabel(
            "Select the member(s) along which the 1 kN unit load travels:")
        path_hint.setStyleSheet("color:#565f89; font-size:9px;")
        pl.addWidget(path_hint)

        self._path_list = QListWidget()
        self._path_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._path_list.setMinimumHeight(120)
        for mid in project.members:
            m = project.members[mid]
            L = self._member_length(mid)
            item = QListWidgetItem(
                f"{mid}  ({m.start_node_id}→{m.end_node_id})  L={L:.2f} m")
            item.setData(Qt.ItemDataRole.UserRole, mid)
            self._path_list.addItem(item)
            # Pre-select if only one member (common case)
            if len(project.members) == 1:
                item.setSelected(True)
        # Fallback: pre-select target member's path
        if target_member_id:
            for i in range(self._path_list.count()):
                it = self._path_list.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == target_member_id:
                    it.setSelected(True)
        pl.addWidget(self._path_list)
        root.addWidget(path_grp)

        # ── Resolution ─────────────────────────────────────────────────────
        res_grp = QGroupBox("Resolution")
        rf = QFormLayout(res_grp)
        self._n_pts = QSpinBox()
        self._n_pts.setRange(5, 100)
        self._n_pts.setValue(25)
        self._n_pts.setSuffix("  positions")
        rf.addRow("Load positions:", self._n_pts)
        root.addWidget(res_grp)

        # ── Buttons ────────────────────────────────────────────────────────
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Compute ILD")
        bb.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            "background:#364a82; color:#c0caf5; border-radius:5px; padding:6px 18px;")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            "background:#24253a; color:#c0caf5; border-radius:5px; padding:6px 18px;")
        root.addWidget(bb)

        # Connect update callbacks
        self._tgt_member.currentIndexChanged.connect(self._update_x_range)
        self._tgt_x.valueChanged.connect(self._update_x_label)
        self._update_x_range()

    # ── Helpers ────────────────────────────────────────────────────────────

    def _member_length(self, mid: str) -> float:
        m  = self.project.members.get(mid)
        if not m:
            return 0.0
        ni = self.project.nodes.get(m.start_node_id)
        nj = self.project.nodes.get(m.end_node_id)
        if ni and nj:
            return math.hypot(nj.x - ni.x, nj.y - ni.y)
        return 0.0

    def _update_x_range(self) -> None:
        mid = self._tgt_member.currentData()
        L   = self._member_length(mid) if mid else 0.0
        self._tgt_x.setRange(0.0, max(L, 1e-6))
        self._update_x_label()

    def _update_x_label(self) -> None:
        mid = self._tgt_member.currentData()
        L   = self._member_length(mid) if mid else 0.0
        x   = self._tgt_x.value()
        if L > 0:
            pct = x / L * 100
            self._tgt_x_lbl.setText(f"= {pct:.1f}% of span  (L = {L:.3f} m)")
        else:
            self._tgt_x_lbl.setText("")

    # ── Public API ─────────────────────────────────────────────────────────

    def get_config(self) -> dict:
        """Return configuration dict after the dialog is accepted."""
        selected = [
            self._path_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._path_list.count())
            if self._path_list.item(i).isSelected()
        ]
        return {
            "target_member_id": self._tgt_member.currentData(),
            "target_x":         self._tgt_x.value(),
            "force_type":       self._force_cb.currentData(),
            "path_member_ids":  selected,
            "n_points":         self._n_pts.value(),
        }
