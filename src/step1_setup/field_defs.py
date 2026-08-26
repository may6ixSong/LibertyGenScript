"""
field_defs.py

이 프로젝트의 입력 필드 및 파일 형식 정의를 모아두는 곳.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 입력 경로: (key, 라벨, 종류, 허용 확장자 목록)
#   종류: "dir" = 폴더 선택, "file" = 파일 선택
#   허용 확장자는 "file" 종류에만 적용 (dir은 None)
# ---------------------------------------------------------------------------
INPUT_PATH_FIELDS = [
    ("pdk_folder", "PDK Folder", "dir", None),
    ("dbs_folder", "DBS Simulation Folder", "dir", None),
    ("port_list_file", "Port List (Excel)", "file", [".xls", ".xlsx"]),
]

DBS_FILE_EXTENSION = ".mt0"

# PDK/DK 파일 인식 규칙 (2026-08 확정): 화이트리스트가 아니라, 확장자가 ".lib"로
# 시작하는 파일이면 전부 PDK 파일로 인식한다 (.lib, .lib_css_tn, 그 외 어떤 접미사가
# 붙어도 인식됨).
PDK_EXTENSION_PREFIX = ".lib"


def is_pdk_filename(filename: str) -> bool:
    dot = filename.rfind(".")
    if dot == -1:
        return False
    return filename[dot:].lower().startswith(PDK_EXTENSION_PREFIX)


def strip_pdk_extension(filename: str) -> str | None:
    dot = filename.rfind(".")
    if dot == -1 or not filename[dot:].lower().startswith(PDK_EXTENSION_PREFIX):
        return None
    return filename[:dot]


# ---------------------------------------------------------------------------
# Port List 시트 검증 규칙
#   REQUIRED: 모든 row에 값이 있어야 하는 컬럼
#   OPTIONAL: 컬럼이 있어도 값이 비어있을 수 있는 컬럼 (있으면 인식만 함)
# ---------------------------------------------------------------------------
PORT_LIST_REQUIRED_COLUMNS = [
    "Port", "Pin name", "Bits", "Num", "I/O", "Volts", "Cap", "Map",
]
PORT_LIST_OPTIONAL_COLUMNS = [
    "Related Power", "Related ground", "Related Pin", "Timing reference",
]

# ---------------------------------------------------------------------------
# 'Port' 컬럼 값 -> 행 분류 (2026-08 확정)
#   PORT = I/O 신호 핀, PWR = 전원 핀, GND = 접지 핀
# ---------------------------------------------------------------------------
PORT_TYPE_IO = "PORT"
PORT_TYPE_PWR = "PWR"
PORT_TYPE_GND = "GND"
PORT_TYPE_VALUES = [PORT_TYPE_IO, PORT_TYPE_PWR, PORT_TYPE_GND]