"""
port_list_reader.py

Port List Excel 파일(.xls/.xlsx)을 읽어 대상 시트를 찾고, 헤더 행을 유동적으로
탐지한 뒤 필수 컬럼 값 존재 여부를 검사하고 port 개수를 세는 로직.
GUI에 의존하지 않는 순수 함수로 작성.

- .xlsx 는 openpyxl 로 읽음
- .xls (구 포맷) 는 openpyxl이 지원하지 않아 xlrd 로 읽음
  (둘 다 없다면 이 파일 최초 import 시가 아니라, 실제 해당 확장자 파일을
   읽으려는 시점에 ImportError가 발생함 - 그때 필요한 것만 설치하면 됨.
   xlrd가 없을 때는 "무엇을 설치하면 되는지"가 그대로 Step1 Details에 뜨도록
   _import_xlrd()에서 메시지를 바꿔 올린다)
- 허용 확장자 목록은 field_defs.PORT_LIST_FILE_EXTENSIONS 하나로 관리한다.
"""

from __future__ import annotations

import re
from pathlib import Path

from step1_setup.field_defs import (
    PORT_LIST_FILE_EXTENSIONS, PORT_LIST_OPTIONAL_COLUMNS, PORT_LIST_REQUIRED_COLUMNS,
    PORT_TYPE_GND, PORT_TYPE_IO, PORT_TYPE_PWR,
)

# read_port_list_rows()가 각 행마다 담아주는 컬럼 전체 (필수 + 선택).
# 이 순서/집합에 없는 컬럼은 구조화 결과에 포함되지 않음 (필요해지면 여기에 추가).
_ALL_ROW_COLUMNS = PORT_LIST_REQUIRED_COLUMNS + PORT_LIST_OPTIONAL_COLUMNS

# 시트에 나타날 수 있는 헤더 문자열(대소문자/공백/기호 무시하고 매칭)을
# 표준 컬럼명으로 정규화하기 위한 매핑
_HEADER_ALIASES = {
    "port": "Port",
    "pinname": "Pin name",
    "bits": "Bits",
    "num": "Num",
    "io": "I/O",
    "volts": "Volts",
    "cap": "Cap",
    "map": "Map",
    "relatedpower": "Related Power",
    "relatedground": "Related ground",
    "relatedpin": "Related Pin",
    "timingreference": "Timing reference",
    "block": "Block",
    "maxtransition": "Max transition",
    "functionaldescription": "Functional Description",
    "description": "Description",
    "type": "Type",
    "defaultbinaryhex": "Default(binary/hex)",
    "digitalreg": "Digital Reg",
}

_MAX_HEADER_SCAN_ROWS = 5
_SHEET_NAME_HINT = "port list"


def _normalize(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _is_valid_int(value) -> bool:
    """
    Bits 컬럼 값 검사용. 정수만 허용(소수점 있는 값은 불허), 엑셀에서 숫자 셀은
    float(예: 4.0)로 들어올 수 있으므로 그 경우도 정수로 취급한다.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    text = str(value).strip()
    if not text:
        return False
    try:
        return float(text).is_integer()
    except ValueError:
        return False


def _to_int(value) -> int:
    return int(float(value))


_VOLTS_NUMBER_PATTERN = re.compile(r"[-+]?\d*\.?\d+")


def parse_volts_value(value) -> float | None:
    """
    Port List 'Volts' 컬럼 값에서 숫자만 뽑아 float으로 반환한다. 단위가 붙어있는
    경우(예: "0.8V", "0.8 V")도 앞의 숫자 부분만 파싱한다. 숫자를 찾을 수 없으면
    None (예외를 던지지 않음 - block4의 pg_pin 작성에서 결측 처리로 이어짐).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = _VOLTS_NUMBER_PATTERN.search(text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _import_xlrd():
    """
    .xls(구 엑셀 포맷)를 읽는 데 필요한 xlrd를 import한다. 없으면 무슨 패키지가
    필요한지 바로 알 수 있는 메시지로 바꿔서 올린다 (Step1 Validate 화면의 Details에
    그대로 표시된다).
    """
    try:
        import xlrd  # noqa: PLC0415 - 확장자가 .xls일 때만 필요한 선택적 의존성
    except ImportError as e:
        raise ImportError(
            "Reading an .xls (old Excel format) file requires the 'xlrd' package. "
            "Install it (pip install xlrd) or save the Port List as .xlsx."
        ) from e
    return xlrd


def _suffix_of(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix not in PORT_LIST_FILE_EXTENSIONS:
        raise ValueError(
            "Unsupported Port List file extension: %s (expected %s)"
            % (suffix or "(none)", " / ".join(PORT_LIST_FILE_EXTENSIONS))
        )
    return suffix


def _list_sheet_names(file_path: str) -> list[str]:
    if _suffix_of(file_path) == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(file_path, read_only=True)
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()

    xlrd = _import_xlrd()
    wb = xlrd.open_workbook(file_path, on_demand=True)
    return list(wb.sheet_names())


def _load_sheet_rows(file_path: str, sheet_name: str) -> list[list]:
    """지정된 시트의 전체 셀 값을 2차원 리스트(행 우선, 1행부터 순서대로)로 반환."""
    if _suffix_of(file_path) == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(file_path, read_only=True, data_only=True)
        try:
            sheet = wb[sheet_name]
            return [[cell.value for cell in row] for row in sheet.iter_rows()]
        finally:
            wb.close()

    xlrd = _import_xlrd()
    wb = xlrd.open_workbook(file_path)
    sheet = wb.sheet_by_name(sheet_name)
    return [
        [sheet.cell_value(r, c) for c in range(sheet.ncols)]
        for r in range(sheet.nrows)
    ]


def find_port_list_sheet_name(file_path: str) -> str | None:
    """시트명에 (대소문자 무관) 'port list'가 포함된 첫 시트명을 반환."""
    if not file_path or not Path(file_path).is_file():
        return None
    for name in _list_sheet_names(file_path):
        if _SHEET_NAME_HINT in name.lower():
            return name
    return None


def _find_header_row(rows: list[list]) -> tuple[int, dict[str, int]]:
    """
    상단 몇 개 행(_MAX_HEADER_SCAN_ROWS)을 스캔해서 알려진 컬럼명과 가장 많이
    일치하는 행을 헤더 행으로 판단 (1행일 수도, 2행일 수도 있으므로 유동 탐지).

    Returns:
        (header_row_index(1-based, 못 찾으면 0), {표준_컬럼명: col_index(1-based)})
    """
    best_row_idx = 0
    best_map: dict[str, int] = {}

    for row_idx, row in enumerate(rows[:_MAX_HEADER_SCAN_ROWS], start=1):
        header_map: dict[str, int] = {}
        for col_idx, value in enumerate(row, start=1):
            if value is None or str(value).strip() == "":
                continue
            canonical = _HEADER_ALIASES.get(_normalize(str(value)))
            if canonical:
                header_map[canonical] = col_idx
        if len(header_map) > len(best_map):
            best_map = header_map
            best_row_idx = row_idx

    return best_row_idx, best_map


def read_port_list(file_path: str) -> dict:
    """
    Port List Excel 파일을 읽어 검증 결과를 반환.

    Returns:
        {
            "sheet_name": str | None,
            "header_row": int,
            "found_columns": [str, ...],
            "missing_required_columns": [str, ...],
            "port_count": int,
            "row_errors": [str, ...],   # "Row 12: missing value for Port" 형태
        }
    """
    sheet_name = find_port_list_sheet_name(file_path)
    if sheet_name is None:
        return {
            "sheet_name": None,
            "header_row": 0,
            "found_columns": [],
            "missing_required_columns": list(PORT_LIST_REQUIRED_COLUMNS),
            "port_count": 0,
            "row_errors": [],
        }

    rows = _load_sheet_rows(file_path, sheet_name)
    header_row, column_map = _find_header_row(rows)
    missing_required = [c for c in PORT_LIST_REQUIRED_COLUMNS if c not in column_map]

    row_errors: list[str] = []
    port_count = 0

    if not missing_required:
        for row_idx, row in enumerate(rows[header_row:], start=header_row + 1):
            def _value_at(col_idx: int, _row=row):
                return _row[col_idx - 1] if col_idx - 1 < len(_row) else None

            required_values = [_value_at(column_map[c]) for c in PORT_LIST_REQUIRED_COLUMNS]
            if all(v is None or str(v).strip() == "" for v in required_values):
                continue  # 완전히 빈 행은 데이터 끝으로 간주하고 건너뜀

            missing_in_row = [
                c for c in PORT_LIST_REQUIRED_COLUMNS
                if _value_at(column_map[c]) is None or str(_value_at(column_map[c])).strip() == ""
            ]
            if missing_in_row:
                row_errors.append(f"Row {row_idx}: missing value for {', '.join(missing_in_row)}")
                continue

            # 2026-08 확정: Bits 컬럼은 정수여야 함 (Step4 block3의 type_bus 생성이
            # 이 값을 그대로 bit_width/bit_from으로 사용하므로, 숫자가 아니면 여기서
            # 걸러내야 함).
            bits_value = _value_at(column_map["Bits"])
            if not _is_valid_int(bits_value):
                row_errors.append(f"Row {row_idx}: Bits value is not a valid integer: {bits_value!r}")
                continue

            port_count += 1

    return {
        "sheet_name": sheet_name,
        "header_row": header_row,
        "found_columns": sorted(column_map.keys()),
        "missing_required_columns": missing_required,
        "port_count": port_count,
        "row_errors": row_errors,
    }


def list_pins_by_port_type(file_path: str, port_type: str) -> list[str]:
    """Port List에서 'Port' 컬럼 값이 port_type과 일치하는 행들의 'Pin name' 값 목록을 반환."""
    sheet_name = find_port_list_sheet_name(file_path)
    if sheet_name is None:
        return []

    rows = _load_sheet_rows(file_path, sheet_name)
    header_row, column_map = _find_header_row(rows)
    if "Port" not in column_map or "Pin name" not in column_map:
        return []

    port_col = column_map["Port"]
    pin_col = column_map["Pin name"]
    target = port_type.strip().upper()

    result = []
    for row in rows[header_row:]:
        port_val = row[port_col - 1] if port_col - 1 < len(row) else None
        pin_val = row[pin_col - 1] if pin_col - 1 < len(row) else None
        if port_val is None or pin_val is None:
            continue
        if str(port_val).strip().upper() == target:
            name = str(pin_val).strip()
            if name:
                result.append(name)
    return result


def read_port_list_rows(file_path: str) -> dict:
    """
    Port List Excel을 읽어 'Port' 컬럼 값(PORT/PWR/GND) 기준으로 행을 분류해서
    구조화된 딕셔너리 리스트로 반환한다. (2026-08 확정: PORT=I/O, PWR=전원, GND=접지)

    이후 단계(.pdt/.udc/pg_pin 조립 등)에서 이 결과를 그대로 재사용할 수 있도록
    GUI에 의존하지 않는 순수 함수로 작성. 값이 없는 컬럼은 빈 문자열로 채운다.

    Returns:
        {
            "sheet_name": str | None,
            "port_rows": [ {컬럼명: 값, ...}, ... ],   # Port == "PORT" (I/O)
            "pwr_rows":  [ {...}, ... ],                # Port == "PWR"
            "gnd_rows":  [ {...}, ... ],                # Port == "GND"
            "unclassified_rows": [ {...}, ... ],        # Port 값이 PORT/PWR/GND 중 아무것도 아닌 행
            "errors": [str, ...],
        }
    """
    result = {
        "sheet_name": None,
        "port_rows": [],
        "pwr_rows": [],
        "gnd_rows": [],
        "unclassified_rows": [],
        "errors": [],
    }

    sheet_name = find_port_list_sheet_name(file_path)
    result["sheet_name"] = sheet_name
    if sheet_name is None:
        result["errors"].append("No sheet found with a name containing 'Port list'.")
        return result

    rows = _load_sheet_rows(file_path, sheet_name)
    header_row, column_map = _find_header_row(rows)

    missing_required = [c for c in PORT_LIST_REQUIRED_COLUMNS if c not in column_map]
    if missing_required:
        result["errors"].append(
            "Missing required column(s): " + ", ".join(missing_required)
        )
        return result

    def _value_at(row: list, col_name: str):
        col_idx = column_map.get(col_name)
        if col_idx is None:
            return ""
        raw = row[col_idx - 1] if col_idx - 1 < len(row) else None
        return "" if raw is None else raw

    for row_idx, row in enumerate(rows[header_row:], start=header_row + 1):
        required_values = [_value_at(row, c) for c in PORT_LIST_REQUIRED_COLUMNS]
        if all(v is None or str(v).strip() == "" for v in required_values):
            continue  # 완전히 빈 행은 데이터 끝으로 간주

        record = {col: _value_at(row, col) for col in _ALL_ROW_COLUMNS}
        record["_row"] = row_idx

        port_type = str(record.get("Port", "")).strip().upper()
        if port_type == PORT_TYPE_IO:
            result["port_rows"].append(record)
        elif port_type == PORT_TYPE_PWR:
            result["pwr_rows"].append(record)
        elif port_type == PORT_TYPE_GND:
            result["gnd_rows"].append(record)
        else:
            result["unclassified_rows"].append(record)
            result["errors"].append(
                f"Row {row_idx}: unrecognized Port value '{record.get('Port', '')}' "
                "(expected PORT / PWR / GND)"
            )

    return result


def list_port_bit_values(file_path: str) -> list[int]:
    """
    Port List에서 'Port' 컬럼 값이 PORT(I/O)인 행들의 'Bits' 값을 정수로 모아
    중복 제거 후 오름차순으로 정렬해 반환한다 (Step4 block3의 type_bus 생성용).

    Step1 Validate에서 이미 Bits가 정수인지 검사하지만, 방어적으로 여기서도
    정수로 변환 안 되는 값은 조용히 건너뛴다(예외를 던지지 않음).
    """
    result = read_port_list_rows(file_path)
    values: set[int] = set()
    for row in result["port_rows"]:
        bits = row.get("Bits", "")
        if _is_valid_int(bits):
            values.add(_to_int(bits))
    return sorted(values)


def list_power_ground_pins(file_path: str) -> dict:
    """
    Port List에서 Port=="PWR" / "GND"인 행들을 각각 파일에 나온 순서 그대로
    {"pin_name": str, "voltage_value": float | None, "related_pins": [str, ...]}
    리스트로 반환한다 (Step4 block4의 pg_pin, block5의
    {process_prefix}_pdt_pin(...) 생성용).

    - voltage_value는 'Volts' 컬럼에서 단위를 뺀 숫자만 파싱한 값이며, 파싱이 안
      되면 None(예외를 던지지 않고 결측 처리로 이어짐).
    - related_pins(2026-08 추가): Port List 전체(타입 무관)를 훑어서, 이 핀 이름을
      'Related Power'(PWR인 경우) 또는 'Related ground'(GND인 경우) 컬럼 값으로
      쓰고 있는 다른 행들의 Pin name을 파일에 나온 순서대로 모은 것. PWR pin은
      Related Power 컬럼만 보고, GND pin은 Related ground 컬럼만 본다(서로 교차해서
      보지 않음).

    Returns:
        {"pwr_pins": [{...}, ...], "gnd_pins": [{...}, ...]}
    """
    result = read_port_list_rows(file_path)
    all_rows = (
        result["port_rows"] + result["pwr_rows"] + result["gnd_rows"] + result["unclassified_rows"]
    )
    all_rows.sort(key=lambda r: r.get("_row", 0))

    def _to_pin_list(rows: list[dict], related_column: str) -> list[dict]:
        pins = []
        for row in rows:
            pin_name = str(row.get("Pin name", "")).strip()
            if not pin_name:
                continue
            related_pins = [
                str(other.get("Pin name", "")).strip()
                for other in all_rows
                if str(other.get(related_column, "")).strip() == pin_name
                and str(other.get("Pin name", "")).strip()
            ]
            pins.append({
                "pin_name": pin_name,
                "voltage_value": parse_volts_value(row.get("Volts")),
                "related_pins": related_pins,
            })
        return pins

    return {
        "pwr_pins": _to_pin_list(result["pwr_rows"], "Related Power"),
        "gnd_pins": _to_pin_list(result["gnd_rows"], "Related ground"),
    }


def list_port_pins_detailed(file_path: str) -> list[dict]:
    """
    Port List에서 Port=="PORT"인 행들을 파일에 나온 순서 그대로
    {"pin_name": str, "bits": int, "volts": float | None, "cap": float | None,
     "related_power": str, "related_ground": str, "related_pin": str, "io": str}
    리스트로 반환한다 (Step4 block5의 pin()/bus() 생성용).

    - bits는 Step1 Validate에서 이미 정수인지 검사하지만, 방어적으로 여기서도 정수로
      변환 안 되면 해당 행은 건너뛴다(예외를 던지지 않음).
    - volts는 단위(V 등)가 붙어있어도 숫자만 파싱한다. 파싱 안 되면 None.
    - cap은 숫자로 바로 파싱을 시도하고, 안 되면 None.
    - related_power/related_ground/related_pin/io는 빈 값이면 빈 문자열 그대로
      반환(결측 표시는 block5_writer.py에서 처리).
    """
    result = read_port_list_rows(file_path)
    pins: list[dict] = []
    for row in result["port_rows"]:
        pin_name = str(row.get("Pin name", "")).strip()
        if not pin_name:
            continue
        bits_raw = row.get("Bits", "")
        if not _is_valid_int(bits_raw):
            continue
        cap_raw = row.get("Cap", "")
        try:
            cap_value = float(str(cap_raw).strip())
        except (TypeError, ValueError):
            cap_value = None

        pins.append({
            "pin_name": pin_name,
            "bits": _to_int(bits_raw),
            "volts": parse_volts_value(row.get("Volts")),
            "cap": cap_value,
            "related_power": str(row.get("Related Power", "")).strip(),
            "related_ground": str(row.get("Related ground", "")).strip(),
            "related_pin": str(row.get("Related Pin", "")).strip(),
            "io": str(row.get("I/O", "")).strip(),
        })
    return pins


def list_all_pin_names(file_path: str) -> list[str]:
    """Port List의 모든 행에서 'Pin name' 값 목록을 반환 (Port 타입 무관)."""
    sheet_name = find_port_list_sheet_name(file_path)
    if sheet_name is None:
        return []

    rows = _load_sheet_rows(file_path, sheet_name)
    header_row, column_map = _find_header_row(rows)
    if "Pin name" not in column_map:
        return []

    pin_col = column_map["Pin name"]
    result = []
    for row in rows[header_row:]:
        pin_val = row[pin_col - 1] if pin_col - 1 < len(row) else None
        if pin_val is not None:
            name = str(pin_val).strip()
            if name:
                result.append(name)
    return result