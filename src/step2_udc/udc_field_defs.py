"""
udc_field_defs.py

Step 2 (UDC Settings) 화면의 필드 정의 (2026-08 전면 재설계 -> 2026-08 2차 재설계).

1차 재설계에서는 PDK 폴더와 DBS 폴더의 파일명을 voltage+temperature로 자동 페어링해서
"짝이 맞는 파일 개수 = 만들 liberty 개수"로 삼았다. 그러나 실제로는 PDK 폴더에 훨씬
많은 종류의 PDK 파일이 들어있고 DBS 파일은 그보다 적기 때문에, 자동 페어링만으로는
어떤 조합의 liberty를 만들지 결정할 수 없다는 것이 확인됐다 (2026-08 2차 재설계).

그래서 이제는 **liberty 파일 하나당 setting 1개**를 사용자가 직접 추가한다:
  - corner        : ffg / ffpg / fsg / sfg / ssg / sspg / tt 중 선택, 또는 "Custom input"을
                    골라 직접 입력 (2026-10 추가)
  - beol inform   : nominal / sigcmin / sigrcmin / sigrcmax / sigcmax / N/A 중 선택
                    (N/A = 파일명에 BEOL 토큰이 없음, 2026-10 추가)
  - voltage       : 숫자 입력 (화면에 V 단위 표시)
  - temperature   : 숫자 입력 (화면에 ℃ 단위 표시)
  - condition     : Voltage Map에 정의된 voltage condition 중 선택 (이름은 사용자 정의)
  - PDK file      : Step1에서 인식된 모든 PDK 파일 중 선택
  - DBS file      : PDK를 고르면 자동으로 매핑, 없으면 직접 선택

공통 필드(area/width/height/static_current/cell_name/MC·HDA·OUT Timing State)는 1차
재설계 그대로 - 이번에 생성하는 모든 조합에 1번만 입력한다.

이 모듈은 위 필드 정의와, "사용자가 입력한 setting -> 그에 맞는 PDK/DBS 파일 추천"
매칭 로직을 담당한다.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation

# ---------------------------------------------------------------------------
# 공통 필드: (key, label, kind)
#   kind: "text" | "number" | "dropdown"
# ---------------------------------------------------------------------------
COMMON_FIELD_DEFS = [
    ("area", "Area", "number"),
    ("width", "Width", "number"),
    ("height", "Height", "number"),
    ("static_current", "Static Current", "number"),
    ("cell_name", "Cell Name", "text"),
    ("mc_timing_state", "MC Timing State", "dropdown"),
    ("hda_timing_state", "HDA Timing State", "dropdown"),
    ("out_timing_state", "OUT Timing State", "dropdown"),
]

TIMING_STATE_OPTIONS = ["rising", "falling"]

# ---------------------------------------------------------------------------
# liberty 1개당 setting 필드 (2026-08 2차 재설계)
# ---------------------------------------------------------------------------
CORNER_OPTIONS = ["ffg", "ffpg", "fsg", "sfg", "ssg", "sspg", "tt"]
# Corner 드롭다운의 "직접 입력" 항목 (2026-10 추가). 이 항목은 저장되는 값이 아니라
# 화면 전용 표시이고, 고르면 옆에 입력칸이 나타나 사용자가 적은 문자열 자체가 corner
# 값으로 저장된다. 그래서 CORNER_OPTIONS에 없는 corner 값 = 직접 입력한 값이다.
CORNER_CUSTOM_LABEL = "Custom input"
# 직접 입력한 corner는 파일명 토큰으로 그대로 검색되므로 영문/숫자/'-'만 허용한다
# ('_'는 파일명 토큰 구분자라 쓸 수 없음).
CORNER_CUSTOM_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")

# N/A (2026-10 추가): PDK/DBS 파일명에 BEOL 토큰 자체가 없는 경우. 이때는 BEOL을 추천
# 매칭에서 전혀 고려하지 않고(corner/voltage/temperature만 보고 전부 MATCH_EXACT),
# operating_conditions 이름 등 BEOL을 이어 붙이는 곳에서도 빠진다.
BEOL_NA = "N/A"
BEOL_OPTIONS = ["nominal", "sigcmin", "sigrcmin", "sigrcmax", "sigcmax", BEOL_NA]


def is_beol_na(value) -> bool:
    return str(value or "").strip().upper() == BEOL_NA


def join_corner_beol(corner: str, beol: str) -> str:
    """'{corner}_{beol}' - beol이 N/A(또는 빈 값)이면 corner만."""
    beol = str(beol or "").strip()
    if not beol or is_beol_na(beol):
        return corner
    return f"{corner}_{beol}"

# liberty 1개당 voltage condition 하나를 고른다 -> Voltage Map(같은 화면 왼쪽 열)의 어느
# condition에서 voltage_map 값을 가져올지 결정한다. PDK 파일명의 min/max와는 무관.
#
# 2026-08 사용자 정의 condition 재설계: 예전에는 bst/wst/tiv로 고정된 목록이었지만,
# 이제 선택지는 사용자가 Voltage Map에 만들어 둔 condition 이름들이다(코드에 고정된
# 목록이 없다). 저장되는 값도 그 이름 문자열이며, 예전 config의 'bst'/'wst'/'tiv'는
# 기본 condition 이름 'BST'/'WST'/'TIV'와 대소문자만 다르므로 그대로 이어서 쓸 수 있다
# (udc_view가 콤보를 채울 때 대소문자 무시로 매칭해서 현재 이름으로 정규화한다).

ENTRY_CORNER_KEY = "corner"
ENTRY_BEOL_KEY = "beol_inform"
ENTRY_VOLTAGE_KEY = "voltage"
ENTRY_TEMPERATURE_KEY = "temperature"
ENTRY_CONDITION_KEY = "condition"
ENTRY_PDK_KEY = "pdk_file"
ENTRY_DBS_KEY = "dbs_file"
ENTRY_ID_KEY = "id"

# (key, 화면 라벨, kind, 부가정보)
#   kind "select" -> 부가정보는 선택지 목록
#   kind "number" -> 부가정보는 입력칸 오른쪽에 붙는 단위 표기(postfix)
ENTRY_FIELD_DEFS = [
    (ENTRY_CORNER_KEY, "Corner", "select", CORNER_OPTIONS),
    (ENTRY_BEOL_KEY, "BEOL Inform", "select", BEOL_OPTIONS),
    (ENTRY_VOLTAGE_KEY, "Voltage", "number", "V"),
    (ENTRY_TEMPERATURE_KEY, "Temperature", "number", "℃"),
    # "condition_select": 선택지가 코드에 없고 Voltage Map에서 온다 (udc_view가 채움)
    (ENTRY_CONDITION_KEY, "Condition", "condition_select", None),
]

ENTRY_SELECT_FIELD_KEYS = [ENTRY_CORNER_KEY, ENTRY_BEOL_KEY, ENTRY_CONDITION_KEY]
ENTRY_NUMBER_FIELD_KEYS = [ENTRY_VOLTAGE_KEY, ENTRY_TEMPERATURE_KEY]


def all_common_field_keys() -> list[str]:
    return [key for key, _, _ in COMMON_FIELD_DEFS]


def new_entry() -> dict:
    """빈 liberty setting 1개. id는 화면/저장에서 행을 구분하는 용도로만 쓴다."""
    return {
        ENTRY_ID_KEY: uuid.uuid4().hex,
        ENTRY_CORNER_KEY: "",
        ENTRY_BEOL_KEY: "",
        ENTRY_VOLTAGE_KEY: "",
        ENTRY_TEMPERATURE_KEY: "",
        ENTRY_CONDITION_KEY: "",
        ENTRY_PDK_KEY: "",
        ENTRY_DBS_KEY: "",
    }


# ---------------------------------------------------------------------------
# 파일명 토큰 규칙 (2026-08 2차 재설계 확정 -> 2026-10 붙여쓴 형식 추가)
#
#   PDK/DK:
#     {공정명}lpv_[{??}_{??}_{??}_{??}_c{??}]_{corner}_{beol}_{min|max}_0p{volt}v_{temp}c_[{??}...].lib*
#     예) cs17lpv_sc_d7p47t_flk_rvt_c90l14_ffpg_nominal_min_0p7500v_75c_lvf_dth.lib
#         └공정┘ └───── 있을 수도 없을 수도 ─────┘ └corner┘└beol┘└min┘└volt┘└temp┘└추가토큰┘
#     - 대괄호 구간은 파일마다 있을 수도 없을 수도 있어서 토큰 개수가 고정되지 않는다.
#       그래서 위치(index)로 자르지 않고, "[min|max] 0p...v ...c"라는 덩어리를 먼저 찾은
#       뒤 그 앞쪽(prefix)에서 corner/beol을 읽는다.
#     - beol은 여러 토큰일 수도 있으므로 "corner 다음 ~ min|max 직전" 전체를 beol로 본다.
#       BEOL Inform이 N/A면 파일명에 beol 토큰이 아예 없다 (corner 바로 뒤가 min|max).
#     - **2026-10 추가**: corner/min|max/voltage/temperature 사이의 '_'는 있을 수도 없을
#       수도 있고, min|max 토큰 자체가 없을 수도 있다.
#       예) xxxxxxxx_ffg0p99v125c.lib  (corner=ffg, voltage=0.99, temperature=125)
#       그래서 '_' 단위로 토큰을 자르지 않고 stem 문자열에서 정규식으로 덩어리를 찾는다.
#     - **PDK 파일의 beol 토큰은 사용자가 고른 beol inform과 다를 확률이 매우 크다**
#       (2026-08 확인). 그래서 추천 매칭에서 beol은 필수 조건이 아니라 순위 가산점으로만
#       쓰고, 필수 조건은 corner + voltage + temperature 세 가지다.
#
#   DBS output:
#     {prefix}_0p{volt}v_{temp}c.mt0   (PDK와 마찬가지로 '_'가 없어도 인식)
#     예) ffpg_nominal_0p7500v_75c.mt0, ffg0p99v125c.mt0
#
#   - 0p{digits}v -> 0.{digits} (0p920v -> 0.920, 0p7500v -> 0.7500, 0p99v -> 0.99).
#     자릿수가 달라도 같은 전압이면(0.920 == 0.9200) 같은 것으로 봐야 하므로 부동소수점
#     대신 Decimal로 정확히 비교한다.
#   - temperature: m{n} -> -n, m 없으면 그대로 양수 (m40 -> -40, 75 -> 75)
# ---------------------------------------------------------------------------
# prefix(최단) + [_][min|max][_] 0p{digits}v [_] [m]{n}c + (끝 또는 '_')
_CONDITION_CHUNK_PATTERN = re.compile(
    r"^(?P<prefix>.*?)_?(?:(?P<minmax>min|max)_?)?"
    r"0p(?P<digits>\d+)v_?(?P<temp>m?\d+)c(?P<suffix>_.*)?$",
    re.IGNORECASE,
)

# 추천 순위: 낮을수록 먼저 보여준다.
MATCH_EXACT = 0  # corner/voltage/temperature + beol 까지 전부 일치 (beol N/A면 beol 무시)
MATCH_BEOL_DIFFERS = 1  # corner/voltage/temperature 일치, beol만 다름


def _voltage_from_digits(digits: str) -> Decimal:
    """'920' -> Decimal('0.920'), '7500' -> Decimal('0.7500') (자릿수 무관하게 정확 비교 가능)."""
    return Decimal(digits) / (Decimal(10) ** len(digits))


def _parse_temperature_token(token: str) -> int:
    if token.lower().startswith("m"):
        return -int(token[1:])
    return int(token)


def parse_voltage_input(text) -> Decimal | None:
    """사용자가 입력한 voltage 문자열 -> Decimal. 숫자가 아니면 None."""
    try:
        return Decimal(str(text).strip())
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def parse_temperature_input(text) -> int | None:
    """
    사용자가 입력한 temperature 문자열 -> int. 파일명 토큰은 정수 온도만 쓰므로
    '75.0'처럼 들어와도 정수로 떨어질 때만 인정한다.
    """
    value = str(text).strip()
    if not value:
        return None
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError, ArithmeticError):
        return None
    if number != number.to_integral_value():
        return None
    return int(number)


def format_voltage_token(voltage: Decimal | float | str, digits: int = 4) -> str:
    """0.72 -> '0p7200' (파일명에 쓰이는 표기, 기본 소수점 4자리)."""
    value = parse_voltage_input(voltage)
    if value is None:
        return ""
    scaled = int((value * (Decimal(10) ** digits)).to_integral_value())
    return f"0p{scaled:0{digits}d}v"


def format_temperature_token(temperature: int | str) -> str:
    """40 -> '40c', -40 -> 'm40c' (파일명에 쓰이는 표기)."""
    value = parse_temperature_input(temperature)
    if value is None:
        return ""
    return f"m{-value}c" if value < 0 else f"{value}c"


def _parse_condition_chunk(stem: str) -> dict | None:
    """
    stem에서 "[min|max] 0p..v ..c" 덩어리를 찾아
    {"prefix", "suffix", "minmax", "voltage", "temperature"}를 반환. 못 찾으면 None.
    prefix는 덩어리 앞부분(끝의 '_' 제외), suffix는 뒷부분(앞의 '_' 제외)이다.
    """
    match = _CONDITION_CHUNK_PATTERN.match(stem)
    if not match:
        return None
    return {
        "prefix": match.group("prefix"),
        "suffix": (match.group("suffix") or "")[1:],
        "minmax": (match.group("minmax") or "").lower(),
        "voltage": _voltage_from_digits(match.group("digits")),
        "temperature": _parse_temperature_token(match.group("temp")),
    }


def parse_pdk_filename(filename: str) -> dict | None:
    """
    PDK/DK 파일명에서 corner 앞쪽(prefix)과 min|max/voltage/temperature를 읽는다.
    '_' 구분자가 있든 없든(xxx_ffg_min_0p9900v_125c / xxx_ffg0p99v125c) 인식한다.

    Returns:
        {"prefix": str, "suffix": str, "minmax": "min"|"max"|"", "voltage": Decimal,
         "temperature": int}. voltage/temperature 덩어리를 못 찾으면 None.
    """
    from step1_setup.field_defs import strip_pdk_extension

    stem = strip_pdk_extension(filename)
    if stem is None:
        return None
    return _parse_condition_chunk(stem)


def parse_dbs_filename(filename: str) -> dict | None:
    """DBS output(.mt0) 파일명을 parse_pdk_filename과 같은 형식의 dict로. 못 찾으면 None."""
    from step1_setup.field_defs import DBS_FILE_EXTENSION

    if not filename.lower().endswith(DBS_FILE_EXTENSION):
        return None
    return _parse_condition_chunk(filename[: -len(DBS_FILE_EXTENSION)])


def _find_corner(text: str, corner: str) -> int:
    """
    text 안에서 '_' 경계로 구분된 corner의 (마지막) 끝 위치. 없으면 -1.
    corner 앞은 문자열 시작 또는 '_', 뒤는 문자열 끝 또는 '_'여야 한다
    ('ffg'가 'xffg'나 'ffgx' 안에서 잘못 잡히지 않도록).
    """
    text = text.lower()
    target = corner.lower()
    start = text.rfind(target)
    while start >= 0:
        end = start + len(target)
        if (start == 0 or text[start - 1] == "_") and (end == len(text) or text[end] == "_"):
            return end
        start = text.rfind(target, 0, start + len(target) - 1)
    return -1


def _entry_conditions(entry: dict):
    corner = str(entry.get(ENTRY_CORNER_KEY, "")).strip()
    voltage = parse_voltage_input(entry.get(ENTRY_VOLTAGE_KEY, ""))
    temperature = parse_temperature_input(entry.get(ENTRY_TEMPERATURE_KEY, ""))
    beol = str(entry.get(ENTRY_BEOL_KEY, "")).strip()
    return corner, voltage, temperature, beol


def _values_match(
    parsed: dict, voltage: Decimal | None, temperature: int | None,
) -> bool:
    if voltage is None or temperature is None:
        return False
    return parsed["voltage"] == voltage and parsed["temperature"] == temperature


def match_pdk_file(filename: str, entry: dict) -> int | None:
    """
    PDK 파일 하나가 이 setting(entry)에 맞는지 판정한다.

    Returns:
        MATCH_EXACT        - corner/voltage/temperature + beol까지 전부 일치
                             (BEOL Inform이 N/A면 beol은 보지 않고 바로 MATCH_EXACT)
        MATCH_BEOL_DIFFERS - corner/voltage/temperature는 일치, beol만 다름
        None               - 추천 대상 아님
    """
    parsed = parse_pdk_filename(filename)
    if parsed is None:
        return None

    corner, voltage, temperature, beol_selected = _entry_conditions(entry)
    if not corner or not _values_match(parsed, voltage, temperature):
        return None

    prefix = parsed["prefix"]
    corner_end = _find_corner(prefix, corner)
    if corner_end < 0:
        return None

    if is_beol_na(beol_selected):
        return MATCH_EXACT
    beol_in_file = prefix[corner_end:].strip("_").lower()
    if beol_selected and beol_in_file == beol_selected.lower():
        return MATCH_EXACT
    return MATCH_BEOL_DIFFERS


def match_dbs_file(filename: str, entry: dict) -> int | None:
    """
    DBS output 파일 하나가 이 setting(entry)에 맞는지 판정한다. corner가 파일명
    어디엔가('_' 경계로) 있고 voltage/temperature가 일치하면 후보로 본다. corner 뒤쪽에
    beol 토큰이 있으면 MATCH_EXACT (BEOL Inform이 N/A면 beol은 보지 않고 MATCH_EXACT).
    """
    parsed = parse_dbs_filename(filename)
    if parsed is None:
        return None

    corner, voltage, temperature, beol_selected = _entry_conditions(entry)
    if not corner or not _values_match(parsed, voltage, temperature):
        return None

    text = parsed["prefix"] + "_" + parsed["suffix"]
    corner_end = _find_corner(text, corner)
    if corner_end < 0:
        return None

    if is_beol_na(beol_selected):
        return MATCH_EXACT
    remaining = text[corner_end:].lower().split("_")
    if beol_selected and beol_selected.lower() in remaining:
        return MATCH_EXACT
    return MATCH_BEOL_DIFFERS


def _rank_matches(filenames: list[str], entry: dict, matcher) -> list[tuple[str, int]]:
    matches = []
    for filename in filenames:
        rank = matcher(filename, entry)
        if rank is not None:
            matches.append((filename, rank))
    matches.sort(key=lambda item: (item[1], item[0]))
    return matches


def recommend_pdk_files(pdk_files: list[str], entry: dict) -> list[tuple[str, int]]:
    """
    이 setting에 맞을 것으로 보이는 PDK 파일들을 추천 순위(MATCH_EXACT 먼저)대로 반환.
    화면에서는 이 목록을 드롭다운 맨 위로 올려 highlight한다.
    """
    return _rank_matches(pdk_files, entry, match_pdk_file)


def recommend_dbs_files(dbs_files: list[str], entry: dict) -> list[tuple[str, int]]:
    """이 setting에 맞을 것으로 보이는 DBS output 파일들을 추천 순위대로 반환."""
    return _rank_matches(dbs_files, entry, match_dbs_file)


def auto_select_dbs_file(dbs_files: list[str], entry: dict) -> str:
    """
    PDK를 고른 뒤 자동으로 엮어줄 DBS output 파일. 후보가 정확히 하나면 그 파일명을,
    후보가 없거나 여러 개면 빈 문자열을 반환한다(사용자가 직접 고르게 함).
    """
    matches = recommend_dbs_files(dbs_files, entry)
    if len(matches) == 1:
        return matches[0][0]
    exact = [name for name, rank in matches if rank == MATCH_EXACT]
    if len(exact) == 1:
        return exact[0]
    return ""
