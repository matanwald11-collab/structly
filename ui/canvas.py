"""
ui/canvas.py
============
Interactive QGraphicsScene/View for drawing structural models.

Coordinate conventions
-----------------------
  World : X→right, Y→up  (metres)
  Scene : X→right, Y→down (Qt default)
  Transform: scene_x =  world_x * SCALE
             scene_y = -world_y * SCALE

Changes:
  • Nodes are NOT draggable (Feature 1).
  • Right-click on a node  → Releases dialog for that node's members.
  • Right-click on a member → Releases toggle context menu.
  • NodeItem.hoverEnterEvent → rich tooltip showing support type meaning.
  • MemberItem draws point-load markers (∇ arrows) at exact x-positions.
"""
from __future__ import annotations

import math
from enum import Enum, auto
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF, pyqtSignal
from PyQt6.QtGui import (
    QColor, QPen, QBrush, QPainter, QPainterPath, QPolygonF,
    QFont, QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsItem,
    QGraphicsObject, QGraphicsLineItem, QGraphicsPathItem,
    QGraphicsEllipseItem, QMenu, QToolTip,
)

from models.project import Project
from models.node import Node, SupportType
from models.member import Member


# ── Palette ───────────────────────────────────────────────────────────────────
BG          = QColor("#0f1117")
GRID_MINOR  = QColor("#1c1e2e")
GRID_MAJOR  = QColor("#252840")
AXIS_COLOR  = QColor("#2e3155")

NODE_DEFAULT  = QColor("#7aa2f7")
NODE_PINNED   = QColor("#e0af68")
NODE_ROLLER   = QColor("#9ece6a")
NODE_FIXED    = QColor("#f7768e")
NODE_SELECTED = QColor("#ffe600")

MEMBER_COLOR     = QColor("#a9b1d6")
MEMBER_SELECTED  = QColor("#ffe600")
HINGE_COLOR      = QColor("#bb9af7")

LOAD_FORCE_COLOR  = QColor("#ff9e64")
LOAD_MOMENT_COLOR = QColor("#bb9af7")
LOAD_PT_COLOR     = QColor("#f7768e")   # point-load-on-member marker

BMD_POS = QColor(250, 100, 100, 140)
BMD_NEG = QColor(100, 150, 250, 140)
SFD_POS = QColor(100, 220, 120, 140)
SFD_NEG = QColor(220, 100, 220, 140)
AFD_POS = QColor(100, 200, 255, 140)
AFD_NEG = QColor(255, 180, 50,  140)

# ── Constants ─────────────────────────────────────────────────────────────────
SCALE        = 80.0    # pixels per metre  (initial zoom)
GRID_MINOR_M = 0.5     # grid spacing (m)
GRID_MAJOR_M = 2.0
SNAP_M       = 0.5     # snap grid (m)
NODE_R       = 9.0     # node circle radius (px)

# Rich tooltip text for each support type
_SUPPORT_TIPS: dict[SupportType, str] = {
    SupportType.FREE: (
        "<b>Free node</b><br>"
        "No restraint — all three DOFs (ΔX, ΔY, ΘZ) are free.<br>"
        "Structure will translate/rotate without additional supports."
    ),
    SupportType.PINNED: (
        "<b>Pinned support  △</b><br>"
        "Restrains: <b>ΔX, ΔY</b>&nbsp;&nbsp;Free: <b>ΘZ</b><br>"
        "Provides two reaction forces (Rx, Ry); no moment reaction.<br>"
        "Node can rotate freely."
    ),
    SupportType.ROLLER_X: (
        "<b>Roller — X free  ⊙</b><br>"
        "Restrains: <b>ΔY</b>&nbsp;&nbsp;Free: <b>ΔX, ΘZ</b><br>"
        "Slides horizontally; provides only a vertical reaction (Ry)."
    ),
    SupportType.ROLLER_Y: (
        "<b>Roller — Y free  ⊙</b><br>"
        "Restrains: <b>ΔX</b>&nbsp;&nbsp;Free: <b>ΔY, ΘZ</b><br>"
        "Slides vertically; provides only a horizontal reaction (Rx)."
    ),
    SupportType.FIXED: (
        "<b>Fixed / Encastré support  ▭</b><br>"
        "Restrains: <b>ΔX, ΔY, ΘZ</b> — all three DOFs locked.<br>"
        "Provides reactions Rx, Ry <i>and</i> a moment reaction Mz.<br>"
        "Maximum restraint — node cannot translate or rotate."
    ),
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def w2s(wx: float, wy: float, scale: float = SCALE) -> QPointF:
    """World → scene coordinates."""
    return QPointF(wx * scale, -wy * scale)


def s2w(sx: float, sy: float, scale: float = SCALE) -> tuple[float, float]:
    """Scene → world coordinates."""
    return sx / scale, -sy / scale


def snap(v: float, step: float = SNAP_M) -> float:
    return round(v / step) * step


# ─────────────────────────────────────────────────────────────────────────────
# Interaction modes
# ─────────────────────────────────────────────────────────────────────────────
class Mode(Enum):
    SELECT         = auto()
    ADD_NODE       = auto()
    ADD_MEMBER     = auto()
    DELETE         = auto()
    INFLUENCE_LINE = auto()   # click member/node to set IL target


# ─────────────────────────────────────────────────────────────────────────────
# NodeItem
# ─────────────────────────────────────────────────────────────────────────────
class NodeItem(QGraphicsObject):
    """Visual representation of a structural node.

    Feature 1: NO ItemIsMovable flag — nodes are precision-placed only.
    Feature 4: hoverEnterEvent shows a rich tooltip for the support type.
    """

    moved = pyqtSignal(str, float, float)   # kept for compatibility but never fires

    def __init__(self, node: Node, scale: float = SCALE):
        super().__init__()
        self.node   = node
        self._scale = scale
        self.setPos(w2s(node.x, node.y, scale))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges,
            # NOTE: ItemIsMovable is intentionally omitted (Feature 1)
        )
        self.setAcceptHoverEvents(True)     # needed for Feature 4
        self.setZValue(10)
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        self.setToolTip(
            f"{self.node.id}  ({self.node.x:.2f}, {self.node.y:.2f} m)"
        )

    # Feature 1: set_movable is kept for API compatibility but is a no-op
    def set_movable(self, on: bool) -> None:
        pass   # nodes are NEVER movable via canvas dragging

    def sync_from_model(self) -> None:
        """Re-position item when model coordinates changed externally."""
        self.setPos(w2s(self.node.x, self.node.y, self._scale))
        self._update_tooltip()
        self.update()

    # ── QGraphicsItem interface ──────────────────────────────────────────────
    def boundingRect(self) -> QRectF:
        pad = 4
        return QRectF(-NODE_R - pad, -NODE_R - 28, 2 * (NODE_R + pad), 2 * NODE_R + 46)

    def paint(self, painter: QPainter, option, widget) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = {
            SupportType.FREE:     NODE_DEFAULT,
            SupportType.PINNED:   NODE_PINNED,
            SupportType.ROLLER_X: NODE_ROLLER,
            SupportType.ROLLER_Y: NODE_ROLLER,
            SupportType.FIXED:    NODE_FIXED,
        }.get(self.node.support, NODE_DEFAULT)

        pen_color = NODE_SELECTED if self.isSelected() else QColor("#ffffff")
        pen_width = 2.5 if self.isSelected() else 1.5

        painter.setPen(QPen(pen_color, pen_width))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QRectF(-NODE_R, -NODE_R, 2 * NODE_R, 2 * NODE_R))

        self._draw_support(painter)
        self._draw_loads(painter)

        # Label
        painter.setPen(QPen(QColor("#c0caf5")))
        painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        painter.drawText(QRectF(-20, -NODE_R - 16, 40, 14),
                         Qt.AlignmentFlag.AlignHCenter, self.node.id)

    def _draw_support(self, painter: QPainter) -> None:
        s  = self.node.support
        r  = NODE_R
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if s == SupportType.PINNED:
            painter.setPen(QPen(NODE_PINNED, 1.5))
            painter.setBrush(QBrush(NODE_PINNED))
            pts = [QPointF(0, r), QPointF(-12, r + 18), QPointF(12, r + 18)]
            painter.drawPolygon(QPolygonF(pts))
            painter.drawLine(QLineF(-14, r + 19, 14, r + 19))
            for i in range(-12, 13, 6):
                painter.drawLine(QLineF(i, r + 19, i - 5, r + 25))

        elif s == SupportType.FIXED:
            painter.setPen(QPen(NODE_FIXED, 1.5))
            painter.setBrush(QBrush(NODE_FIXED.darker(130)))
            painter.drawRect(QRectF(-14, r, 28, 10))
            painter.setPen(QPen(NODE_FIXED, 1))
            for i in range(-12, 14, 6):
                painter.drawLine(QLineF(i, r + 10, i - 4, r + 16))

        elif s == SupportType.ROLLER_X:   # fixed Y, free X
            painter.setPen(QPen(NODE_ROLLER, 1.5))
            painter.setBrush(QBrush(NODE_ROLLER))
            pts = [QPointF(0, r), QPointF(-10, r + 14), QPointF(10, r + 14)]
            painter.drawPolygon(QPolygonF(pts))
            painter.setBrush(QBrush())
            painter.drawEllipse(QRectF(-11, r + 14, 8, 8))
            painter.drawEllipse(QRectF(3,   r + 14, 8, 8))

        elif s == SupportType.ROLLER_Y:   # fixed X, free Y
            painter.setPen(QPen(NODE_ROLLER, 1.5))
            painter.setBrush(QBrush(NODE_ROLLER))
            pts = [QPointF(-r, 0), QPointF(-r - 14, -10), QPointF(-r - 14, 10)]
            painter.drawPolygon(QPolygonF(pts))
            painter.setBrush(QBrush())
            painter.drawEllipse(QRectF(-r - 22, -11, 8, 8))
            painter.drawEllipse(QRectF(-r - 22,   3, 8, 8))

        painter.restore()

    def _draw_loads(self, painter: QPainter) -> None:
        for load in self.node.loads:
            painter.save()
            painter.setPen(QPen(LOAD_FORCE_COLOR, 2))
            painter.setBrush(QBrush(LOAD_FORCE_COLOR))
            arrow_len = 30
            if load.Fx != 0:
                sign = 1 if load.Fx > 0 else -1
                self._arrow(painter, QPointF(-sign * arrow_len, 0), QPointF(0, 0))
                painter.setPen(QPen(LOAD_FORCE_COLOR))
                painter.setFont(QFont("Consolas", 7))
                painter.drawText(QPointF(-sign * (arrow_len + 4), 0),
                                 f"{abs(load.Fx):.1f}")
            if load.Fy != 0:
                sign = 1 if load.Fy > 0 else -1
                self._arrow(painter, QPointF(0, sign * arrow_len), QPointF(0, 0))
                painter.setPen(QPen(LOAD_FORCE_COLOR))
                painter.setFont(QFont("Consolas", 7))
                painter.drawText(QPointF(4, sign * (arrow_len + 4)),
                                 f"{abs(load.Fy):.1f}")
            if load.Mz != 0:
                # Draw a curved moment arc
                painter.setPen(QPen(LOAD_MOMENT_COLOR, 2))
                painter.setBrush(QBrush())
                arc_r = 16
                sign  = 1 if load.Mz > 0 else -1
                painter.drawArc(QRectF(-arc_r, -arc_r, 2*arc_r, 2*arc_r), 0, sign*270*16)
                painter.setPen(QPen(LOAD_MOMENT_COLOR))
                painter.setFont(QFont("Consolas", 7))
                painter.drawText(QPointF(arc_r + 2, -arc_r),
                                 f"{abs(load.Mz):.1f}")
            painter.restore()

    @staticmethod
    def _arrow(painter: QPainter, frm: QPointF, to: QPointF) -> None:
        painter.drawLine(QLineF(frm, to))
        dx = to.x() - frm.x()
        dy = to.y() - frm.y()
        length = math.hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length
        w = 5
        p1 = QPointF(to.x() - ux * 10 - uy * w, to.y() - uy * 10 + ux * w)
        p2 = QPointF(to.x() - ux * 10 + uy * w, to.y() - uy * 10 - ux * w)
        painter.drawPolygon(QPolygonF([to, p1, p2]))

    # ── Feature 4: Hover tooltip ──────────────────────────────────────────────
    def hoverEnterEvent(self, event) -> None:
        tip = _SUPPORT_TIPS.get(self.node.support, "")
        if tip:
            QToolTip.showText(
                event.screenPos(), tip,
                msecShowTime=8000,
            )
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        QToolTip.hideText()
        super().hoverLeaveEvent(event)

    # No itemChange drag tracking needed (Feature 1)
    def itemChange(self, change, value):
        return super().itemChange(change, value)


# ─────────────────────────────────────────────────────────────────────────────
# MemberItem
# ─────────────────────────────────────────────────────────────────────────────
class MemberItem(QGraphicsObject):
    """Visual representation of a structural member (beam/column/truss bar).

    Hinge circles are drawn for Mz end-releases (Feature 3 visual).
    PointLoad marker (∇) drawn at exact x-position (Feature 2 visual).
    """

    HINGE_R = 5.0

    def __init__(self, member: Member,
                 start_item: NodeItem, end_item: NodeItem):
        super().__init__()
        self.member = member
        self._si = start_item
        self._ei = end_item
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(5)
        self._pos_cached: tuple[QPointF, QPointF] = (QPointF(), QPointF())
        self._update_cache()
        self.setToolTip(member.id)

    def _update_cache(self) -> None:
        self._pos_cached = (self._si.scenePos(), self._ei.scenePos())

    def update_geometry(self) -> None:
        self.prepareGeometryChange()
        self._update_cache()
        self.update()

    def _endpoints(self) -> tuple[QPointF, QPointF]:
        return self._pos_cached

    def boundingRect(self) -> QRectF:
        p1, p2 = self._endpoints()
        x = min(p1.x(), p2.x()) - 30
        y = min(p1.y(), p2.y()) - 30
        w = abs(p2.x() - p1.x()) + 60
        h = abs(p2.y() - p1.y()) + 60
        return QRectF(x, y, w, h)

    def shape(self) -> QPainterPath:
        """Hit-test area — thick band along member axis."""
        p1, p2 = self._endpoints()
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy) or 1
        nx, ny = -dy / length * 8, dx / length * 8
        poly = QPolygonF([
            QPointF(p1.x() + nx, p1.y() + ny),
            QPointF(p2.x() + nx, p2.y() + ny),
            QPointF(p2.x() - nx, p2.y() - ny),
            QPointF(p1.x() - nx, p1.y() - ny),
        ])
        path2 = QPainterPath()
        path2.addPolygon(poly)
        return path2

    def paint(self, painter: QPainter, option, widget) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        p1, p2 = self._endpoints()

        color  = MEMBER_SELECTED if self.isSelected() else MEMBER_COLOR
        width  = 3.0 if self.isSelected() else 2.0
        painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(QLineF(p1, p2))

        # ── End-release hinge circles  (Feature 3) ────────────────────────────
        self._draw_releases(painter, p1, p2)

        # ── UDL arrows ────────────────────────────────────────────────────────
        if self.member.dist_loads:
            self._draw_udl(painter, p1, p2)

        # ── Point load markers (Feature 2) ────────────────────────────────────
        if self.member.pt_loads:
            self._draw_pt_loads(painter, p1, p2)

        # ── Member label at midpoint ───────────────────────────────────────────
        mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        painter.setPen(QPen(QColor("#565f89")))
        painter.setFont(QFont("Consolas", 7))
        painter.drawText(mid + QPointF(3, -4), self.member.id)

    # ── End-release symbols ────────────────────────────────────────────────────
    def _draw_releases(self, painter: QPainter, p1: QPointF, p2: QPointF) -> None:
        """Draw engineering-standard symbols for Mz / Fy / Fx end releases."""
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length   # unit along member
        nx, ny = -uy, ux                    # unit normal (left of member)

        r = self.HINGE_R

        # ── Mz release: hollow circle (hinge) ─────────────────────────────
        painter.setBrush(QBrush(BG))
        painter.setPen(QPen(HINGE_COLOR, 1.8))
        if self.member.releases_start.Mz:
            cx = p1.x() + ux * (r + 2)
            cy = p1.y() + uy * (r + 2)
            painter.drawEllipse(QPointF(cx, cy), r, r)

        if self.member.releases_end.Mz:
            cx = p2.x() - ux * (r + 2)
            cy = p2.y() - uy * (r + 2)
            painter.drawEllipse(QPointF(cx, cy), r, r)

        # ── Fy release: shear-slider symbol ───────────────────────────────
        # Two perpendicular tick-marks separated by a gap along the member.
        # Looks like: ─┤├─  (slot allows transverse slide)
        painter.setBrush(QBrush())
        fy_off = r + 10   # inset from node
        fy_hw  = 7        # half-width of tick perpendicular to member
        fy_gap = 3        # half-gap along member

        def _fy_symbol(base: QPointF, direction: int) -> None:
            # direction: +1 from start (inset inward), -1 from end
            cx = base.x() + direction * ux * fy_off
            cy = base.y() + direction * uy * fy_off
            # Two parallel ticks
            for sign in (-1, +1):
                ox = cx + sign * direction * ux * fy_gap
                oy = cy + sign * direction * uy * fy_gap
                painter.drawLine(QLineF(
                    ox + nx * fy_hw, oy + ny * fy_hw,
                    ox - nx * fy_hw, oy - ny * fy_hw))
            # Connecting spine along member between ticks
            painter.setPen(QPen(HINGE_COLOR, 1.0, Qt.PenStyle.DotLine))
            painter.drawLine(QLineF(
                cx - direction * ux * fy_gap, cy - direction * uy * fy_gap,
                cx + direction * ux * fy_gap, cy + direction * uy * fy_gap))
            painter.setPen(QPen(HINGE_COLOR, 1.8))

        painter.setPen(QPen(HINGE_COLOR, 1.8))
        if self.member.releases_start.Fy:
            _fy_symbol(p1, +1)
        if self.member.releases_end.Fy:
            _fy_symbol(p2, -1)

        # ── Fx release: axial-sleeve symbol ───────────────────────────────
        # Two short perpendicular bars (⊥ to member) with a gap between them.
        # Looks like: ─|  |─  (sleeve allows axial slide)
        fx_off = r + 10
        fx_hw  = 6
        fx_gap = 4

        def _fx_symbol(base: QPointF, direction: int) -> None:
            cx = base.x() + direction * ux * fx_off
            cy = base.y() + direction * uy * fx_off
            for sign in (-1, +1):
                ox = cx + sign * direction * ux * fx_gap
                oy = cy + sign * direction * uy * fx_gap
                painter.drawLine(QLineF(
                    ox + nx * fx_hw, oy + ny * fx_hw,
                    ox - nx * fx_hw, oy - ny * fx_hw))
            # diagonal X mark between the bars to indicate axial freedom
            painter.setPen(QPen(HINGE_COLOR, 0.8))
            painter.drawLine(QLineF(
                cx - direction * ux * fx_gap + nx * fx_hw * 0.6,
                cy - direction * uy * fx_gap + ny * fx_hw * 0.6,
                cx + direction * ux * fx_gap - nx * fx_hw * 0.6,
                cy + direction * uy * fx_gap - ny * fx_hw * 0.6))
            painter.setPen(QPen(HINGE_COLOR, 1.8))

        painter.setPen(QPen(HINGE_COLOR, 1.8))
        if self.member.releases_start.Fx:
            _fx_symbol(p1, +1)
        if self.member.releases_end.Fx:
            _fx_symbol(p2, -1)

    # ── UDL arrows ────────────────────────────────────────────────────────────
    def _draw_udl(self, painter: QPainter, p1: QPointF, p2: QPointF) -> None:
        """Draw small tick-arrows indicating a distributed load.

        Arrow direction follows the load sign:
          w < 0  (downward gravity) → tails above member, arrows point ↓
          w >= 0 (upward or axial)  → tails below member, arrows point ↑
        """
        if not self.member.dist_loads:
            return
        painter.save()
        painter.setPen(QPen(LOAD_FORCE_COLOR, 1.2))
        painter.setBrush(QBrush(LOAD_FORCE_COLOR))
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy) or 1

        w = self.member.dist_loads[0].w_start
        load_sign = 1 if w >= 0 else -1

        arrow_len = 20
        nx = -dy / length * arrow_len * load_sign
        ny =  dx / length * arrow_len * load_sign

        steps = 5
        for i in range(steps + 1):
            t = i / steps
            ox = p1.x() + dx * t
            oy = p1.y() + dy * t
            frm = QPointF(ox + nx, oy + ny)
            to  = QPointF(ox, oy)
            painter.drawLine(QLineF(frm, to))
            adx = to.x() - frm.x()
            ady = to.y() - frm.y()
            al = math.hypot(adx, ady) or 1
            ux, uy = adx / al, ady / al
            ah = 6
            q1 = QPointF(to.x() - ux*ah - uy*3, to.y() - uy*ah + ux*3)
            q2 = QPointF(to.x() - ux*ah + uy*3, to.y() - uy*ah - ux*3)
            painter.drawPolygon(QPolygonF([to, q1, q2]))

        frm_bar = QPointF(p1.x() + nx, p1.y() + ny)
        to_bar  = QPointF(p2.x() + nx, p2.y() + ny)
        painter.drawLine(QLineF(frm_bar, to_bar))
        painter.restore()

    # ── Feature 2: Point load markers ─────────────────────────────────────────
    def _draw_pt_loads(self, painter: QPainter, p1: QPointF, p2: QPointF) -> None:
        """Draw a ∇ marker (downward triangle + stem) at each pt_load position."""
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length_px = math.hypot(dx, dy) or 1
        ux, uy = dx / length_px, dy / length_px    # unit along member
        # Normal: perpendicular, "upward in world" = flip scene-Y convention
        nx_up = -uy   # pointing "left-of" member direction (upward for horiz)
        ny_up =  ux

        for pl in self.member.pt_loads:
            # Compute member length in world coords using the cached NodeItem refs
            ni = self._si
            nj = self._ei
            world_length = math.hypot(
                nj.node.x - ni.node.x, nj.node.y - ni.node.y)
            if world_length == 0:
                continue
            t = pl.x / world_length    # fraction along member (0..1)
            t = max(0.0, min(1.0, t))

            px = p1.x() + dx * t
            py = p1.y() + dy * t

            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            sign = -1 if pl.magnitude < 0 else 1
            # For Fy: negative → from above; positive → from below
            stem_len = 24
            if pl.direction in ("Fy", "FY"):
                # Perpendicular to member
                sfx = nx_up * stem_len * sign
                sfy = ny_up * stem_len * sign
            elif pl.direction in ("Fx", "FX"):
                # Along member
                sfx = ux * stem_len * sign
                sfy = uy * stem_len * sign
            else:
                sfx = nx_up * stem_len
                sfy = ny_up * stem_len

            tip  = QPointF(px, py)
            tail = QPointF(px + sfx, py + sfy)

            painter.setPen(QPen(LOAD_PT_COLOR, 2))
            painter.setBrush(QBrush(LOAD_PT_COLOR))
            painter.drawLine(QLineF(tail, tip))

            # Arrowhead at tip
            adx = tip.x() - tail.x()
            ady = tip.y() - tail.y()
            al = math.hypot(adx, ady) or 1
            au, av = adx / al, ady / al
            ah = 7
            q1 = QPointF(tip.x() - au*ah - av*4, tip.y() - av*ah + au*4)
            q2 = QPointF(tip.x() - au*ah + av*4, tip.y() - av*ah - au*4)
            painter.drawPolygon(QPolygonF([tip, q1, q2]))

            # Label: magnitude + direction
            painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
            painter.setPen(QPen(LOAD_PT_COLOR))
            lbl = f"{abs(pl.magnitude):.1f} kN"
            painter.drawText(tail + QPointF(4, -3), lbl)

            painter.restore()


# ─────────────────────────────────────────────────────────────────────────────
# Releases context-menu dialog (Feature 3)
# ─────────────────────────────────────────────────────────────────────────────

class _ReleasesMenu:
    """Right-click context menu to toggle end releases on a Member."""

    @staticmethod
    def show(member: Member, project, parent_widget, screen_pos) -> None:
        menu = QMenu(parent_widget)
        menu.setStyleSheet(
            "QMenu { background:#1a1b26; color:#c0caf5; border:1px solid #2a2d4a; }"
            "QMenu::item:selected { background:#364a82; }"
        )
        menu.setTitle(f"Releases — {member.id}")
        menu.addAction(f"Member: {member.id}  "
                       f"({member.start_node_id} → {member.end_node_id})"
                       ).setEnabled(False)
        menu.addSeparator()

        def _toggle(flag: str, end: str):
            """Toggle the given release flag ('Fx','Fy','Mz') at 'start'/'end'."""
            rel = member.releases_start if end == "start" else member.releases_end
            cur = getattr(rel, flag)
            setattr(rel, flag, not cur)
            project.member_changed.emit(member)

        def _chk(flag: str, end: str) -> str:
            rel = member.releases_start if end == "start" else member.releases_end
            return "✓ " if getattr(rel, flag) else "    "

        for end, lbl in [("start", f"i-end  ({member.start_node_id})"),
                         ("end",   f"j-end  ({member.end_node_id})")]:
            menu.addAction(lbl).setEnabled(False)
            for flag, desc in [("Mz", "Mz — moment (hinge)"),
                                ("Fy", "Fy — shear slider"),
                                ("Fx", "Fx — axial release")]:
                act = menu.addAction(f"  {_chk(flag, end)}{desc}")
                # Closure capture
                act.triggered.connect(
                    (lambda f=flag, e=end: lambda: _toggle(f, e))()
                )
            menu.addSeparator()

        menu.exec(screen_pos)


# ─────────────────────────────────────────────────────────────────────────────
# StructureScene
# ─────────────────────────────────────────────────────────────────────────────
class StructureScene(QGraphicsScene):
    """Interactive scene that owns NodeItems and MemberItems."""

    status_update      = pyqtSignal(str)
    item_selected      = pyqtSignal(object)   # Node | Member | None
    mode_changed       = pyqtSignal(str)
    cursor_moved       = pyqtSignal(float, float)  # world_x, world_y (snapped)
    il_target_selected = pyqtSignal(str, float)    # member_id, local_x (for IL mode)

    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        self._scale  = SCALE
        self._mode   = Mode.SELECT
        self._theme  = "dark"           # 'dark' | 'light'
        self._diag_user_scale: float = 1.0   # user-controlled multiplier

        self._node_items:   Dict[str, NodeItem]   = {}
        self._member_items: Dict[str, MemberItem] = {}

        self._pending_start_id: Optional[str]             = None
        self._temp_line:        Optional[QGraphicsLineItem] = None

        # Result overlay items (filled polygons)
        self._result_items: list = []
        self._results = None
        self._result_type: str = "none"   # "bmd" | "sfd" | "afd" | "none"

        self.setSceneRect(-4000, -4000, 8000, 8000)

        # Connect project signals
        project.node_added.connect(self._on_node_added)
        project.node_removed.connect(self._on_node_removed)
        project.node_changed.connect(self._on_node_changed)
        project.member_added.connect(self._on_member_added)
        project.member_removed.connect(self._on_member_removed)
        project.member_changed.connect(self._on_member_changed)
        project.project_reset.connect(self._on_project_reset)

        # Selection change → emit item_selected
        self.selectionChanged.connect(self._on_selection_changed)

    # ── Mode ──────────────────────────────────────────────────────────────────
    @property
    def mode(self) -> Mode:
        return self._mode

    def set_mode(self, mode: Mode) -> None:
        self._cancel_member_operation()
        self._mode = mode
        cursor = {
            Mode.SELECT:         Qt.CursorShape.ArrowCursor,
            Mode.ADD_NODE:       Qt.CursorShape.CrossCursor,
            Mode.ADD_MEMBER:     Qt.CursorShape.CrossCursor,
            Mode.DELETE:         Qt.CursorShape.ForbiddenCursor,
            Mode.INFLUENCE_LINE: Qt.CursorShape.PointingHandCursor,
        }.get(mode, Qt.CursorShape.ArrowCursor)
        for view in self.views():
            view.setCursor(cursor)
        self.mode_changed.emit(mode.name)
        self.status_update.emit({
            Mode.SELECT:         "Click to select.  Right-click member → releases",
            Mode.ADD_NODE:       "Click grid to place node  (snaps to 0.5 m grid)",
            Mode.ADD_MEMBER:     "Click start node, then end node",
            Mode.DELETE:         "Click item to delete",
            Mode.INFLUENCE_LINE: "Click a member to set the Influence Line target point",
        }.get(mode, ""))

    # ── Project signal handlers ───────────────────────────────────────────────
    def _on_node_added(self, node: Node) -> None:
        item = NodeItem(node, self._scale)
        item.moved.connect(self._on_node_moved)
        self._node_items[node.id] = item
        self.addItem(item)
        # Feature 1: do NOT call set_movable(True)

    def _on_node_removed(self, node_id: str) -> None:
        item = self._node_items.pop(node_id, None)
        if item:
            self.removeItem(item)

    def _on_node_changed(self, node: Node) -> None:
        item = self._node_items.get(node.id)
        if item:
            item.node = node
            item.sync_from_model()
            for mi in self._member_items.values():
                if mi.member.start_node_id == node.id or mi.member.end_node_id == node.id:
                    mi.update_geometry()

    def _on_member_added(self, member: Member) -> None:
        si = self._node_items.get(member.start_node_id)
        ei = self._node_items.get(member.end_node_id)
        if si and ei:
            item = MemberItem(member, si, ei)
            self._member_items[member.id] = item
            self.addItem(item)

    def _on_member_removed(self, member_id: str) -> None:
        item = self._member_items.pop(member_id, None)
        if item:
            self.removeItem(item)

    def _on_member_changed(self, member: Member) -> None:
        item = self._member_items.get(member.id)
        if item:
            item.member = member
            item.update()

    def _on_project_reset(self) -> None:
        self.clear_all_items()

    def _on_node_moved(self, node_id: str, wx: float, wy: float) -> None:
        # Feature 1: this signal is kept but should never fire
        node = self.project.nodes.get(node_id)
        if node:
            node.x, node.y = wx, wy
        for mi in self._member_items.values():
            if mi.member.start_node_id == node_id or mi.member.end_node_id == node_id:
                mi.update_geometry()

    def clear_all_items(self) -> None:
        for item in list(self._node_items.values()):
            self.removeItem(item)
        for item in list(self._member_items.values()):
            self.removeItem(item)
        self._node_items.clear()
        self._member_items.clear()
        self.clear_results()

    # ── Mouse events ─────────────────────────────────────────────────────────
    def mousePressEvent(self, event) -> None:
        pos = event.scenePos()
        wx, wy = s2w(pos.x(), pos.y(), self._scale)

        if event.button() == Qt.MouseButton.LeftButton:
            if self._mode == Mode.ADD_NODE:
                sx, sy = snap(wx), snap(wy)
                self.project.add_node(sx, sy)
                return

            elif self._mode == Mode.ADD_MEMBER:
                ni = self._node_item_at(pos)
                if ni:
                    if self._pending_start_id is None:
                        self._pending_start_id = ni.node.id
                        self._temp_line = self.addLine(
                            QLineF(ni.scenePos(), ni.scenePos()),
                            QPen(QColor("#64b5f6"), 1.5, Qt.PenStyle.DashLine),
                        )
                        self._temp_line.setZValue(1)
                        self.status_update.emit(
                            f"Start: {ni.node.id} — click end node")
                    else:
                        if ni.node.id != self._pending_start_id:
                            self.project.add_member(
                                self._pending_start_id, ni.node.id)
                        self._cancel_member_operation()
                return

            elif self._mode == Mode.DELETE:
                item = self._any_item_at(pos)
                if isinstance(item, NodeItem):
                    self.project.delete_node(item.node.id)
                elif isinstance(item, MemberItem):
                    self.project.delete_member(item.member.id)
                return

            elif self._mode == Mode.INFLUENCE_LINE:
                # Clicking on a member: compute x from click position
                mi = self._member_item_at(pos)
                if mi:
                    p1 = mi._si.scenePos()
                    p2 = mi._ei.scenePos()
                    dx = p2.x() - p1.x()
                    dy = p2.y() - p1.y()
                    length_px = math.hypot(dx, dy) or 1
                    # Project click onto member axis
                    vec_x = pos.x() - p1.x()
                    vec_y = pos.y() - p1.y()
                    t = max(0.0, min(1.0, (vec_x * dx + vec_y * dy) / (length_px ** 2)))
                    world_len = math.hypot(
                        mi._ei.node.x - mi._si.node.x,
                        mi._ei.node.y - mi._si.node.y)
                    local_x = t * world_len
                    self.il_target_selected.emit(mi.member.id, local_x)
                return

        elif event.button() == Qt.MouseButton.RightButton:
            # Feature 3: right-click context menus
            if self._mode == Mode.ADD_MEMBER:
                self._cancel_member_operation()
                return
            self._show_context_menu(pos, event)
            return

        super().mousePressEvent(event)

    def _show_context_menu(self, scene_pos: QPointF, event) -> None:
        """Right-click: show releases menu for members, support menu for nodes."""
        item = self._any_item_at(scene_pos)

        # Get the QGraphicsView to convert to screen coords
        views = self.views()
        screen_pos = event.screenPos() if views else scene_pos.toPoint()

        if isinstance(item, MemberItem):
            _ReleasesMenu.show(item.member, self.project,
                               views[0] if views else None,
                               screen_pos)
        elif isinstance(item, NodeItem):
            # Node right-click: quick support-type picker
            menu = QMenu(views[0] if views else None)
            menu.setStyleSheet(
                "QMenu { background:#1a1b26; color:#c0caf5; border:1px solid #2a2d4a; }"
                "QMenu::item:selected { background:#364a82; }"
            )
            menu.addAction(f"Support — {item.node.id}").setEnabled(False)
            menu.addSeparator()
            for st in SupportType:
                act = menu.addAction(
                    ("✓ " if item.node.support == st else "    ") + st.value)
                act.triggered.connect(
                    (lambda s=st, n=item.node: lambda: self._set_support(n, s))()
                )
            menu.exec(screen_pos)

    def _set_support(self, node: Node, support: SupportType) -> None:
        node.support = support
        self.project.node_changed.emit(node)

    def mouseMoveEvent(self, event) -> None:
        pos = event.scenePos()
        wx, wy = s2w(pos.x(), pos.y(), self._scale)
        sx, sy = snap(wx), snap(wy)
        self.cursor_moved.emit(sx, sy)
        if self._temp_line and self._pending_start_id:
            si = self._node_items.get(self._pending_start_id)
            if si:
                self._temp_line.setLine(QLineF(si.scenePos(), pos))
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_member_operation()
        elif event.key() == Qt.Key.Key_Delete:
            for item in self.selectedItems():
                if isinstance(item, NodeItem):
                    self.project.delete_node(item.node.id)
                elif isinstance(item, MemberItem):
                    self.project.delete_member(item.member.id)
        super().keyPressEvent(event)

    # ── Selection ─────────────────────────────────────────────────────────────
    def _on_selection_changed(self) -> None:
        items = self.selectedItems()
        if not items:
            self.item_selected.emit(None)
            return
        item = items[0]
        if isinstance(item, NodeItem):
            self.item_selected.emit(item.node)
        elif isinstance(item, MemberItem):
            self.item_selected.emit(item.member)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _node_item_at(self, pos: QPointF) -> Optional[NodeItem]:
        for it in self.items(pos):
            if isinstance(it, NodeItem):
                return it
        return None

    def _any_item_at(self, pos: QPointF):
        for it in self.items(pos):
            if isinstance(it, (NodeItem, MemberItem)):
                return it
        return None

    def _member_item_at(self, pos: QPointF) -> Optional[MemberItem]:
        for it in self.items(pos):
            if isinstance(it, MemberItem):
                return it
        return None

    def _cancel_member_operation(self) -> None:
        if self._temp_line:
            self.removeItem(self._temp_line)
            self._temp_line = None
        self._pending_start_id = None
        self.clearSelection()

    # ── Reaction overlay ──────────────────────────────────────────────────────
    def show_reactions(self, results) -> None:
        """Draw Rx / Ry / Mz reaction arrows at every supported node."""
        COL_RY = QColor("#9ece6a")   # green  — vertical
        COL_RX = QColor("#7aa2f7")   # blue   — horizontal
        COL_MZ = QColor("#bb9af7")   # purple — moment
        ARROW  = 38                   # arrow length px
        AH     = 9                    # arrowhead half-width
        FONT   = QFont("Consolas", 7, QFont.Weight.Bold)

        def _arrow_path(frm: QPointF, to: QPointF) -> QPainterPath:
            dx = to.x() - frm.x(); dy = to.y() - frm.y()
            L  = math.hypot(dx, dy) or 1
            ux, uy = dx / L, dy / L
            p1 = QPointF(to.x() - ux*AH*1.4 - uy*AH*0.5,
                         to.y() - uy*AH*1.4 + ux*AH*0.5)
            p2 = QPointF(to.x() - ux*AH*1.4 + uy*AH*0.5,
                         to.y() - uy*AH*1.4 - ux*AH*0.5)
            path = QPainterPath()
            path.moveTo(frm); path.lineTo(to)
            path.moveTo(to);  path.lineTo(p1)
            path.moveTo(to);  path.lineTo(p2)
            return path

        for nid, nr in results.nodes.items():
            node = self.project.nodes.get(nid)
            if not node or node.support.name == "FREE":
                continue
            ni = self._node_items.get(nid)
            if not ni:
                continue
            sp = ni.scenePos()
            offset = 0  # label stacking offset

            # Ry — vertical reaction (positive = upward in world = down arrow tip)
            if abs(nr.rxn_fy) > 1e-4:
                sign = 1 if nr.rxn_fy > 0 else -1
                frm  = QPointF(sp.x(), sp.y() + sign * ARROW)
                to_  = QPointF(sp.x(), sp.y())
                path = _arrow_path(frm, to_)
                pi   = self.addPath(path, QPen(COL_RY, 2.0), QBrush())
                pi.setZValue(15); self._result_items.append(pi)
                lbl = self.addSimpleText(f"Ry={nr.rxn_fy:.2f} kN", FONT)
                lbl.setBrush(QBrush(COL_RY))
                lbl.setPos(sp.x() + 8, sp.y() + sign * (ARROW // 2) - 6 + offset)
                lbl.setZValue(15); self._result_items.append(lbl)
                offset += 14

            # Rx — horizontal reaction
            if abs(nr.rxn_fx) > 1e-4:
                sign = 1 if nr.rxn_fx > 0 else -1
                frm  = QPointF(sp.x() - sign * ARROW, sp.y())
                to_  = QPointF(sp.x(), sp.y())
                path = _arrow_path(frm, to_)
                pi   = self.addPath(path, QPen(COL_RX, 2.0), QBrush())
                pi.setZValue(15); self._result_items.append(pi)
                lbl = self.addSimpleText(f"Rx={nr.rxn_fx:.2f} kN", FONT)
                lbl.setBrush(QBrush(COL_RX))
                lbl.setPos(sp.x() - sign * ARROW, sp.y() - 16 + offset)
                lbl.setZValue(15); self._result_items.append(lbl)
                offset += 14

            # Mz — moment reaction (arc label only; no arrow)
            if abs(nr.rxn_mz) > 1e-4:
                lbl = self.addSimpleText(f"Mz={nr.rxn_mz:.2f} kN·m", FONT)
                lbl.setBrush(QBrush(COL_MZ))
                lbl.setPos(sp.x() + 8, sp.y() + 20 + offset)
                lbl.setZValue(15); self._result_items.append(lbl)

    # ── Grid background ──────────────────────────────────────────────────────
    def drawBackground(self, painter: QPainter, rect) -> None:
        painter.fillRect(rect, BG)
        minor = GRID_MINOR_M * self._scale
        major = GRID_MAJOR_M * self._scale

        # Minor grid
        painter.setPen(QPen(GRID_MINOR, 0.5))
        lx = math.floor(rect.left()  / minor) * minor
        ly = math.floor(rect.top()   / minor) * minor
        x = lx
        while x <= rect.right():
            painter.drawLine(QLineF(x, rect.top(), x, rect.bottom()))
            x += minor
        y = ly
        while y <= rect.bottom():
            painter.drawLine(QLineF(rect.left(), y, rect.right(), y))
            y += minor

        # Major grid
        painter.setPen(QPen(GRID_MAJOR, 1.0))
        lx = math.floor(rect.left()  / major) * major
        ly = math.floor(rect.top()   / major) * major
        x = lx
        while x <= rect.right():
            painter.drawLine(QLineF(x, rect.top(), x, rect.bottom()))
            x += major
        y = ly
        while y <= rect.bottom():
            painter.drawLine(QLineF(rect.left(), y, rect.right(), y))
            y += major

        # Axes
        painter.setPen(QPen(AXIS_COLOR, 1.5))
        painter.drawLine(QLineF(rect.left(), 0, rect.right(), 0))
        painter.drawLine(QLineF(0, rect.top(), 0, rect.bottom()))

    # ── Result overlays ───────────────────────────────────────────────────────
    def show_results(self, results, diagram_type: str = "bmd") -> None:
        """Draw BMD/SFD/AFD polygons over the members."""
        self._results     = results
        self._result_type = diagram_type
        self.clear_results()

        scale_factor = self._diagram_scale(results, diagram_type)
        if scale_factor == 0:
            return

        colours = {
            "bmd": (BMD_POS, BMD_NEG),
            "sfd": (SFD_POS, SFD_NEG),
            "afd": (AFD_POS, AFD_NEG),
        }
        col_pos, col_neg = colours.get(diagram_type, (BMD_POS, BMD_NEG))

        for mid, mr in results.members.items():
            ni = self._node_items.get(self.project.members[mid].start_node_id)
            nj = self._node_items.get(self.project.members[mid].end_node_id)
            if not ni or not nj:
                continue

            pi = ni.scenePos()
            pj = nj.scenePos()
            dx = pj.x() - pi.x()
            dy = pj.y() - pi.y()
            length_px = math.hypot(dx, dy) or 1

            ux, uy = dx / length_px, dy / length_px
            nx, ny = -uy, ux

            values = {
                "bmd": mr.bmd,
                "sfd": mr.sfd,
                "afd": mr.afd,
            }.get(diagram_type, mr.bmd)

            n = len(mr.positions)
            for polarity in (+1, -1):
                pts_top: list[QPointF] = []
                pts_bot: list[QPointF] = []
                for i in range(n):
                    t   = mr.positions[i] / mr.length
                    val = values[i]
                    if polarity == +1 and val < 0:
                        continue
                    if polarity == -1 and val >= 0:
                        continue
                    px = pi.x() + dx * t
                    py = pi.y() + dy * t
                    offset = val * scale_factor
                    ox = nx * (-offset)
                    oy = ny * (-offset)
                    pts_top.append(QPointF(px + ox, py + oy))
                    pts_bot.append(QPointF(px, py))

                if len(pts_top) < 2:
                    continue

                poly_pts = pts_top + list(reversed(pts_bot))
                poly = QPolygonF(poly_pts)
                path = QPainterPath()
                path.addPolygon(poly)

                fill = col_pos if polarity == +1 else col_neg
                item = self.addPath(path,
                                    QPen(fill.lighter(150), 0.8),
                                    QBrush(fill))
                item.setZValue(3)
                self._result_items.append(item)

    def _diagram_scale(self, results, dtype: str) -> float:
        mx = {
            "bmd": results.max_moment(),
            "sfd": results.max_shear(),
            "afd": results.max_axial(),
        }.get(dtype, 1.0)
        if mx == 0:
            return 0.0
        return (60.0 / mx) * self._diag_user_scale

    def set_diagram_scale(self, factor: float) -> None:
        """Called by the toolbar spinbox; redraws the active diagram overlay."""
        self._diag_user_scale = max(0.1, factor)
        if self._results and self._result_type != "none":
            self.show_results(self._results, self._result_type)

    def clear_results(self) -> None:
        for item in self._result_items:
            self.removeItem(item)
        self._result_items.clear()
        self._results     = None
        self._result_type = "none"


# ─────────────────────────────────────────────────────────────────────────────
# StructureView
# ─────────────────────────────────────────────────────────────────────────────
class StructureView(QGraphicsView):
    """QGraphicsView with zoom (wheel) and pan (middle-button / Space+drag)."""

    def __init__(self, scene: StructureScene):
        super().__init__(scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform,
        )
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameStyle(0)
        self.setStyleSheet("background: transparent; border: none;")
        self._panning   = False
        self._pan_start = QPointF()
        self.setSceneRect(-4000, -4000, 8000, 8000)
        self.centerOn(0, 0)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning   = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space and not self._panning:
            self._panning   = True
            self._pan_start = QPointF()
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._panning = False
            self.unsetCursor()
        super().keyReleaseEvent(event)

    def fit_all(self) -> None:
        """Zoom to fit all items."""
        if self.scene() and self.scene().items():
            self.fitInView(self.scene().itemsBoundingRect().adjusted(-50, -50, 50, 50),
                           Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self.resetTransform()
            self.centerOn(0, 0)
