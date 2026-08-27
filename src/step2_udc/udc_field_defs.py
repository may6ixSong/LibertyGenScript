"""
udc_field_defs.py

Step 2 (UDC Settings) 화면의 필드 정의 (2026-08 전면 재설계 -> 2026-08 2차 재설계).

1차 재설계에서는 PDK 폴더와 DBS 폴더의 파일명을 voltage+temperature로 자동 페어링해서
"짝이 맞는 파일 개수 = 만들 liberty 개수"로 삼았다. 그러나 실제로는 PDK 폴더에 훨씬
많은 종류의 PDK 파일이 들어있고 DBS 파일은 그보다 적기 때문에, 자동 페어링만으로는
어떤 조합의 liberty를 만들지 결정할 수 없다는 것이 확인됐다 (2026-08 2차 재설계).

그래서 이제는 **liberty 파일 하나당 setting 1개**를 사용자가 직접 추가한다:
  - corner        : ffpg / fsg / sfg / sspg / tt 중 선택
  - beol inform   : nominal / sigcmin / sigrcmax / sigcmax 중 선택
  - voltage       : 숫자 입력 (화면에 V 단위 표시)
  - temperature   : 숫자 입력 (화면에 ℃ 단위 표시)
  - condition     : bst / wst / tiv 중 선택
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
CORNER_OPTIONS = ["ffpg", "fsg", "sfg", "sspg", "tt"]
BEOL_OPTIONS = ["nominal", "sigcmin", "sigrcmax", "sigcmax"]

# liberty 1개당 bst/wst/tiv 중 하나를 자유롭게 선택 -> Step3 Voltage Map의 어느 그룹
# (BST/WST/TIV)에서 voltage_map 값을 가져올지 결정한다. PDK 파일명의 min/max와는 무관.
CONDITION_OPTIONS = ["bst", "wst", "tiv"]

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
    (ENTRY_CONDITION_KEY, "Condition", "select", CONDITION_OPTIONS),
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
# 파일명 토큰 규칙 (2026-08 2차 재설계 확정)
#
#   PDK/DK:
#     {공정명}lpv_[{??}_{??}_{??}_{??}_c{??}]_{corner}_{beol}_{min|max}_0p{volt}v_{temp}c_[{??}...].lib*
#     예) cs17lpv_sc_d7p47t_flk_rvt_c90l14_ffpg_nominal_min_0p7500v_75c_lvf_dth.lib
#         └공정┘ └───── 있을 수도 없을 수도 ─────┘ └corner┘└beol┘└min┘└volt┘└temp┘└추가토큰┘
#     - 대괄호 구간은 파일마다 있을 수도 없을 수도 있어서 토큰 개수가 고정되지 않는다.
#       그래서 위치(index)로 자르지 않고, "min|max 다음에 0p...v, 그 다음에 ...c"라는
#       고정된 세 토큰 덩어리를 먼저 찾은 뒤 그 앞쪽에서 corner/beol을 읽는다.
#     - beol은 여러 토큰일 수도 있으므로 "corner 다음 ~ min|max 직전" 전체를 beol로 본다.
#     - **PDK 파일의 beol 토큰은 사용자가 고른 beol inform과 다를 확률이 매우 크다**
#       (2026-08 확인). 그래서 추천 매칭에서 beol은 필수 조건이 아니라 순위 가산점으로만
#       쓰고, 필수 조건은 corner + voltage + temperature 세 가지다.
#
#   DBS output:
#     {prefix}_0p{volt}v_{temp}c.mt0
#     예) ffpg_nominal_0p7500v_75c.mt0
#
#   - 0p{digits}v -> 0.{digits} (0p920v -> 0.920, 0p7500v -> 0.7500). 자릿수가 3자리든
#     4자리든 같은 전압이면(0.920 == 0.9200) 같은 것으로 봐야 하므로 부동소수점 대신
#     Decimal로 정확히 비교한다.
#   - temperature: m{n} -> -n, m 없으면 그대로 양수 (m40 -> -40, 75 -> 75)
# ---------------------------------------------------------------------------
_VOLTAGE_TOKEN_PATTERN = re.compile(r"^0p(?P<digits>\d{3,4})v$", re.IGNORECASE)
_TEMPERATURE_TOKEN_PATTERN = re.compile(r"^(?P<temp>m?\d+)c$", re.IGNORECASE)
_MINMAX_TOKENS = ("min", "max")

# 추천 순위: 낮을수록 먼저 보여준다.
MATCH_EXACT = 0  # corner/voltage/temperature + beol 까지 전부 일치
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


def _split_stem_tokens(stem: str) -> list[str]:
    return stem.split("_")


def parse_pdk_filename(filename: str) -> dict | None:
    """
    PDK/DK 파일명을 토큰으로 분해한다.

    Returns:
        {
            "tokens": [...],           # 확장자를 뗀 stem을 '_'로 자른 것
            "minmax_index": int,       # min|max 토큰의 위치
            "minmax": "min" | "max",
            "voltage": Decimal,
            "temperature": int,
        }
        위 고정 3토큰 덩어리(min|max, 0p..v, ..c)를 못 찾으면 None.
    """
    from step1_setup.field_defs import strip_pdk_extension

    stem = strip_pdk_extension(filename)
    if stem is None:
        return None
    tokens = _split_stem_tokens(stem)

    for index, token in enumerate(tokens):
        if token.lower() not in _MINMAX_TOKENS:
            continue
        if index + 2 >= len(tokens):
            continue
        volt_match = _VOLTAGE_TOKEN_PATTERN.match(tokens[index + 1])
        temp_match = _TEMPERATURE_TOKEN_PATTERN.match(tokens[index + 2])
        if not volt_match or not temp_match:
            continue
        return {
            "tokens": tokens,
            "minmax_index": index,
            "minmax": token.lower(),
            "voltage": _voltage_from_digits(volt_match.group("digits")),
            "temperature": _parse_temperature_token(temp_match.group("temp")),
        }
    return None


def parse_dbs_filename(filename: str) -> dict | None:
    """
    DBS output(.mt0) 파일명을 토큰으로 분해해서
    {"tokens": [...], "voltage": Decimal, "temperature": int}를 반환. 못 찾으면 None.
    """
    from step1_setup.field_defs import DBS_FILE_EXTENSION

    if not filename.lower().endswith(DBS_FILE_EXTENSION):
        return None
    stem = filename[: -len(DBS_FILE_EXTENSION)]
    tokens = _split_stem_tokens(stem)

    for index in range(len(tokens) - 1):
        volt_match = _VOLTAGE_TOKEN_PATTERN.match(tokens[index])
        temp_match = _TEMPERATURE_TOKEN_PATTERN.match(tokens[index + 1])
        if not volt_match or not temp_match:
            continue
        return {
            "tokens": tokens,
            "voltage": _voltage_from_digits(volt_match.group("digits")),
            "temperature": _parse_temperature_token(temp_match.group("temp")),
        }
    return None


def _corner_index(tokens: list[str], corner: str, before_index: int | None = None) -> int:
    """tokens 안에서 corner 토큰의 위치. before_index가 주어지면 그 앞에서만 찾는다."""
    limit = len(tokens) if before_index is None else before_index
    target = corner.lower()
    for index in range(limit - 1, -1, -1):
        if tokens[index].lower() == target:
            return index
    return -1


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
        MATCH_BEOL_DIFFERS - corner/voltage/temperature는 일치, beol만 다름
        None               - 추천 대상 아님
    """
    parsed = parse_pdk_filename(filename)
    if parsed is None:
        return None

    corner = str(entry.get(ENTRY_CORNER_KEY, "")).strip()
    if not corner:
        return None

    voltage = parse_voltage_input(entry.get(ENTRY_VOLTAGE_KEY, ""))
    temperature = parse_temperature_input(entry.get(ENTRY_TEMPERATURE_KEY, ""))
    if not _values_match(parsed, voltage, temperature):
        return None

    tokens = parsed["tokens"]
    minmax_index = parsed["minmax_index"]
    corner_index = _corner_index(tokens, corner, minmax_index)
    if corner_index < 0:
        return None

    beol_in_file = "_".join(tokens[corner_index + 1: minmax_index]).lower()
    beol_selected = str(entry.get(ENTRY_BEOL_KEY, "")).strip().lower()
    if beol_selected and beol_in_file == beol_selected:
        return MATCH_EXACT
    return MATCH_BEOL_DIFFERS


def match_dbs_file(filename: str, entry: dict) -> int | None:
    """
    DBS output 파일 하나가 이 setting(entry)에 맞는지 판정한다. PDK와 달리 min/max
    토큰이 없으므로, corner 토큰이 파일명 어디엔가 있고 voltage/temperature가 일치하면
    후보로 본다. beol까지 일치하면 MATCH_EXACT.
    """
    parsed = parse_dbs_filename(filename)
    if parsed is None:
        return None

    corner = str(entry.get(ENTRY_CORNER_KEY, "")).strip()
    if not corner:
        return None

    voltage = parse_voltage_input(entry.get(ENTRY_VOLTAGE_KEY, ""))
    temperature = parse_temperature_input(entry.get(ENTRY_TEMPERATURE_KEY, ""))
    if not _values_match(parsed, voltage, temperature):
        return None

    tokens = parsed["tokens"]
    corner_index = _corner_index(tokens, corner)
    if corner_index < 0:
        return None

    beol_selected = str(entry.get(ENTRY_BEOL_KEY, "")).strip().lower()
    remaining = [token.lower() for token in tokens[corner_index + 1:]]
    if beol_selected and beol_selected in remaining:
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
