"""
loading_overlay.py

창 전체를 덮는 반투명 로딩 오버레이. PyQt5는 단일 스레드라 진짜 비동기 로딩은
아니고, "무거운 작업 직전에 오버레이를 보여주고 processEvents()로 강제 렌더링한 뒤
작업을 수행 -> 끝나면 숨김" 방식으로 최소한의 로딩 표시를 제공한다.

2026-08 추가: 예전에는 배경을 거의 불투명한 흰색(rgba(255,255,255,210))으로 덮어서
뒤쪽 화면이 실제로는 가려지는데도 "덮인 느낌"이 잘 안 나 어색하다는 피드백이 있었다.
그래서 전체 배경은 어두운 반투명 스크림(rgba(15,23,42,150))으로 뒤쪽을 음영 처리하고,
스피너/텍스트는 화면 중앙의 작은 흰 카드 안에 넣어 대비를 준다.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

from ui.theme import BORDER_COLOR, CARD_COLOR, PRIMARY_COLOR, TEXT_COLOR

_SPINNER_FRAMES = ["◐", "◓", "◑", "◒"]

# 뒤쪽 화면을 음영 처리하는 어두운 반투명 스크림 색.
_SCRIM_BG = "rgba(15, 23, 42, 150)"


class LoadingOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {_SCRIM_BG};")
        self.hide()

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setStyleSheet(
            f"background-color: {CARD_COLOR}; border: 1px solid {BORDER_COLOR}; "
            f"border-radius: 14px;"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(36, 28, 36, 28)
        card_layout.setAlignment(Qt.AlignCenter)
        card_layout.setSpacing(10)

        self._spinner_label = QLabel(_SPINNER_FRAMES[0])
        self._spinner_label.setAlignment(Qt.AlignCenter)
        self._spinner_label.setStyleSheet(f"font-size: 40px; color: {PRIMARY_COLOR};")
        card_layout.addWidget(self._spinner_label)

        self._text_label = QLabel("Loading...")
        self._text_label.setAlignment(Qt.AlignCenter)
        self._text_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_COLOR};")
        card_layout.addWidget(self._text_label)

        outer.addWidget(card)

        self._frame_index = 0
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._advance_frame)

    def _advance_frame(self) -> None:
        self._frame_index = (self._frame_index + 1) % len(_SPINNER_FRAMES)
        self._spinner_label.setText(_SPINNER_FRAMES[self._frame_index])

    def show_overlay(self, text: str = "Loading...") -> None:
        self._text_label.setText(text)
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(0, 0, parent.width(), parent.height())
        self.raise_()
        self.show()
        self._timer.start()
        QApplication.processEvents()

    def hide_overlay(self) -> None:
        self._timer.stop()
        self.hide()
