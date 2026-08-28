"""
theme.py

Liberty Generator GUI 전역 스타일(QSS) 및 색상 상수.
"""

PRIMARY_COLOR = "#4F46E5"
PRIMARY_TINT = "#EEF0FE"
PRIMARY_COLOR_HOVER = "#4338CA"
PRIMARY_COLOR_DISABLED = "#C7C9F5"
BACK_BUTTON_COLOR = "#6B7280"
BACK_BUTTON_COLOR_HOVER = "#4B5563"
BACK_BUTTON_COLOR_DISABLED = "#D1D5DB"

# Import Config 버튼 색 (2026-08 추가): "초록 계열"이되, Validate 결과에 쓰이는
# SUCCESS_COLOR(순수 녹색)와 나란히 보여도 헷갈리지 않도록 청록 쪽으로 살짝 튼 색을 쓴다.
IMPORT_BUTTON_COLOR = "#0D9488"
IMPORT_BUTTON_COLOR_HOVER = "#0F766E"
BACKGROUND_COLOR = "#F3F4F8"
CARD_COLOR = "#FFFFFF"
BORDER_COLOR = "#E4E6EF"
TEXT_COLOR = "#1F2430"
MUTED_TEXT_COLOR = "#6B7280"
ERROR_COLOR = "#DC2626"
SUCCESS_COLOR = "#16A34A"
PENDING_COLOR = "#9CA3AF"
VOLTAGE_COLOR = "#2563EB"
WARNING_BG = "#FEF9E7"
WARNING_BORDER = "#F5D06B"
WARNING_TEXT = "#8A6D1D"

# 추천(자동 매칭된) PDK/DBS 파일을 드롭다운/행에서 강조할 때 쓰는 색
RECOMMEND_BG = "#ECFDF5"
RECOMMEND_BORDER = "#6EE7B7"
RECOMMEND_TEXT = "#047857"

# 창 기본 크기 (2026-08 레이아웃 개편: Step3의 입력이 스크롤 없이 보이도록 넓혔다)
WINDOW_DEFAULT_WIDTH = 1560
WINDOW_DEFAULT_HEIGHT = 1000
WINDOW_MIN_WIDTH = 1180
WINDOW_MIN_HEIGHT = 760

APP_STYLESHEET = f"""
QWidget {{
    background-color: {BACKGROUND_COLOR};
    color: {TEXT_COLOR};
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}

QMainWindow {{
    background-color: {BACKGROUND_COLOR};
}}

QFrame#card {{
    background-color: {CARD_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 12px;
}}

/* 카드(흰 배경) 안에 놓인 라벨/레이아웃용 빈 위젯이 전역 QWidget 배경색(회색)을
   그대로 칠해서 회색 띠처럼 보이는 것을 막는다. 배경이 필요한 라벨은 자기 자신의
   objectName 규칙이나 인라인 스타일로 덮어쓰므로 영향받지 않는다. */
QLabel {{
    background: transparent;
}}

QWidget#transparentRow {{
    background: transparent;
}}

QLabel#titleLabel {{
    font-size: 24px;
    font-weight: 700;
    color: {TEXT_COLOR};
}}

QLabel#subtitleLabel {{
    font-size: 12px;
    color: {MUTED_TEXT_COLOR};
}}

QLabel#sectionLabel {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT_COLOR};
}}

QLineEdit {{
    background-color: #FAFBFF;
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: {PRIMARY_COLOR};
}}

QLineEdit:focus {{
    border: 1px solid {PRIMARY_COLOR};
}}

QPushButton {{
    background-color: #FFFFFF;
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    padding: 7px 16px;
    color: {TEXT_COLOR};
}}

QPushButton:hover {{
    background-color: #F0F1FA;
}}

QPushButton:pressed {{
    background-color: #E4E6EF;
}}

QPushButton#primaryButton {{
    background-color: {PRIMARY_COLOR};
    color: white;
    border: none;
    font-weight: 600;
    padding: 10px 22px;
    border-radius: 10px;
}}

QPushButton#primaryButton:hover {{
    background-color: {PRIMARY_COLOR_HOVER};
}}

QPushButton#primaryButton:disabled {{
    background-color: {PRIMARY_COLOR_DISABLED};
    color: #F0F1FF;
}}

QPushButton#backButton {{
    background-color: {BACK_BUTTON_COLOR};
    color: white;
    border: none;
    font-weight: 600;
    padding: 10px 22px;
    border-radius: 10px;
}}

QPushButton#backButton:hover {{
    background-color: {BACK_BUTTON_COLOR_HOVER};
}}

QPushButton#backButton:disabled {{
    background-color: {BACK_BUTTON_COLOR_DISABLED};
    color: #F3F4F6;
}}

QPushButton#importButton {{
    background-color: {IMPORT_BUTTON_COLOR};
    color: white;
    border: none;
    font-weight: 600;
    padding: 7px 16px;
    border-radius: 8px;
}}

QPushButton#importButton:hover {{
    background-color: {IMPORT_BUTTON_COLOR_HOVER};
}}

QPushButton#iconDangerButton {{
    background-color: transparent;
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    padding: 0px;
    font-size: 14px;
}}

QPushButton#iconDangerButton:hover {{
    background-color: #FEF2F2;
    border: 1px solid {ERROR_COLOR};
    color: {ERROR_COLOR};
}}

QFrame#noteBanner {{
    background-color: {WARNING_BG};
    border: 1px solid {WARNING_BORDER};
    border-radius: 10px;
}}

QLabel#noteLabel {{
    color: {WARNING_TEXT};
    font-size: 12px;
}}

QListWidget#resultsList {{
    background-color: {CARD_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 10px;
    padding: 4px;
    outline: none;
}}

QListWidget#resultsList::item {{
    padding: 6px 8px;
    border-radius: 6px;
}}

QListWidget#resultsList::item:selected {{
    background-color: transparent;
}}

QLabel#infoIcon {{
    background-color: {PRIMARY_TINT};
    color: {PRIMARY_COLOR};
    border: 1px solid {PRIMARY_COLOR_DISABLED};
    border-radius: 8px;
    font-size: 10px;
    font-weight: 700;
    font-style: italic;
}}

QToolTip {{
    background-color: {TEXT_COLOR};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 12px;
}}

QFrame#entryCard {{
    background-color: {CARD_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 10px;
}}

QFrame#entryCard:hover {{
    border: 1px solid {PRIMARY_COLOR_DISABLED};
}}

QComboBox {{
    background-color: #FAFBFF;
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    padding: 5px 8px;
}}

QComboBox:focus {{
    border: 1px solid {PRIMARY_COLOR};
}}

QSpinBox {{
    background-color: #FAFBFF;
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    padding: 4px 6px;
}}

QTableWidget {{
    background-color: {CARD_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    gridline-color: {BORDER_COLOR};
}}
"""