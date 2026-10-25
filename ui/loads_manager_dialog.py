"""
ui/loads_manager_dialog.py
==========================
Centralized "Manage Loads" dialog — lists ALL project loads in one table
and provides Add / Edit / Delete controls.
"""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QLabel, QAbstractItemView, QMessageBox,
    QDialogButtonBox, QFrame,
)
from PyQt6.QtGui import QColor, QFont

from models.project import Project
from models.node import NodeLoad
from models.member import DistLoad, PointLoad

_STYLE = """
    QDialog       { background:#1a1b26; color:#c0caf5; }
    QTableWidget  { background:#16161e; color:#c0caf5;
                    gridline-color:#2a2d4a; border:1px solid #2a2d4a; }
    QHeaderView::section { background:#24253a; color:#7aa2f7;
                           border:1px solid #2a2d4a; padding:4px; }
    QTableWidget::item:selected { background:#364a82; }
    QPushButton   { background:#24253a; color:#c0caf5; border:1px solid #2a2d4a;
                    border-radius:5px; padding:5px 14px; }
    QPushButton:hover  { background:#364a82; }
    QPushButton#del    { color:#f7768e; border-color:#f7768e; }
    QPushButton#del:hover { background:#3d2030; }
    QLabel        { color:#c0caf5; }
"""

_COLS = ["Type", "ID", "Direction", "w₁ / Magnitude", "w₂ / x (m)", "Span %"]


class LoadsManagerDialog(QDialog):
    """
    Unified loads manager.

    Shows all NodeLoads, DistLoads and PointLoads in a single QTableWidget.
    Changes are written back to the project model on 'Close'.
    """

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Manage Loads")
        self.setMinimumSize(740, 460)
        self.setModal(True)
        self.setStyleSheet(_STYLE)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        # Title
        title = QLabel("📋  All Project Loads")
        title.setStyleSheet(
            "color:#c0caf5; font-size:14px; font-weight:bold; padding:2px 0;")
        root.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#2a2d4a;")
        root.addWidget(sep)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            _STYLE + "QTableWidget { alternate-background-color:#1e1f2e; }")
        root.addWidget(self._table)

        # Button row
        btn_row = QHBoxLayout()
        self._btn_add  = QPushButton("➕  Add Load")
        self._btn_edit = QPushButton("✏️  Edit Selected")
        self._btn_del  = QPushButton("🗑  Delete Selected")
        self._btn_del.setObjectName("del")
        for b in (self._btn_add, self._btn_edit, self._btn_del):
            btn_row.addWidget(b)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # Close button
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.accept)
        bb.button(QDialogButtonBox.StandardButton.Close).setStyleSheet(
            "background:#364a82; color:#c0caf5; border-radius:5px; padding:6px 18px;")
        root.addWidget(bb)

        # Connect
        self._btn_add.clicked.connect(self._add_load)
        self._btn_edit.clicked.connect(self._edit_load)
        self._btn_del.clicked.connect(self._delete_load)
        self._table.itemSelectionChanged.connect(self._on_selection)

        self._refresh()
        self._on_selection()

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _refresh(self) -> None:
        """Populate the table from the current project state."""
        self._table.setRowCount(0)
        self._rows: list[dict] = []   # metadata for each row

        # ── Node loads ──────────────────────────────────────────────────────
        for nid, node in self.project.nodes.items():
            for load in node.loads:
                comps = []
                if load.Fx: comps.append(f"Fx={load.Fx:.2f}")
                if load.Fy: comps.append(f"Fy={load.Fy:.2f}")
                if load.Mz: comps.append(f"Mz={load.Mz:.2f}")
                row_data = {
                    "kind": "node", "nid": nid, "load": load,
                    "type_lbl": "Node Load",
                    "id_lbl": f"N: {nid}",
                    "dir_lbl": " ".join(comps),
                    "mag_lbl": f"Fx={load.Fx:.2f}  Fy={load.Fy:.2f}  Mz={load.Mz:.2f}",
                    "extra_lbl": "",
                    "span_lbl": "",
                }
                self._add_row(row_data, QColor("#7aa2f7"))

        # ── Member distributed loads ────────────────────────────────────────
        for mid, mem in self.project.members.items():
            L = self._member_len(mid)
            for dl in mem.dist_loads:
                row_data = {
                    "kind": "dist", "mid": mid, "load": dl,
                    "type_lbl": "UDL",
                    "id_lbl": f"M: {mid}",
                    "dir_lbl": dl.direction,
                    "mag_lbl": f"{dl.w_start:.2f}",
                    "extra_lbl": f"{dl.w_end:.2f}",
                    "span_lbl": "full span",
                }
                self._add_row(row_data, QColor("#9ece6a"))

        # ── Member point loads ──────────────────────────────────────────────
        for mid, mem in self.project.members.items():
            L = self._member_len(mid)
            for pl in mem.pt_loads:
                pct = f"{pl.x / L * 100:.1f}%" if L > 0 else "?"
                row_data = {
                    "kind": "pt", "mid": mid, "load": pl,
                    "type_lbl": "Point Load",
                    "id_lbl": f"M: {mid}",
                    "dir_lbl": pl.direction,
                    "mag_lbl": f"{pl.magnitude:.2f} kN",
                    "extra_lbl": f"{pl.x:.3f}",
                    "span_lbl": pct,
                }
                self._add_row(row_data, QColor("#f7768e"))

    def _add_row(self, data: dict, accent: QColor) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        self._rows.append(data)
        cells = [
            data["type_lbl"], data["id_lbl"], data["dir_lbl"],
            data["mag_lbl"], data["extra_lbl"], data["span_lbl"],
        ]
        for c, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setForeground(accent if c == 0 else QColor("#c0caf5"))
            if c == 0:
                item.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            self._table.setItem(r, c, item)

    def _member_len(self, mid: str) -> float:
        m  = self.project.members.get(mid)
        if not m:
            return 0.0
        ni = self.project.nodes.get(m.start_node_id)
        nj = self.project.nodes.get(m.end_node_id)
        if ni and nj:
            return math.hypot(nj.x - ni.x, nj.y - ni.y)
        return 0.0

    def _selected_row(self) -> Optional[int]:
        rows = self._table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _on_selection(self) -> None:
        has = self._selected_row() is not None
        self._btn_edit.setEnabled(has)
        self._btn_del.setEnabled(has)

    # ── Actions ────────────────────────────────────────────────────────────────

    def _add_load(self) -> None:
        from ui.loads_dialog import LoadsDialog
        dlg = LoadsDialog(self.project, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply()
            self._refresh()

    def _edit_load(self) -> None:
        r = self._selected_row()
        if r is None:
            return
        data = self._rows[r]
        from ui.loads_dialog import LoadsDialog
        presel_node   = data.get("nid", "")
        presel_member = data.get("mid", "")
        dlg = LoadsDialog(self.project,
                          presel_node=presel_node,
                          presel_member=presel_member,
                          parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply()
            self._refresh()

    def _delete_load(self) -> None:
        r = self._selected_row()
        if r is None:
            return
        data = self._rows[r]
        ans = QMessageBox.question(
            self, "Delete Load",
            f"Delete this {data['type_lbl']} from {data['id_lbl']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes:
            return

        if data["kind"] == "node":
            node = self.project.nodes.get(data["nid"])
            if node:
                node.loads = [l for l in node.loads if l is not data["load"]]
                self.project.node_changed.emit(node)
        elif data["kind"] == "dist":
            mem = self.project.members.get(data["mid"])
            if mem:
                mem.dist_loads = [l for l in mem.dist_loads
                                   if l is not data["load"]]
                self.project.member_changed.emit(mem)
        elif data["kind"] == "pt":
            mem = self.project.members.get(data["mid"])
            if mem:
                mem.pt_loads = [l for l in mem.pt_loads
                                 if l is not data["load"]]
                self.project.member_changed.emit(mem)

        self._refresh()
