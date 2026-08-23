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
"""