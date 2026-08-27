"""
file_viewer.py

생성된 liberty 파일을 **새 창**으로 열어서 보는 읽기 전용 뷰어 (2026-08 추가).

Step4에서 파일 아이콘을 클릭하면 이 창이 뜬다. 화면 구성/조작감을 vi/vim에 맞췄다:
  - 어두운 배경 + 고정폭 글꼴 + 왼쪽 줄번호 거터
  - 맨 아래 vim 스타일 상태줄 ("파일경로" 1234L, 56789B  --12%--)
  - 읽기 전용 (실수로 내용이 바뀌지 않음)
  - 이동 키: j/k, h/l, g/G, Ctrl+D/Ctrl+U, q 또는 Esc로 창 닫기
  - 검색: "/"를 누르면 상태줄 위에 vim 스타일 검색창이 뜨고, 패턴을 입력한 뒤 Enter로
    검색한다(끝까지 못 찾으면 파일 처음/끝에서 한 번 더 시도해 자동으로 wrap-around
    한다). n = 같은 방향으로 다음 일치, N = 반대 방향. 검색창에서 Esc를 누르면 검색을
    취소하고 본문으로 포커스가 돌아간다 (2026-08 추가 - 읽기 전용이어도 vi의 기본
    검색 명령은 그대로 먹히게 해 달라는 요청 반영).

**환경 제약 (2026-08 확인)**: 실제 `vi`/`vim` 프로세스를 띄우려면 터미널
에뮬레이터(xterm 등)가 필요하고, GUI를 X11 forwarding으로 띄우는 VWP 환경에서는 그게
항상 있다고 보장할 수 없다(+ 외부 프로세스가 뜨면 앱이 그 창의 생명주기를 관리할 수도
없다). 그래서 외부 편집기를 실행하지 않고 **앱 안에 vim처럼 보이고 동작하는 뷰어 창을
직접 구현**했다. 편집/저장은 지원하지 않는다(생성 결과를 보는 용도).

아주 큰 파일은 전부 메모리에 올리면 창이 멈추므로 앞부분 _MAX_LINES 줄까지만 읽고,
상태줄에 잘렸다는 표시를 남긴다.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QRect, QSize, Qt
from PyQt5.QtGui import (
    QColor, QFont, QFontMetrics, QKeyEvent, QPainter, QTextCursor, QTextDocument,
    QTextFormat, QTextOption,
)
from PyQt5.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPlainTextEdit, QTextEdit, QVBoxLayout,
    QWidget,
)

# vim 기본 배색(어두운 테마)에 가깝게
_BG_COLOR = "#1E1E1E"
_FG_COLOR = "#D4D4D4"
_GUTTER_BG = "#252526"
_GUTTER_FG = "#7A7A7A"
_CURRENT_LINE_BG = "#2A2D2E"
_STATUS_BG = "#3A3D41"
_STATUS_FG = "#E8E8E8"

_MONOSPACE_FAMILIES = "DejaVu Sans Mono, Liberation Mono, Courier New, monospace"

# 한 번에 읽어 들일 최대 줄 수 / 파일 크기 (그보다 크면 앞부분만 보여준다)
_MAX_LINES = 200000
_MAX_BYTES = 40 * 1024 * 1024

_VIEWER_DEFAULT_WIDTH = 1000
_VIEWER_DEFAULT_HEIGHT = 720


class _LineNumberArea(QWidget):
    """편집기 왼쪽에 줄번호를 그리는 거터 (Qt 공식 CodeEditor 예제와 같은 구조)."""

    def __init__(self, editor: "_ViewerEdit"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        self.editor.paint_line_numbers(event)


class _ViewerEdit(QPlainTextEdit):
    """읽기 전용 + 줄번호 + vim식 이동/검색 키를 가진 텍스트 뷰."""

    def __init__(self, on_quit, on_search_start, on_search_step, parent=None):
        super().__init__(parent)
        self._on_quit = on_quit
        self._on_search_start = on_search_start
        self._on_search_step = on_search_step
        self.setReadOnly(True)
        self.setWordWrapMode(QTextOption.NoWrap)
        self.setFrameShape(QPlainTextEdit.NoFrame)

        font = QFont(_MONOSPACE_FAMILIES.split(",")[0].strip())
        font.setStyleHint(QFont.Monospace)
        font.setFixedPitch(True)
        font.setPointSize(11)
        self.setFont(font)
        self.setTabStopWidth(4 * QFontMetrics(font).width(" "))
        self.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {_BG_COLOR}; color: {_FG_COLOR}; "
            f"border: none; selection-background-color: #264F78; }}"
        )

        self.line_number_area = _LineNumberArea(self)
        self.blockCountChanged.connect(lambda _c: self._update_line_number_area_width())
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_area_width()
        self._highlight_current_line()

    # -- 줄번호 거터 --------------------------------------------------------
    def line_number_area_width(self) -> int:
        digits = max(3, len(str(max(1, self.blockCount()))))
        # Qt 5.11 미만에는 horizontalAdvance()가 없어 width()로 폴백해야 한다
        # (VWP의 Qt가 그렇다 - CLAUDE.md 실행 환경 참고).
        metrics = self.fontMetrics()
        char_width = (
            metrics.horizontalAdvance("9") if hasattr(metrics, "horizontalAdvance")
            else metrics.width("9")
        )
        return 12 + char_width * digits

    def _update_line_number_area_width(self) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0, rect.y(), self.line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(_GUTTER_BG))
        painter.setPen(QColor(_GUTTER_FG))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        line_height = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0, int(top), self.line_number_area.width() - 6, line_height,
                    Qt.AlignRight, str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def _highlight_current_line(self) -> None:
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(_CURRENT_LINE_BG))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    # -- vim식 키 조작 ------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        key = event.key()
        modifiers = event.modifiers()
        text = event.text()

        if key in (Qt.Key_Q, Qt.Key_Escape) and not (modifiers & Qt.ControlModifier):
            self._on_quit()
            return
        if text == "/" and not (modifiers & Qt.ControlModifier):
            self._on_search_start()
            return
        if text == "n":
            self._on_search_step(True)
            return
        if text == "N":
            self._on_search_step(False)
            return
        if modifiers & Qt.ControlModifier and key == Qt.Key_D:
            self._move_cursor_pages(0.5)
            return
        if modifiers & Qt.ControlModifier and key == Qt.Key_U:
            self._move_cursor_pages(-0.5)
            return
        if key == Qt.Key_G:
            # G = 파일 끝, g = 파일 처음 (vim의 gg를 한 번으로 단순화)
            self.moveCursor(
                QTextCursor.End if modifiers & Qt.ShiftModifier else QTextCursor.Start
            )
            return

        replacement = {
            Qt.Key_J: Qt.Key_Down, Qt.Key_K: Qt.Key_Up,
            Qt.Key_H: Qt.Key_Left, Qt.Key_L: Qt.Key_Right,
        }.get(key)
        if replacement is not None:
            super().keyPressEvent(_remap(event, replacement))
            return

        super().keyPressEvent(event)

    def _move_cursor_pages(self, pages: float) -> None:
        visible_lines = self.viewport().height() / max(1, self.fontMetrics().height())
        lines = int(visible_lines * pages)
        operation = QTextCursor.Down if lines > 0 else QTextCursor.Up
        for _ in range(max(1, abs(lines))):
            self.moveCursor(operation)


def _remap(event, key: int) -> QKeyEvent:
    """j/k/h/l 키 입력을 방향키 이벤트로 바꿔서 그대로 넘긴다."""
    return QKeyEvent(event.type(), key, event.modifiers())


class _SearchEdit(QLineEdit):
    """
    "/" 검색창. Enter는 QLineEdit 기본 returnPressed로 처리하고, Esc만 여기서 가로채
    (기본 동작이 없으므로) 검색을 취소하는 콜백을 부른다.
    """

    def __init__(self, on_cancel, parent=None):
        super().__init__(parent)
        self._on_cancel = on_cancel

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        if event.key() == Qt.Key_Escape:
            self._on_cancel()
            return
        super().keyPressEvent(event)


class FileViewerWindow(QMainWindow):
    """
    파일 하나를 보여주는 독립 창. 여러 개를 동시에 띄울 수 있으며, 닫으면 스스로
    정리된다(WA_DeleteOnClose).
    """

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        # 부모(메인 윈도우) 위에 붙는 종속 창이 아니라 독립된 창으로 띄운다.
        self.setWindowFlags(Qt.Window)
        self.file_path = str(file_path)
        self.setWindowTitle(f"{Path(self.file_path).name} - Liberty Generator (read-only)")
        self.resize(_VIEWER_DEFAULT_WIDTH, _VIEWER_DEFAULT_HEIGHT)

        self.edit = _ViewerEdit(self.close, self._start_search, self._step_search)
        self._last_search = ""

        # "/" 검색창 - 평소엔 숨겨져 있다가 "/"를 누르면 본문과 상태줄 사이에 나타난다
        # (vim이 화면 맨 아래에 명령줄을 띄우는 것과 같은 자리).
        search_row = QWidget()
        search_row.setVisible(False)
        search_row.setStyleSheet(f"background-color: {_STATUS_BG};")
        search_layout = QHBoxLayout(search_row)
        search_layout.setContentsMargins(6, 2, 6, 2)
        search_layout.setSpacing(4)
        prefix_label = QLabel("/")
        prefix_label.setStyleSheet(
            f"color: {_STATUS_FG}; font-family: {_MONOSPACE_FAMILIES}; font-size: 12px;"
        )
        search_layout.addWidget(prefix_label)
        self.search_edit = _SearchEdit(self._cancel_search)
        self.search_edit.setStyleSheet(
            f"background-color: {_BG_COLOR}; color: {_FG_COLOR}; border: none; "
            f"font-family: {_MONOSPACE_FAMILIES}; font-size: 12px; padding: 2px 4px;"
        )
        self.search_edit.returnPressed.connect(self._submit_search)
        search_layout.addWidget(self.search_edit, 1)
        self.search_row = search_row

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.edit, 1)
        central_layout.addWidget(self.search_row)
        self.setCentralWidget(central)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"background-color: {_STATUS_BG}; color: {_STATUS_FG}; padding: 3px 8px; "
            f"font-family: {_MONOSPACE_FAMILIES}; font-size: 12px;"
        )
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().setStyleSheet(f"background-color: {_STATUS_BG}; border: none;")

        self._load()
        self.edit.cursorPositionChanged.connect(self._refresh_status)

    def _load(self) -> None:
        path = Path(self.file_path)
        self._truncated = False
        try:
            size = path.stat().st_size
            lines: list[str] = []
            loaded_bytes = 0
            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if len(lines) >= _MAX_LINES or loaded_bytes >= _MAX_BYTES:
                        self._truncated = True
                        break
                    loaded_bytes += len(line)
                    lines.append(line.rstrip("\n"))
            self._byte_size = size
            self.edit.setPlainText("\n".join(lines))
            self._line_count = len(lines)
        except OSError as e:
            self._byte_size = 0
            self._line_count = 0
            self.edit.setPlainText(f'"{self.file_path}" could not be opened: {e}')
        self.edit.moveCursor(QTextCursor.Start)
        self._refresh_status()

    # -- "/" 검색 -----------------------------------------------------------
    def _start_search(self) -> None:
        self.search_row.setVisible(True)
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _cancel_search(self) -> None:
        self.search_row.setVisible(False)
        self.edit.setFocus()

    def _submit_search(self) -> None:
        pattern = self.search_edit.text()
        self.search_row.setVisible(False)
        self.edit.setFocus()
        if not pattern:
            return
        self._last_search = pattern
        self._run_search(pattern, forward=True)

    def _step_search(self, forward: bool) -> None:
        """n(forward) / N(backward)로 마지막 검색어를 다시 찾는다."""
        if not self._last_search:
            return
        self._run_search(self._last_search, forward=forward)

    def _run_search(self, pattern: str, forward: bool) -> None:
        """
        현재 커서 위치부터 찾고, 끝(또는 시작)까지 못 찾으면 파일 반대쪽 끝으로 커서를
        옮겨 한 번 더 시도한다 - vim의 검색 wrap-around와 같은 동작.
        """
        flags = QTextDocument.FindFlags()
        if not forward:
            flags |= QTextDocument.FindBackward

        found = self.edit.find(pattern, flags)
        if not found:
            cursor = self.edit.textCursor()
            cursor.movePosition(QTextCursor.Start if forward else QTextCursor.End)
            self.edit.setTextCursor(cursor)
            found = self.edit.find(pattern, flags)

        if not found:
            self.status_label.setText(f'Pattern not found: "{pattern}"')

    def _refresh_status(self) -> None:
        """vim 상태줄 흉내: "경로" 1234L, 5678B  12,1  Top/All/xx%"""
        cursor = self.edit.textCursor()
        line = cursor.blockNumber() + 1
        column = cursor.columnNumber() + 1
        total = max(1, self._line_count)
        percent = int(line * 100 / total)
        position = "All" if total <= 1 else ("Top" if line == 1 else (
            "Bot" if line == total else f"{percent}%"
        ))
        truncated = (
            f"  [only the first {_MAX_LINES} lines are shown]" if self._truncated else ""
        )
        # 전체 경로는 길어서 상태줄에서 잘리므로 파일명만 쓰고, 전체 경로는 창 제목과
        # 상태줄 툴팁으로 보여준다 (vim의 상태줄도 보통 짧은 경로만 보여준다).
        self.status_label.setToolTip(self.file_path)
        self.status_label.setText(
            f'"{Path(self.file_path).name}" {self._line_count}L, {self._byte_size}B'
            f"   {line},{column}   {position}   [read-only: j/k move, / search, q closes]{truncated}"
        )


def open_file_viewer(file_path: str, parent=None) -> FileViewerWindow | None:
    """
    파일을 새 창으로 연다. 파일이 없으면 아무것도 하지 않고 None을 반환한다.
    호출한 쪽은 반환된 창의 참조를 들고 있어야 한다(그렇지 않으면 GC로 즉시 닫힘).
    """
    if not file_path or not Path(file_path).is_file():
        return None
    window = FileViewerWindow(file_path, parent)
    window.show()
    window.raise_()
    window.activateWindow()
    return window
