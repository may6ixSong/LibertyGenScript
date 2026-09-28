"""
ui_common.py

여러 화면(Step1 SetupView, Step2 UDCView 등)에서 공통으로 쓰는 작은 UI 유틸리티.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QPropertyAnimation, QTimer
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QToolTip, QWidget,
)

import config_transfer
from ui.theme import ERROR_COLOR, MUTED_TEXT_COLOR, SUCCESS_COLOR, TEXT_COLOR


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


def build_bottom_button_row(
    back_button: QPushButton | None,
    *right_buttons: QPushButton,
    extra_left_buttons: tuple[QPushButton, ...] = (),
) -> QHBoxLayout:
    """
    하단 버튼 행 공통 레이아웃: Back 버튼(있으면)은 항상 왼쪽 끝, extra_left_buttons가
    있으면 그 옆에 이어서 배치(예: Export Config), 나머지 버튼들은 오른쪽 끝에 정렬.
    back_button이 None이면 Back 없이 배치.
    """
    row = QHBoxLayout()
    if back_button is not None:
        row.addWidget(back_button)
    for btn in extra_left_buttons:
        row.addWidget(btn)
    row.addStretch()
    for btn in right_buttons:
        row.addWidget(btn)
    return row


# ---------------------------------------------------------------------------
# Config export/import (2026-08 추가) - 어느 Step에서든 현재 config(3개 json 파일)를
# 파일 하나로 export할 수 있고, Step1에서 그 파일을 import할 수 있다. 실제 읽기/쓰기
# 로직은 config_transfer.py(Qt 비의존)에 있고, 여기서는 파일 대화상자 + 결과 알림만
# 담당한다.
# ---------------------------------------------------------------------------
def run_export_config_dialog(parent: QWidget, start_dir_hint: str = "") -> None:
    default_name = config_transfer.DEFAULT_EXPORT_BASENAME + config_transfer.EXPORT_FILE_EXTENSION
    initial_path = str(Path(start_dir_hint) / default_name) if start_dir_hint else default_name

    path, _ = QFileDialog.getSaveFileName(
        parent, "Export Config", initial_path,
        f"Config Files (*{config_transfer.EXPORT_FILE_EXTENSION})",
        options=QFileDialog.DontUseNativeDialog,
    )
    if not path:
        return
    if not path.lower().endswith(config_transfer.EXPORT_FILE_EXTENSION):
        path += config_transfer.EXPORT_FILE_EXTENSION

    try:
        config_transfer.export_config(path)
    except OSError as e:
        QMessageBox.critical(parent, "Export Failed", f"Could not write config file:\n{e}")
        return
    QMessageBox.information(parent, "Export Complete", f"Config exported to:\n{path}")


def run_import_config_dialog(parent: QWidget) -> bool:
    """
    config 파일을 불러와 3개 config 파일(user_config/udc_settings/step3_settings)을
    전부 덮어쓴다. 성공하면 True를 반환하지만, 불러온 경로가 실제로 유효한지는 여기서
    검사하지 않는다 - 예전처럼 각 Step의 Validate를 다시 통과해야 한다.
    """
    path, _ = QFileDialog.getOpenFileName(
        parent, "Import Config", "",
        f"Config Files (*{config_transfer.EXPORT_FILE_EXTENSION});;All Files (*)",
        options=QFileDialog.DontUseNativeDialog,
    )
    if not path:
        return False

    try:
        config_transfer.import_config(path)
    except (OSError, ValueError) as e:
        QMessageBox.critical(parent, "Import Failed", f"Could not read config file:\n{e}")
        return False

    QMessageBox.information(
        parent, "Import Complete",
        "Config imported. Files/folders referenced by the config may have changed or moved, "
        "so run Validate again on each step to confirm they are still valid.",
    )
    return True


class InfoIcon(QLabel):
    """
    작은 원형 "i" 아이콘. 마우스를 올리면 설명이 툴팁으로 뜬다 (2026-08 레이아웃 개편).

    예전에는 화면마다 설명 문단(hint/note)을 그대로 깔아두느라 세로 공간을 크게
    차지해서, Step3의 "1) Check DBS Output Pins" 버튼처럼 정작 먼저 눌러야 하는 요소가
    스크롤을 내려야만 보였다. 그래서 설명은 전부 이 아이콘의 툴팁으로 옮기고 화면에는
    입력 요소만 남긴다.
    """

    _SIZE = 16

    def __init__(self, text: str, parent=None):
        super().__init__("i", parent)
        self.setObjectName("infoIcon")
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setAlignment(Qt.AlignCenter)
        self.setToolTip(text)
        self.setCursor(Qt.WhatsThisCursor)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        # 툴팁 기본 지연(약 700ms) 없이 hover 즉시 뜨도록 직접 띄운다.
        QToolTip.showText(self.mapToGlobal(self.rect().bottomLeft()), self.toolTip(), self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        QToolTip.hideText()
        super().leaveEvent(event)


def build_section_header(title: str, info_text: str = "", object_name: str = "sectionLabel") -> QWidget:
    """
    섹션 제목 + (설명이 있으면) 오른쪽에 hover 정보 아이콘 하나를 붙인 한 줄.
    설명 문단을 화면에 깔지 않고 아이콘 툴팁으로 접어두기 위한 공용 헬퍼.
    """
    container = QWidget()
    container.setObjectName("transparentRow")  # 카드 위에서 회색 띠로 보이지 않도록
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    label = QLabel(title)
    label.setObjectName(object_name)
    layout.addWidget(label)
    if info_text:
        layout.addWidget(InfoIcon(info_text))
    layout.addStretch()
    return container


def build_label_with_info(text, info_text: str) -> QWidget:
    """
    폼(QFormLayout)의 라벨 자리에 넣는 "라벨 + hover 정보 아이콘" 위젯.
    필드 하나하나에 붙는 설명을 접어두는 용도.

    text는 문자열이거나 이미 만들어진 라벨 위젯(예: Step3 Pin Settings의 상위 pin용
    굵은 라벨)일 수 있다.
    """
    container = QWidget()
    container.setObjectName("transparentRow")  # 카드 위에서 회색 띠로 보이지 않도록
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    label = text if isinstance(text, QWidget) else QLabel(text)
    layout.addWidget(label)
    layout.addWidget(InfoIcon(info_text))
    layout.addStretch()
    return container


def build_hint(text: str) -> QLabel:
    """화면에 그대로 남겨두는 짧은 보조 문구 (긴 설명은 InfoIcon 툴팁으로 옮길 것)."""
    label = QLabel(text)
    label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
    label.setWordWrap(True)
    return label


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

# ---------------------------------------------------------------------------
# 필수 입력칸 "Must fill" 표시 - Step2/Step3 Validate 때 비어 있어서 에러가 난 입력칸을
# 빨간 테두리 + 안내 문구로 표시한다. 입력할 칸이 많아 놓친 칸을 바로 찾을 수 있도록.
#   - QLineEdit: 빨간 테두리/배경 + placeholder를 "Must fill"로 바꿈
#   - QComboBox: 빨간 테두리/배경 + 빈 선택지(data가 "")의 문구를 "Must select"로 바꿈
# 사용자가 값을 채우면(글자 입력/선택 변경) 그 칸의 표시는 즉시 사라진다.
# ---------------------------------------------------------------------------
MISSING_REQUIRED_PROPERTY = "missingRequired"
MISSING_FILL_TEXT = "Must fill"
MISSING_SELECT_TEXT = "Must select"
_ORIGINAL_TEXT_PROPERTY = "_missingRequiredOriginalText"
_HOOKED_PROPERTY = "_missingRequiredHooked"


def _is_empty_required(widget: QWidget) -> bool:
    if isinstance(widget, QLineEdit):
        return not widget.text().strip()
    if isinstance(widget, QComboBox):
        if widget.currentIndex() < 0:
            return True
        data = widget.currentData()
        # data 없이 addItems()로만 채운 드롭다운은 보이는 글자로 판단한다.
        return not str(widget.currentText() if data is None else data).strip()
    return False


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _set_missing_required(widget: QWidget, missing: bool) -> None:
    was_missing = bool(widget.property(MISSING_REQUIRED_PROPERTY))
    if was_missing == missing:
        return
    widget.setProperty(MISSING_REQUIRED_PROPERTY, missing)
    _repolish(widget)

    if isinstance(widget, QLineEdit):
        if missing:
            widget.setProperty(_ORIGINAL_TEXT_PROPERTY, widget.placeholderText())
            widget.setPlaceholderText(MISSING_FILL_TEXT)
            palette = widget.palette()
            palette.setColor(QPalette.PlaceholderText, QColor(ERROR_COLOR))
            widget.setPalette(palette)
        else:
            widget.setPlaceholderText(str(widget.property(_ORIGINAL_TEXT_PROPERTY) or ""))
            widget.setPalette(QPalette())
    elif isinstance(widget, QComboBox) and widget.count() > 0 and widget.itemData(0) in ("", None):
        # 빈 선택지("(Select)"/"(None)")가 맨 앞에 있는 드롭다운만 문구를 바꾼다.
        if missing:
            widget.setProperty(_ORIGINAL_TEXT_PROPERTY, widget.itemText(0))
            widget.setItemText(0, MISSING_SELECT_TEXT)
        else:
            original = widget.property(_ORIGINAL_TEXT_PROPERTY)
            if original is not None and widget.itemText(0) == MISSING_SELECT_TEXT:
                widget.setItemText(0, str(original))


def _hook_auto_clear(widget: QWidget) -> None:
    """값이 채워지는 순간 표시를 지우도록 한 번만 연결한다."""
    if widget.property(_HOOKED_PROPERTY):
        return
    widget.setProperty(_HOOKED_PROPERTY, True)

    def _on_changed(*_args) -> None:
        if widget.property(MISSING_REQUIRED_PROPERTY) and not _is_empty_required(widget):
            _set_missing_required(widget, False)

    if isinstance(widget, QLineEdit):
        widget.textChanged.connect(_on_changed)
    elif isinstance(widget, QComboBox):
        widget.currentIndexChanged.connect(_on_changed)


def highlight_empty_required_fields(widgets) -> list[QWidget]:
    """
    넘겨받은 필수 입력칸 중 비어 있는 칸은 "Must fill"로 표시하고, 채워진 칸은 표시를
    지운다. 표시한 칸 목록을 돌려준다(화면 순서 그대로) - 호출한 쪽에서 접혀 있는
    카드를 펼치고 첫 번째 칸으로 스크롤(scroll_to_widget)하는 데 쓴다.

    어떤 칸이 "필수"인지는 호출한 쪽(각 Step 화면)이 validator 규칙에 맞춰 골라서
    넘긴다 - 비어 있으면 항상 Validate 에러가 나는 칸만 넘길 것.
    """
    marked: list[QWidget] = []
    for widget in widgets:
        if widget is None:
            continue
        _hook_auto_clear(widget)
        missing = _is_empty_required(widget)
        _set_missing_required(widget, missing)
        if missing:
            marked.append(widget)
    return marked


def scroll_to_widget(widget: QWidget) -> None:
    """
    widget을 감싸는 QScrollArea가 있으면 그 widget이 보이도록 스크롤한다. 방금 펼친
    카드 안의 칸일 수 있으므로 레이아웃이 다시 계산된 다음(이벤트 루프 한 바퀴 뒤)에
    스크롤한다.
    """
    def _scroll() -> None:
        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                parent.ensureWidgetVisible(widget, 50, 50)
                return
            parent = parent.parentWidget()

    QTimer.singleShot(0, _scroll)
