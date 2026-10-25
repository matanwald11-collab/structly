"""
ui/main_window.py
=================
Main application window for Structly.

Key design choices:
  • Toolbar uses explicit QAction objects (PyQt6 removed the addAction(text,slot,shortcut) overload)
  • Diagram types use structural notation: M (moment), T (shear), N (axial)
  • Cursor position is shown on the RIGHT side of the status bar
  • Loads button opens LoadsDialog
  • Reaction labels use "R" prefix on result overlays
"""
from __future__ import annotations

import sys
from typing import Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import (
    QAction, QKeySequence, QColor, QPalette, QFont,
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QToolBar, QStatusBar,
    QLabel, QFileDialog, QMessageBox, QDockWidget,
    QTabWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QFormLayout, QDoubleSpinBox, QComboBox, QCheckBox,
    QPushButton, QTableWidget, QTableWidgetItem, QApplication,
    QSizePolicy,
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import numpy as np

from models.project import Project
from models.node import Node, SupportType, NodeLoad
from models.member import Member, Releases, DistLoad
from models.section import CrossSection
from engine.solver import Solver, Results, SolverError, InfluenceLineResult
from ui.canvas import StructureScene, StructureView, Mode
from ui.loads_dialog import LoadsDialog
from ui.loads_manager_dialog import LoadsManagerDialog
from ui.influence_dialog import InfluenceLineDialog


# ─── Dark Palette ────────────────────────────────────────────────────────────

def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    c = {
        QPalette.ColorRole.Window:          QColor("#1a1b26"),
        QPalette.ColorRole.WindowText:      QColor("#c0caf5"),
        QPalette.ColorRole.Base:            QColor("#16161e"),
        QPalette.ColorRole.AlternateBase:   QColor("#1e1e2e"),
        QPalette.ColorRole.ToolTipBase:     QColor("#1a1b26"),
        QPalette.ColorRole.ToolTipText:     QColor("#c0caf5"),
        QPalette.ColorRole.Text:            QColor("#c0caf5"),
        QPalette.ColorRole.Button:          QColor("#24253a"),
        QPalette.ColorRole.ButtonText:      QColor("#c0caf5"),
        QPalette.ColorRole.BrightText:      QColor("#ff0000"),
        QPalette.ColorRole.Link:            QColor("#7aa2f7"),
        QPalette.ColorRole.Highlight:       QColor("#364a82"),
        QPalette.ColorRole.HighlightedText: QColor("#c0caf5"),
    }
    for role, color in c.items():
        pal.setColor(role, color)
    app.setPalette(pal)
    app.setFont(QFont("Segoe UI", 9))


# ─── Shared stylesheet ────────────────────────────────────────────────────────

DARK_STYLE = """
    QMainWindow  { background: #1a1b26; }
    QToolBar     { background: #16161e; border-bottom: 1px solid #2a2d4a;
                   spacing: 4px; padding: 4px; }
    QToolButton  { color: #c0caf5; background: #24253a;
                   border-radius: 6px; padding: 6px 10px; }
    QToolButton:checked { background: #364a82; color: #7aa2f7; }
    QToolButton:hover   { background: #2e3155; }
    QGroupBox    { color: #7aa2f7; border: 1px solid #2a2d4a;
                   border-radius: 6px; margin-top: 8px; padding-top: 6px; }
    QGroupBox::title { subcontrol-origin: margin; left: 8px; }
    QDoubleSpinBox, QComboBox {
                   background: #16161e; color: #c0caf5;
                   border: 1px solid #2a2d4a; border-radius: 4px;
                   padding: 2px 4px; }
    QPushButton  { background: #364a82; color: #c0caf5;
                   border-radius: 5px; padding: 5px 10px; }
    QPushButton:hover  { background: #4a5fa3; }
    QPushButton:pressed{ background: #2e3155; }
    QCheckBox    { color: #c0caf5; }
    QLabel       { color: #c0caf5; }
    QSplitter::handle { background: #2a2d4a; }
    QStatusBar   { background: #16161e; color: #565f89; }
"""

LIGHT_STYLE = """
    QMainWindow  { background: #f4f5fb; }
    QToolBar     { background: #e8eaf6; border-bottom: 1px solid #c5c8e8;
                   spacing: 4px; padding: 4px; }
    QToolButton  { color: #1a1b26; background: #dde1f4;
                   border-radius: 6px; padding: 6px 10px; }
    QToolButton:checked { background: #2255cc; color: #ffffff; }
    QToolButton:hover   { background: #c9cef0; }
    QGroupBox    { color: #2255cc; border: 1px solid #c5c8e8;
                   border-radius: 6px; margin-top: 8px; padding-top: 6px; }
    QGroupBox::title { subcontrol-origin: margin; left: 8px; }
    QDoubleSpinBox, QComboBox {
                   background: #ffffff; color: #1a1b26;
                   border: 1px solid #c5c8e8; border-radius: 4px;
                   padding: 2px 4px; }
    QPushButton  { background: #2255cc; color: #ffffff;
                   border-radius: 5px; padding: 5px 10px; }
    QPushButton:hover  { background: #1a45b8; }
    QCheckBox    { color: #1a1b26; }
    QLabel       { color: #1a1b26; }
    QSplitter::handle { background: #c5c8e8; }
    QStatusBar   { background: #e8eaf6; color: #3a3b50; }
"""


def apply_light_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    lc = {
        QPalette.ColorRole.Window:          QColor("#f4f5fb"),
        QPalette.ColorRole.WindowText:      QColor("#1a1b26"),
        QPalette.ColorRole.Base:            QColor("#ffffff"),
        QPalette.ColorRole.AlternateBase:   QColor("#eef0fa"),
        QPalette.ColorRole.ToolTipBase:     QColor("#ffffff"),
        QPalette.ColorRole.ToolTipText:     QColor("#1a1b26"),
        QPalette.ColorRole.Text:            QColor("#1a1b26"),
        QPalette.ColorRole.Button:          QColor("#dde1f4"),
        QPalette.ColorRole.ButtonText:      QColor("#1a1b26"),
        QPalette.ColorRole.BrightText:      QColor("#ff0000"),
        QPalette.ColorRole.Link:            QColor("#2255cc"),
        QPalette.ColorRole.Highlight:       QColor("#2255cc"),
        QPalette.ColorRole.HighlightedText: QColor("#ffffff"),
    }
    for role, color in lc.items():
        pal.setColor(role, color)
    app.setPalette(pal)
    app.setFont(QFont("Segoe UI", 9))


# ─── Properties Panel ────────────────────────────────────────────────────────

class PropertiesPanel(QWidget):
    """Right panel: shows/edits properties of the selected item."""

    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        self._current: Optional[Node | Member] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self._title = QLabel("Nothing selected")
        self._title.setStyleSheet(
            "color:#7aa2f7; font-weight:bold; font-size:12px;"
            " padding:4px; border-bottom:1px solid #2a2d4a;")
        layout.addWidget(self._title)

        # ── Node group ────────────────────────────────────────────────────────
        self._node_grp = QGroupBox("Node Properties")
        nf = QFormLayout(self._node_grp)
        nf.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._n_id  = QLabel()
        nf.addRow("ID:", self._n_id)
        self._n_x   = QDoubleSpinBox(); self._n_x.setRange(-1e6, 1e6)
        self._n_x.setSuffix(" m")
        self._n_y   = QDoubleSpinBox(); self._n_y.setRange(-1e6, 1e6)
        self._n_y.setSuffix(" m")
        nf.addRow("X:", self._n_x)
        nf.addRow("Y:", self._n_y)
        self._n_sup = QComboBox()
        for s in SupportType:
            self._n_sup.addItem(s.value, s)
        nf.addRow("Support:", self._n_sup)
        self._n_apply = QPushButton("Apply")
        self._n_apply.clicked.connect(self._apply_node)
        nf.addRow(self._n_apply)

        # Nodal load sub-group
        load_grp = QGroupBox("Point Load")
        lf = QFormLayout(load_grp)
        self._l_fx = QDoubleSpinBox(); self._l_fx.setRange(-1e6, 1e6)
        self._l_fx.setSuffix(" kN")
        self._l_fy = QDoubleSpinBox(); self._l_fy.setRange(-1e6, 1e6)
        self._l_fy.setSuffix(" kN")
        self._l_mz = QDoubleSpinBox(); self._l_mz.setRange(-1e6, 1e6)
        self._l_mz.setSuffix(" kN·m")
        lf.addRow("Fx:", self._l_fx)
        lf.addRow("Fy:", self._l_fy)
        lf.addRow("Mz:", self._l_mz)
        self._l_apply = QPushButton("Set Load")
        self._l_apply.clicked.connect(self._apply_node_load)
        lf.addRow(self._l_apply)
        nf.addRow(load_grp)
        layout.addWidget(self._node_grp)

        # ── Member group ──────────────────────────────────────────────────────
        self._mem_grp = QGroupBox("Member Properties")
        mf = QFormLayout(self._mem_grp)
        self._m_id  = QLabel()
        mf.addRow("ID:", self._m_id)
        self._m_E   = QDoubleSpinBox(); self._m_E.setRange(0, 1e12)
        self._m_E.setSuffix(" kN/m²"); self._m_E.setDecimals(0)
        self._m_A   = QDoubleSpinBox(); self._m_A.setRange(0, 1e6)
        self._m_A.setSuffix(" m²");    self._m_A.setDecimals(6)
        self._m_Iz  = QDoubleSpinBox(); self._m_Iz.setRange(0, 1e6)
        self._m_Iz.setSuffix(" m⁴");   self._m_Iz.setDecimals(8)
        mf.addRow("E:", self._m_E)
        mf.addRow("A:", self._m_A)
        mf.addRow("Iz:", self._m_Iz)

        rel_grp = QGroupBox("End Releases")
        rl = QFormLayout(rel_grp)
        self._rs_mz = QCheckBox("Mz — hinge"); rl.addRow("Start:", self._rs_mz)
        self._rs_fy = QCheckBox("Fy — shear"); rl.addRow("",       self._rs_fy)
        self._rs_fx = QCheckBox("Fx — axial"); rl.addRow("",       self._rs_fx)
        self._re_mz = QCheckBox("Mz — hinge"); rl.addRow("End:",   self._re_mz)
        self._re_fy = QCheckBox("Fy — shear"); rl.addRow("",       self._re_fy)
        self._re_fx = QCheckBox("Fx — axial"); rl.addRow("",       self._re_fx)
        mf.addRow(rel_grp)

        udl_grp = QGroupBox("Uniform Dist. Load")
        uf = QFormLayout(udl_grp)
        self._udl_w = QDoubleSpinBox(); self._udl_w.setRange(-1e6, 1e6)
        self._udl_w.setSuffix(" kN/m")
        uf.addRow("w (Fy):", self._udl_w)
        self._udl_apply = QPushButton("Set UDL")
        self._udl_apply.clicked.connect(self._apply_udl)
        uf.addRow(self._udl_apply)
        mf.addRow(udl_grp)

        self._m_apply = QPushButton("Apply Section & Releases")
        self._m_apply.clicked.connect(self._apply_member)
        mf.addRow(self._m_apply)
        layout.addWidget(self._mem_grp)

        layout.addStretch()
        self._show_nothing()

    # ── Public API ────────────────────────────────────────────────────────────

    def show_item(self, item) -> None:
        self._current = item
        if item is None:
            self._show_nothing()
        elif isinstance(item, Node):
            self._show_node(item)
        elif isinstance(item, Member):
            self._show_member(item)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _show_nothing(self) -> None:
        self._title.setText("Nothing selected")
        self._node_grp.hide()
        self._mem_grp.hide()

    def _show_node(self, n: Node) -> None:
        self._title.setText(f"Node  {n.id}")
        self._node_grp.show(); self._mem_grp.hide()
        self._n_id.setText(n.id)
        self._n_x.setValue(n.x)
        self._n_y.setValue(n.y)
        idx = self._n_sup.findData(n.support)
        if idx >= 0:
            self._n_sup.setCurrentIndex(idx)
        if n.loads:
            l = n.loads[0]
            self._l_fx.setValue(l.Fx)
            self._l_fy.setValue(l.Fy)
            self._l_mz.setValue(l.Mz)
        else:
            self._l_fx.setValue(0)
            self._l_fy.setValue(0)
            self._l_mz.setValue(0)

    def _show_member(self, m: Member) -> None:
        self._title.setText(f"Member  {m.id}")
        self._mem_grp.show(); self._node_grp.hide()
        self._m_id.setText(m.id)
        self._m_E.setValue(m.section.E)
        self._m_A.setValue(m.section.A)
        self._m_Iz.setValue(m.section.Iz)
        self._rs_mz.setChecked(m.releases_start.Mz)
        self._rs_fy.setChecked(m.releases_start.Fy)
        self._rs_fx.setChecked(m.releases_start.Fx)
        self._re_mz.setChecked(m.releases_end.Mz)
        self._re_fy.setChecked(m.releases_end.Fy)
        self._re_fx.setChecked(m.releases_end.Fx)
        if m.dist_loads:
            self._udl_w.setValue(m.dist_loads[0].w_start)
        else:
            self._udl_w.setValue(0.0)

    def _apply_node(self) -> None:
        n = self._current
        if not isinstance(n, Node):
            return
        n.x       = self._n_x.value()
        n.y       = self._n_y.value()
        n.support = self._n_sup.currentData()
        self.project.node_changed.emit(n)

    def _apply_node_load(self) -> None:
        n = self._current
        if not isinstance(n, Node):
            return
        load = NodeLoad(Fx=self._l_fx.value(),
                        Fy=self._l_fy.value(),
                        Mz=self._l_mz.value())
        n.loads = [load] if any([load.Fx, load.Fy, load.Mz]) else []
        self.project.node_changed.emit(n)

    def _apply_member(self) -> None:
        m = self._current
        if not isinstance(m, Member):
            return
        m.section = CrossSection(
            name="Custom",
            E=self._m_E.value(),
            G=m.section.G,
            A=self._m_A.value(),
            Iz=self._m_Iz.value(),
            J=m.section.J,
        )
        m.releases_start = Releases(
            Fx=self._rs_fx.isChecked(),
            Fy=self._rs_fy.isChecked(),
            Mz=self._rs_mz.isChecked(),
        )
        m.releases_end = Releases(
            Fx=self._re_fx.isChecked(),
            Fy=self._re_fy.isChecked(),
            Mz=self._re_mz.isChecked(),
        )
        self.project.member_changed.emit(m)

    def _apply_udl(self) -> None:
        m = self._current
        if not isinstance(m, Member):
            return
        w = self._udl_w.value()
        if w == 0:
            m.dist_loads = []
        else:
            m.dist_loads = [DistLoad(direction='Fy', w_start=w, w_end=w)]
        self.project.member_changed.emit(m)


# ─── Results Panel (matplotlib) ──────────────────────────────────────────────

class ResultsPanel(QWidget):
    """Bottom panel: embedded matplotlib tabs for M / T / N diagrams."""

    # Map internal dtype key → display label (structural notation)
    DTYPE_LABELS = {
        "M":    "Bending Moment M (kN·m)",
        "T":    "Shear Force T (kN)",
        "N":    "Axial Force N (kN)",
        "disp": "Displacements (m)",
        "R":    "Support Reactions R",
    }

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(200)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabBar::tab { background:#24253a; color:#c0caf5;"
            " padding:5px 14px; border-radius:4px 4px 0 0; }"
            "QTabBar::tab:selected { background:#364a82; }"
        )
        layout.addWidget(self._tabs)

        self._figures: dict[str, tuple[Figure, FigureCanvasQTAgg]] = {}
        for dtype, label in [
            ("M",    "M"),
            ("T",    "T"),
            ("N",    "N"),
            ("disp", "Disp"),
            ("R",    "R"),
        ]:
            fig = Figure(figsize=(6, 2.2), facecolor="#1a1b26")
            fig.subplots_adjust(left=0.06, right=0.98, top=0.88, bottom=0.18)
            canvas = FigureCanvasQTAgg(fig)
            canvas.setStyleSheet("background:#1a1b26;")
            self._tabs.addTab(canvas, label)
            self._figures[dtype] = (fig, canvas)

        self._tab_map = {"M": 0, "T": 1, "N": 2, "disp": 3, "R": 4, "IL": 5}

        # ILD tab
        fig_il = Figure(figsize=(6, 2.2), facecolor="#1a1b26")
        fig_il.subplots_adjust(left=0.06, right=0.98, top=0.88, bottom=0.18)
        canvas_il = FigureCanvasQTAgg(fig_il)
        canvas_il.setStyleSheet("background:#1a1b26;")
        self._tabs.addTab(canvas_il, "IL")
        self._figures["IL"] = (fig_il, canvas_il)

    def plot_results(self, results: Results, project: Project) -> None:
        """Populate all matplotlib tabs from a solved Results object."""
        colors = {"M": "#f7768e", "T": "#9ece6a", "N": "#7aa2f7"}

        for dtype, color in colors.items():
            self._plot_diagram(dtype, results, project, color)

        self._plot_displacements(results, project)
        self._plot_reactions(results, project)

    def _plot_diagram(self, dtype: str, results: Results,
                      project: Project, color: str) -> None:
        fig, canvas = self._figures[dtype]
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor("#16161e")
        for side in ("top", "bottom", "left", "right"):
            ax.spines[side].set_color("#2a2d4a")
        ax.tick_params(colors="#565f89", labelsize=7)
        ax.set_xlabel("Position (m)", color="#565f89", fontsize=7)
        ax.set_ylabel(self.DTYPE_LABELS[dtype], color="#565f89", fontsize=7)
        ax.set_title(self.DTYPE_LABELS[dtype], color="#c0caf5", fontsize=9, pad=4)
        ax.axhline(0, color="#2a2d4a", linewidth=0.8)
        ax.grid(True, color="#1c1e2e", linestyle="--", linewidth=0.5)

        # Map dtype → MemberResult field
        field_map = {"M": "bmd", "T": "sfd", "N": "afd"}
        result_attr = field_map[dtype]

        offset = 0.0
        member_labels = []
        member_xticks = []
        for mid, mr in results.members.items():
            vals = getattr(mr, result_attr)
            xs   = [x + offset for x in mr.positions]
            ax.plot(xs, vals, color=color, linewidth=1.5)
            ax.fill_between(xs, vals, 0,
                            where=[v >= 0 for v in vals],
                            alpha=0.25, color=color)
            ax.fill_between(xs, vals, 0,
                            where=[v < 0 for v in vals],
                            alpha=0.25, color="#bb9af7")

            # ── Numerical annotations ─────────────────────────────────────
            def _ann(xv: float, yv: float, txt: str) -> None:
                ax.annotate(txt, xy=(xv, yv),
                            xytext=(4, 4), textcoords="offset points",
                            color="#c0caf5", fontsize=6.5,
                            arrowprops=dict(arrowstyle="-",
                                           color="#565f89", lw=0.6))
            # Endpoint values
            _ann(xs[0],  vals[0],  f"{vals[0]:.2f}")
            _ann(xs[-1], vals[-1], f"{vals[-1]:.2f}")
            # Peak max and min within this member
            i_max = int(np.argmax(vals))
            i_min = int(np.argmin(vals))
            if i_max not in (0, len(vals) - 1):
                _ann(xs[i_max], vals[i_max], f"{vals[i_max]:.2f}")
            if i_min not in (0, len(vals) - 1) and i_min != i_max:
                _ann(xs[i_min], vals[i_min], f"{vals[i_min]:.2f}")

            member_labels.append(mid)
            member_xticks.append(offset + mr.length / 2)
            offset += mr.length

        ax.set_xticks(member_xticks)
        ax.set_xticklabels(member_labels, color="#565f89", fontsize=7)
        canvas.draw()

    def _plot_displacements(self, results: Results, project: Project) -> None:
        fig, canvas = self._figures["disp"]
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor("#16161e")
        for side in ("top", "bottom", "left", "right"):
            ax.spines[side].set_color("#2a2d4a")
        ax.tick_params(colors="#565f89", labelsize=7)
        ax.set_title("Node Displacements", color="#c0caf5", fontsize=9, pad=4)
        ax.set_ylabel("Displacement (m)", color="#565f89", fontsize=7)
        ax.grid(True, color="#1c1e2e", linestyle="--", linewidth=0.5)

        ids = list(results.nodes.keys())
        dxs = [results.nodes[i].dx for i in ids]
        dys = [results.nodes[i].dy for i in ids]
        xs  = range(len(ids))
        ax.bar([x - 0.2 for x in xs], dxs, 0.38,
               label="DX", color="#7aa2f7", alpha=0.8)
        ax.bar([x + 0.2 for x in xs], dys, 0.38,
               label="DY", color="#9ece6a", alpha=0.8)
        ax.set_xticks(list(xs))
        ax.set_xticklabels(ids, color="#565f89", fontsize=7)
        ax.legend(fontsize=7, labelcolor="#c0caf5",
                  facecolor="#24253a", edgecolor="#2a2d4a")
        ax.axhline(0, color="#2a2d4a", linewidth=0.8)
        canvas.draw()

    def _plot_reactions(self, results: Results, project: Project) -> None:
        """Plot support reactions labelled 'R' on bar chart."""
        fig, canvas = self._figures["R"]
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor("#16161e")
        for side in ("top", "bottom", "left", "right"):
            ax.spines[side].set_color("#2a2d4a")
        ax.tick_params(colors="#565f89", labelsize=7)
        ax.set_title("Support Reactions  R", color="#c0caf5", fontsize=9, pad=4)
        ax.set_ylabel("Force / Moment (kN, kN·m)", color="#565f89", fontsize=7)
        ax.grid(True, color="#1c1e2e", linestyle="--", linewidth=0.5)
        ax.axhline(0, color="#2a2d4a", linewidth=0.8)

        # Only show nodes that are supported
        sup_ids = [nid for nid, n in project.nodes.items()
                   if n.support != SupportType.FREE]
        xs   = list(range(len(sup_ids)))
        rfx  = [results.nodes[nid].rxn_fx  if nid in results.nodes else 0 for nid in sup_ids]
        rfy  = [results.nodes[nid].rxn_fy  if nid in results.nodes else 0 for nid in sup_ids]
        rmz  = [results.nodes[nid].rxn_mz  if nid in results.nodes else 0 for nid in sup_ids]

        w = 0.25
        ax.bar([x - w   for x in xs], rfx, w, label="Rx (kN)",   color="#f7768e", alpha=0.85)
        ax.bar([x       for x in xs], rfy, w, label="Ry (kN)",   color="#9ece6a", alpha=0.85)
        ax.bar([x + w   for x in xs], rmz, w, label="Rz (kN·m)", color="#bb9af7", alpha=0.85)

        # Label each bar with its value
        for bars in ax.containers:
            ax.bar_label(bars, fmt="%.2f", fontsize=6, color="#c0caf5", padding=2)

        labels = [f"R  {nid}" for nid in sup_ids]
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, color="#e0af68", fontsize=8, fontweight="bold")
        ax.legend(fontsize=7, labelcolor="#c0caf5",
                  facecolor="#24253a", edgecolor="#2a2d4a")
        canvas.draw()

    def clear(self) -> None:
        for fig, canvas in self._figures.values():
            fig.clear()
            canvas.draw()

    def show_tab(self, name: str) -> None:
        idx = self._tab_map.get(name, 0)
        self._tabs.setCurrentIndex(idx)

    def plot_influence_line(self, il_result) -> None:
        """Plot an Influence Line Diagram in the IL tab."""
        fig, canvas = self._figures["IL"]
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor("#16161e")
        for side in ("top", "bottom", "left", "right"):
            ax.spines[side].set_color("#2a2d4a")
        ax.tick_params(colors="#565f89", labelsize=7)
        ax.set_xlabel("Load position along path (m)", color="#565f89", fontsize=7)
        force_labels = {"M": "M  (kN·m / kN)", "T": "T  (kN / kN)", "N": "N  (kN / kN)"}
        ylabel = force_labels.get(il_result.force_type, "Influence ordinate")
        ax.set_ylabel(ylabel, color="#565f89", fontsize=7)
        ax.set_title(
            f"Influence Line — {il_result.force_type} at "
            f"{il_result.target_member_id}  x={il_result.target_x:.2f} m",
            color="#c0caf5", fontsize=9, pad=4)
        ax.axhline(0, color="#565f89", linewidth=0.8)
        ax.grid(True, color="#1c1e2e", linestyle="--", linewidth=0.5)

        xs = il_result.positions
        ys = il_result.values
        col = "#f7768e"
        ax.plot(xs, ys, color=col, linewidth=1.8)
        ax.fill_between(xs, ys, 0, where=[v >= 0 for v in ys],
                        alpha=0.30, color=col)
        ax.fill_between(xs, ys, 0, where=[v < 0 for v in ys],
                        alpha=0.30, color="#7aa2f7")

        # Annotate max absolute ordinate (positive and negative)
        if ys:
            arr_ys    = np.array(ys)
            i_max_abs = int(np.argmax(np.abs(arr_ys)))
            i_min_raw = int(np.argmin(arr_ys))
            i_max_raw = int(np.argmax(arr_ys))
            ax.annotate(f"{ys[i_max_abs]:+.3f}", xy=(xs[i_max_abs], ys[i_max_abs]),
                        xytext=(4, 5), textcoords="offset points",
                        color="#9ece6a", fontsize=7, fontweight="bold")
            if i_min_raw != i_max_abs and abs(ys[i_min_raw]) > 1e-6:
                ax.annotate(f"{ys[i_min_raw]:+.3f}",
                            xy=(xs[i_min_raw], ys[i_min_raw]),
                            xytext=(4, -12), textcoords="offset points",
                            color="#7aa2f7", fontsize=7, fontweight="bold")
            if i_max_raw != i_max_abs and abs(ys[i_max_raw]) > 1e-6:
                ax.annotate(f"{ys[i_max_raw]:+.3f}",
                            xy=(xs[i_max_raw], ys[i_max_raw]),
                            xytext=(4, 5), textcoords="offset points",
                            color="#9ece6a", fontsize=7, fontweight="bold")
        canvas.draw()


# ─── Main Window ─────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Structly — 2D Structural Analysis")
        self.resize(1440, 880)

        self.project              = Project()
        self.solver               = Solver()
        self._results:              Optional[Results] = None
        self._result_type_active: str = ""   # active canvas overlay (bmd/sfd/afd)

        # Scene + View
        self.scene = StructureScene(self.project)
        self.view  = StructureView(self.scene)
        self.scene.item_selected.connect(self._on_item_selected)
        self.scene.status_update.connect(self._on_scene_status)
        self.scene.il_target_selected.connect(self._open_il_dialog)

        # Build UI components
        self._build_toolbar()
        self._build_central()
        self._build_status_bar()
        self._build_menu()

        self.setStyleSheet(DARK_STYLE)

    # ────────────────────────────────────────────────────────────────────────
    # Toolbar
    # ────────────────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        tb = QToolBar("Tools", self)
        tb.setIconSize(QSize(20, 20))
        tb.setMovable(False)
        self.addToolBar(tb)

        def _act(text: str, tip: str, key: Optional[str] = None,
                 checkable: bool = False) -> QAction:
            """Create and add a toolbar QAction (PyQt6 requires explicit QAction)."""
            a = QAction(text, self)
            a.setToolTip(tip)
            a.setCheckable(checkable)
            if key:
                a.setShortcut(QKeySequence(key))
            tb.addAction(a)
            return a

        # ── Editing modes ────────────────────────────────────────────────
        self._act_select = _act("⬆  Select",  "Select / move items (S)", "S", True)
        self._act_node   = _act("●  Node",    "Place node (N)",           "N", True)
        self._act_member = _act("━  Member",  "Draw member (M)",          "M", True)
        self._act_delete = _act("✕  Delete",  "Delete item  (Del)",       None, True)
        tb.addSeparator()

        # ── Loads ───────────────────────────────────────────────────────────────
        self._act_loads = _act("📄  Loads", "Manage Loads (L)", "L")
        tb.addSeparator()

        # ── Analysis ─────────────────────────────────────────────────────
        self._act_run    = _act("▶  Analyse", "Run analysis (F5)",        "F5")
        tb.addSeparator()

        # ── Result diagram toggles  (M / T / N / R, structural notation) ─
        self._act_M         = _act("M",        "Bending Moment Diagram", None, True)
        self._act_T         = _act("T",        "Shear Force Diagram",    None, True)
        self._act_N         = _act("N",        "Axial Force Diagram",    None, True)
        self._act_show_r    = _act("📈 R",     "Toggle Reactions (Ctrl+R)", "Ctrl+R", True)
        self._act_clear_res = _act("✖  Clear",  "Remove overlays", None)
        tb.addSeparator()
        self._act_fit = _act("⊡  Fit", "Fit view (F)", "F")
        tb.addSeparator()

        # ── Influence Line ────────────────────────────────────────────────
        self._act_il = _act("📈 IL", "Influence Line Diagram (I)", "I", True)
        tb.addSeparator()

        # ── Diagram scale spinbox ──────────────────────────────────────────────
        tb.addWidget(QLabel(" Scale:"))
        self._diag_scale_sb = QDoubleSpinBox()
        self._diag_scale_sb.setRange(0.1, 10.0)
        self._diag_scale_sb.setSingleStep(0.1)
        self._diag_scale_sb.setValue(1.0)
        self._diag_scale_sb.setDecimals(1)
        self._diag_scale_sb.setFixedWidth(70)
        self._diag_scale_sb.setToolTip("Diagram overlay scale factor")
        tb.addWidget(self._diag_scale_sb)
        tb.addSeparator()

        # ── Theme toggle ───────────────────────────────────────────────────────────
        self._act_theme = _act("☀️ Light", "Toggle dark/light theme", None, True)

        # Mode action group
        self._mode_actions = {
            Mode.SELECT:         self._act_select,
            Mode.ADD_NODE:       self._act_node,
            Mode.ADD_MEMBER:     self._act_member,
            Mode.DELETE:         self._act_delete,
            Mode.INFLUENCE_LINE: self._act_il,
        }
        self._act_select.setChecked(True)

        # Connect toolbar actions
        self._act_select.triggered.connect(lambda: self._set_mode(Mode.SELECT))
        self._act_node.triggered.connect(lambda:   self._set_mode(Mode.ADD_NODE))
        self._act_member.triggered.connect(lambda: self._set_mode(Mode.ADD_MEMBER))
        self._act_delete.triggered.connect(lambda: self._set_mode(Mode.DELETE))
        self._act_il.triggered.connect(lambda:     self._set_mode(Mode.INFLUENCE_LINE))
        self._act_loads.triggered.connect(self._open_loads_manager)
        self._act_run.triggered.connect(self._run_analysis)
        self._act_M.triggered.connect(lambda: self._show_diagram("M"))
        self._act_T.triggered.connect(lambda: self._show_diagram("T"))
        self._act_N.triggered.connect(lambda: self._show_diagram("N"))
        self._act_show_r.triggered.connect(self._toggle_reactions)
        self._act_clear_res.triggered.connect(self._clear_results)
        self._act_fit.triggered.connect(self.view.fit_all)
        self._act_theme.triggered.connect(self._toggle_theme)
        self._diag_scale_sb.valueChanged.connect(
            lambda v: self.scene.set_diagram_scale(v))

    # ────────────────────────────────────────────────────────────────────────
    # Central layout
    # ────────────────────────────────────────────────────────────────────────

    def _build_central(self) -> None:
        self._prop_panel = PropertiesPanel(self.project)
        self._prop_panel.setMinimumWidth(240)
        self._prop_panel.setMaximumWidth(320)

        h_split = QSplitter(Qt.Orientation.Horizontal)
        h_split.addWidget(self.view)
        h_split.addWidget(self._prop_panel)
        h_split.setStretchFactor(0, 1)
        h_split.setSizes([1100, 300])

        self._results_panel = ResultsPanel()
        self._results_panel.setVisible(False)

        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.addWidget(h_split)
        v_split.addWidget(self._results_panel)
        v_split.setStretchFactor(0, 1)
        v_split.setSizes([630, 230])

        self.setCentralWidget(v_split)

    # ────────────────────────────────────────────────────────────────────────
    # Status bar  (left = info messages,  right = cursor position)
    # ────────────────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        sb = QStatusBar(self)
        sb.setStyleSheet("QStatusBar { background:#16161e; color:#565f89; }")
        self.setStatusBar(sb)

        # Left side: general status messages
        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet("color:#565f89; padding: 0 8px;")
        sb.addWidget(self._status_lbl, 1)   # stretch=1 → fills remaining space

        # Structural element counts (permanent)
        self._node_count_lbl   = QLabel("Nodes: 0")
        self._member_count_lbl = QLabel("Members: 0")
        for lbl in (self._node_count_lbl, self._member_count_lbl):
            lbl.setStyleSheet("color:#364a82; padding: 0 8px;")
            sb.addPermanentWidget(lbl)

        # Separator
        sep = QLabel("|")
        sep.setStyleSheet("color:#2a2d4a;")
        sb.addPermanentWidget(sep)

        # RIGHT side: cursor world-coordinate display
        self._cursor_lbl = QLabel("X: —  m    Y: —  m")
        self._cursor_lbl.setStyleSheet(
            "color:#9ece6a; font-family: 'Consolas', monospace;"
            " font-size: 10px; padding: 0 12px;")
        self._cursor_lbl.setMinimumWidth(200)
        self._cursor_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        sb.addPermanentWidget(self._cursor_lbl)

        # Subscribe to project mutations
        self.project.node_added.connect(self._update_counts)
        self.project.node_removed.connect(self._update_counts)
        self.project.member_added.connect(self._update_counts)
        self.project.member_removed.connect(self._update_counts)
        self.project.project_reset.connect(self._update_counts)

        # Subscribe to canvas mouse-move for cursor coords
        # The scene emits status_update(msg) where msg may be just a position
        # string.  We'll also connect a dedicated cursor_moved signal below.
        self.scene.cursor_moved.connect(self._update_cursor)

    # ────────────────────────────────────────────────────────────────────────
    # Menu  (explicit QAction — PyQt6 dropped convenience overload)
    # ────────────────────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        mb = self.menuBar()
        mb.setStyleSheet(
            "QMenuBar { background:#16161e; color:#c0caf5; }"
            "QMenuBar::item:selected { background:#24253a; }"
            "QMenu { background:#1a1b26; color:#c0caf5;"
            "        border:1px solid #2a2d4a; }"
            "QMenu::item:selected { background:#364a82; }"
        )

        def _ma(menu, text: str, slot, shortcut=None) -> QAction:
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut is not None:
                a.setShortcut(shortcut)
            menu.addAction(a)
            return a

        # File
        file_m = mb.addMenu("File")
        _ma(file_m, "New",    self._new_project,  QKeySequence.StandardKey.New)
        _ma(file_m, "Open…",  self._open_project, QKeySequence.StandardKey.Open)
        _ma(file_m, "Save…",  self._save_project, QKeySequence.StandardKey.Save)
        file_m.addSeparator()
        _ma(file_m, "Exit",   self.close)

        # View
        view_m = mb.addMenu("View")
        _ma(view_m, "Fit All",         self.view.fit_all,           QKeySequence("F"))
        _ma(view_m, "Toggle Results",  self._toggle_results_panel)

        # Loads
        loads_m = mb.addMenu("Loads")
        _ma(loads_m, "Add / Edit Loads…", self._open_loads_dialog, QKeySequence("L"))

        # Analysis
        ana_m = mb.addMenu("Analysis")
        _ma(ana_m, "Run Analysis",    self._run_analysis,  QKeySequence("F5"))
        _ma(ana_m, "Clear Results",   self._clear_results)

        # Diagrams (structural notation M / T / N / R)
        diag_m = mb.addMenu("Diagrams")
        _ma(diag_m, "M — Bending Moment",  lambda: self._show_diagram("M"))
        _ma(diag_m, "T — Shear Force",     lambda: self._show_diagram("T"))
        _ma(diag_m, "N — Axial Force",     lambda: self._show_diagram("N"))
        _ma(diag_m, "R — Reactions",       lambda: self._show_diagram("R"))

        # Examples
        ex_m = mb.addMenu("Examples")
        _ma(ex_m, "Simply-Supported Beam (UDL)",  self._example_ssb)
        _ma(ex_m, "Propped Cantilever",            self._example_propped)
        _ma(ex_m, "Portal Frame",                  self._example_portal)

    # ────────────────────────────────────────────────────────────────────────
    # Slots
    # ────────────────────────────────────────────────────────────────────────

    def _set_mode(self, mode: Mode) -> None:
        for m, act in self._mode_actions.items():
            act.setChecked(m == mode)
        self.scene.set_mode(mode)

    def _on_scene_status(self, msg: str) -> None:
        """Non-coordinate status messages go to the left label."""
        # Cursor coords are forwarded via cursor_moved signal; skip them here
        if not msg.startswith("X:"):
            self._status_lbl.setText(msg)

    def _on_item_selected(self, item) -> None:
        self._prop_panel.show_item(item)

    def _update_counts(self, *_) -> None:
        self._node_count_lbl.setText(f"Nodes: {len(self.project.nodes)}")
        self._member_count_lbl.setText(f"Members: {len(self.project.members)}")

    def _update_cursor(self, wx: float, wy: float) -> None:
        """Receive world coordinates from the canvas and update bottom-right label."""
        self._cursor_lbl.setText(
            f"X: {wx:>7.2f} m    Y: {wy:>7.2f} m"
        )

    # ── Loads dialog ──────────────────────────────────────────────────────────

    def _open_loads_dialog(self) -> None:
        # Pre-select from canvas selection if possible
        selected = self.scene.selectedItems() if hasattr(self.scene, "selectedItems") else []
        presel_node = ""
        presel_member = ""
        from ui.canvas import NodeItem, MemberItem
        for item in selected:
            if isinstance(item, NodeItem):
                presel_node = item.node.id
                break
            if isinstance(item, MemberItem):
                presel_member = item.member.id
                break

        dlg = LoadsDialog(self.project,
                          presel_node=presel_node,
                          presel_member=presel_member,
                          parent=self)
        if dlg.exec() == LoadsDialog.DialogCode.Accepted:
            dlg.apply()
            self._status_lbl.setText("Load applied ✓")

    # ── Analysis ──────────────────────────────────────────────────────────────

    def _run_analysis(self) -> None:
        self.scene.clear_results()
        self._results_panel.clear()
        try:
            results = self.solver.run(self.project)
        except SolverError as e:
            QMessageBox.critical(self, "Analysis Failed", str(e))
            return
        self._results = results
        self._results_panel.plot_results(results, self.project)
        self._results_panel.setVisible(True)
        self._show_diagram("M")
        # Reactions are hidden by default — only drawn if toggle is active
        if self._act_show_r.isChecked():
            self.scene.show_reactions(results)
        self._status_lbl.setText(
            f"Analysis complete ✓  │  "
            f"max M = {results.max_moment():.2f} kN·m  │  "
            f"max T = {results.max_shear():.2f} kN  │  "
            f"max N = {results.max_axial():.2f} kN"
        )

    def _show_diagram(self, dtype: str) -> None:
        for key, act in {"M": self._act_M, "T": self._act_T,
                         "N": self._act_N}.items():
            act.setChecked(key == dtype)

        canvas_map = {"M": "bmd", "T": "sfd", "N": "afd"}
        canvas_type = canvas_map.get(dtype, "")
        self._result_type_active = canvas_type   # track for reaction toggle

        if self._results:
            if canvas_type:
                self.scene.show_results(self._results, canvas_type)
            self._results_panel.show_tab(dtype)
            self._results_panel.setVisible(True)

    def _clear_results(self) -> None:
        self.scene.clear_results()
        self._results_panel.clear()
        self._results = None
        for act in (self._act_M, self._act_T, self._act_N):
            act.setChecked(False)

    # ── Loads Manager ───────────────────────────────────────────────────────

    def _open_loads_manager(self) -> None:
        dlg = LoadsManagerDialog(self.project, parent=self)
        dlg.exec()

    # ── Reaction toggle ───────────────────────────────────────────────────────

    def _toggle_reactions(self) -> None:
        """Show or hide reaction arrows based on the toggle button state."""
        if self._results is None:
            self._act_show_r.setChecked(False)
            return
        if self._act_show_r.isChecked():
            self.scene.show_reactions(self._results)
        else:
            # Remove only reaction overlay items (keep diagram overlay intact)
            self.scene.clear_results()   # re-draw active diagram without reactions
            if self._result_type_active:
                self.scene.show_results(self._results, self._result_type_active)

    # ── Theme toggle ──────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        """Switch between dark and light mode."""
        app = QApplication.instance()
        if self._act_theme.isChecked():
            # Switch to light
            apply_light_theme(app)
            self.setStyleSheet(LIGHT_STYLE)
            self._act_theme.setText("🌙 Dark")
        else:
            # Switch back to dark
            apply_dark_theme(app)
            self.setStyleSheet(DARK_STYLE)
            self._act_theme.setText("☀️ Light")
        self.scene.invalidate()   # force canvas repaint

    # ── Influence Line dialog ─────────────────────────────────────────

    def _open_il_dialog(self, member_id: str = "", local_x: float = 0.0) -> None:
        """Open IL configuration dialog, compute, and plot the ILD."""
        if not self.project.members:
            QMessageBox.warning(self, "No members",
                                "Add at least one member before computing an ILD.")
            return
        dlg = InfluenceLineDialog(self.project,
                                   target_member_id=member_id,
                                   target_x=local_x,
                                   parent=self)
        if dlg.exec() != InfluenceLineDialog.DialogCode.Accepted:
            return
        cfg = dlg.get_config()
        if not cfg["path_member_ids"]:
            QMessageBox.warning(self, "No path", "Select at least one path member.")
            return
        try:
            il_result = self.solver.compute_influence_line(
                self.project,
                target_member_id=cfg["target_member_id"],
                target_x=cfg["target_x"],
                force_type=cfg["force_type"],
                path_member_ids=cfg["path_member_ids"],
            )
        except SolverError as e:
            QMessageBox.critical(self, "IL Failed", str(e))
            return
        self._results_panel.plot_influence_line(il_result)
        self._results_panel.setVisible(True)
        self._results_panel.show_tab("IL")
        self._set_mode(Mode.SELECT)
        self._status_lbl.setText(
            f"ILD: {cfg['force_type']} at {cfg['target_member_id']} "
            f"x={cfg['target_x']:.2f} m  │  "
            f"max={max(il_result.values, default=0):.3f}  "
            f"min={min(il_result.values, default=0):.3f}")

    def _toggle_results_panel(self) -> None:
        self._results_panel.setVisible(not self._results_panel.isVisible())

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _new_project(self) -> None:
        if QMessageBox.question(
                self, "New Project",
                "Discard current project and start fresh?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.project.clear()
            self._clear_results()

    def _save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "", "Structly Files (*.str);;JSON (*.json)")
        if path:
            self.project.save(path)
            self._status_lbl.setText(f"Saved → {path}")

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "Structly Files (*.str);;JSON (*.json)")
        if path:
            self._clear_results()
            self.project.load(path)
            self.view.fit_all()
            self._status_lbl.setText(f"Opened {path}")

    # ── Built-in Examples ────────────────────────────────────────────────────

    def _example_ssb(self) -> None:
        """Simply-supported beam with UDL — M_mid = wL²/8 = 45 kN·m."""
        self.project.clear()
        n1 = self.project.add_node(0, 0)
        n2 = self.project.add_node(6, 0)
        n1.support = SupportType.PINNED
        n2.support = SupportType.ROLLER_X
        self.project.node_changed.emit(n1)
        self.project.node_changed.emit(n2)
        m = self.project.add_member(n1.id, n2.id)
        m.dist_loads = [DistLoad(direction='Fy', w_start=-10, w_end=-10)]
        self.project.member_changed.emit(m)
        self.view.fit_all()
        self._status_lbl.setText(
            "Example: SSB 10 kN/m UDL, L=6 m  →  M_mid = 45 kN·m")

    def _example_propped(self) -> None:
        """Fixed–pinned beam with mid-span point load."""
        self.project.clear()
        n1 = self.project.add_node(0, 0)
        n2 = self.project.add_node(4, 0)
        n3 = self.project.add_node(8, 0)
        n1.support = SupportType.FIXED
        n3.support = SupportType.PINNED
        n2.loads   = [NodeLoad(Fy=-20)]
        self.project.node_changed.emit(n1)
        self.project.node_changed.emit(n2)
        self.project.node_changed.emit(n3)
        self.project.add_member(n1.id, n2.id)
        self.project.add_member(n2.id, n3.id)
        self.view.fit_all()
        self._status_lbl.setText("Example: fixed–pinned beam, 20 kN midspan (L=8 m)")

    def _example_portal(self) -> None:
        """Portal frame with lateral load at eave."""
        self.project.clear()
        n1 = self.project.add_node(0, 0)
        n2 = self.project.add_node(0, 4)
        n3 = self.project.add_node(6, 4)
        n4 = self.project.add_node(6, 0)
        n1.support = SupportType.FIXED
        n4.support = SupportType.FIXED
        n2.loads   = [NodeLoad(Fx=15)]
        self.project.node_changed.emit(n1)
        self.project.node_changed.emit(n2)
        self.project.node_changed.emit(n4)
        self.project.add_member(n1.id, n2.id)
        self.project.add_member(n2.id, n3.id)
        self.project.add_member(n4.id, n3.id)
        self.view.fit_all()
        self._status_lbl.setText("Example: portal frame, 15 kN lateral load at eave")
