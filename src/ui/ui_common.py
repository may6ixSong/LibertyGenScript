"""
ui_common.py

여러 화면(Step1 SetupView, Step2 UDCView 등)에서 공통으로 쓰는 작은 UI 유틸리티.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QPropertyAnimation
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QWidget,
)

from ui.theme import ERROR_COLOR, SUCCESS_COLOR, TEXT_COLOR


def build_back_button(on_back) -> QPushButton:
    """
    각 Step 화면 하단 왼쪽에 배치하는 공용 Back 버튼.
    Primary(Next/Validate/Generate) 버튼과 구분되는 별도 색상(theme.py의
    backButton QSS)을 사용함.
    """
    btn = QPushButton("Back")
    btn.setObjectName("backButton")
    if on_back is not None:
        btn.clicked.connect(lambda: on_back())
    return btn


def build_bottom_button_row(back_button: QPushButton | None, *right_buttons: QPushButton) -> QHBoxLayout:
    """
    하단 버튼 행 공통 레이아웃: Back 버튼(있으면)은 항상 왼쪽 끝, 나머지 버튼들은
    오른쪽 끝에 정렬. back_button이 None이면 Back 없이 오른쪽 버튼들만 배치.
    """
    row = QHBoxLayout()
    if back_button is not None:
        row.addWidget(back_button)
    row.addStretch()
    for btn in right_buttons:
        row.addWidget(btn)
    return row


def add_shadow(widget: QWidget) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(24)
    shadow.setXOffset(0)
    shadow.setYOffset(4)
    shadow.setColor(QColor(0, 0, 0, 40))
    widget.setGraphicsEffect(shadow)


class NoWheelComboBox(QComboBox):
    """
    마우스 휠로 스크롤해도 값이 안 바뀌는 QComboBox.
    (스크롤 영역 안에 콤보박스가 있을 때, 페이지를 스크롤하다 우연히 콤보 위를
    지나가면 선택값이 바뀌어버리는 문제 방지 - 반드시 클릭해서 골라야만 값이 바뀜)
    휠 이벤트를 무시(ignore)하면 Qt가 자동으로 부모 위젯(스크롤 영역)에 넘겨줘서
    페이지 스크롤 자체는 그대로 동작함.
    """

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        event.ignore()


class DetailsList(QListWidget):
    """읽기 전용, 선택 불가능한 결과 메시지 목록. 클릭해도 하이라이트되지 않음."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resultsList")
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(1.0)
        self._anim = None  # QPropertyAnimation 참조 유지용 (GC 방지)

    def add_message(self, message: str, status: str = "info") -> None:
        item = QListWidgetItem(message)
        color = {"error": ERROR_COLOR, "success": SUCCESS_COLOR}.get(status, TEXT_COLOR)
        item.setForeground(QColor(color))
        self.addItem(item)

    def animate_in(self) -> None:
        self._opacity.setOpacity(0.0)
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(280)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._anim = anim