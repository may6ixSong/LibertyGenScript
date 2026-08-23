"""
loading_overlay.py

창 전체를 덮는 반투명 로딩 오버레이. PyQt5는 단일 스레드라 진짜 비동기 로딩은
아니고, "무거운 작업 직전에 오버레이를 보여주고 processEvents()로 강제 렌더링한 뒤
작업을 수행 -> 끝나면 숨김" 방식으로 최소한의 로딩 표시를 제공한다.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from ui.theme import PRIMARY_COLOR, TEXT_COLOR

_SPINNER_FRAMES = ["\u25D0", "\u25D3", "\u25D1", "\u25D2"]


class LoadingOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setStyleSheet("background-color: rgba(255, 255, 255, 210);")
        self.hide()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)

        self._spinner_label = QLabel(_SPINNER_FRAMES[0])
        self._spinner_label.setAlignment(Qt.AlignCenter)
        self._spinner_label.setStyleSheet(f"font-size: 40px; color: {PRIMARY_COLOR};")
        layout.addWidget(self._spinner_label)

        self._text_label = QLabel("Loading...")
        self._text_label.setAlignment(Qt.AlignCenter)
        self._text_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_COLOR};")
        layout.addWidget(self._text_label)

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