"""
udc_field_defs.py

Step 2 (UDC Settings) 화면의 필드 정의 (2026-08 전면 재설계).

더 이상 UDC 항목을 사용자가 하나하나 수동으로 만들지 않는다:
  - 공통 필드(area/width/height/static_current/cell_name/MC·HDA·OUT Timing State)는
    이번에 생성하는 모든 조합에 1번만 입력한다.
  - PDK Folder의 확장자가 .lib로 시작하는 파일들(.lib, .lib_css_tn 등)과 DBS Simulation
    Folder의 .mt0 파일들은 파일명에서 파싱한 voltage+temperature 조합이 일치하는 것끼리
    자동으로 pair(=liberty 1개 생성 대상)로 묶인다. 이 모듈은 그 파싱/페어링 로직을
    담당한다.
"""

from __future__ import annotations

import re
from decimal import Decimal

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

# pair 1개당 bst/wst/tiv 중 하나를 자유롭게 선택 -> Step3 Constants의 단일 Voltage
# Condition 테이블(9칸) 중 어느 3칸(High/Mid/Low)을 쓸지 결정 (2026-08 확정, PDK
# 파일명의 min/max와는 무관하며 제한 없이 자유 선택)
VOLTAGE_CONDITION_OPTIONS = ["bst", "wst", "tiv"]


def all_common_field_keys() -> list[str]:
    return [key for key, _, _ in COMMON_FIELD_DEFS]


# ---------------------------------------------------------------------------
# 파일명 파싱 (2026-08 확정, 2026-08 수정: voltage 자릿수 3~4자리 모두 허용,
# 2026-08 수정: PDK 파일명에 temperature 뒤로 추가 접미사가 붙어도 허용)
#   PDK/DK : {prefix}_{min|max}_0p{voltage}v_{temperature}c{추가 접미사?}.lib(_css_tn)
#            예: cs17lpv_sc_min_0p920v_m40c.lib (3자리) / ..._0p9200v_... (4자리) /
#            cs17lpv_sc_..._ffpg_nominal_min_0p7500v_75c_lvf_dth.lib (뒤에 _lvf_dth
#            같은 추가 토큰이 붙는 경우도 있음)
#   DBS    : {prefix}_0p{voltage}v_{temperature}c.mt0
#            예: cs17lpv_sc_0p920v_m40c.mt0 / cs17lpv_sc_0p9200v_m40c.mt0
#   - 0p{digits}v -> 0.{digits} (0p920v -> 0.920, 0p9200v -> 0.9200) - 자릿수가 3자리든
#     4자리든 같은 전압을 나타내면(0.920 == 0.9200) 같은 pair로 인정해야 하므로,
#     부동소수점 대신 Decimal로 정확히 비교한다.
#   - temperature: m{n} -> -n, m 없으면 그대로 양수 (m40 -> -40, 25 -> 25)
#   - {prefix}와 min/max 토큰은 매칭에 쓰이지 않음 - voltage+temperature 숫자값만
#     같으면 pair로 인정
# ---------------------------------------------------------------------------
_PDK_STEM_PATTERN = re.compile(
    r"^.+_(?:min|max)_0p(?P<volt>\d{3,4})v_(?P<temp>m?\d+)c(?:_.+)?$", re.IGNORECASE
)
_DBS_STEM_PATTERN = re.compile(
    r"^.+_0p(?P<volt>\d{3,4})v_(?P<temp>m?\d+)c$", re.IGNORECASE
)


def _strip_known_extension(filename: str, extensions: list[str]) -> str | None:
    for ext in sorted(extensions, key=len, reverse=True):
        if filename.lower().endswith(ext.lower()):
            return filename[: -len(ext)]
    return None


def _parse_temperature_token(token: str) -> int:
    if token.lower().startswith("m"):
        return -int(token[1:])
    return int(token)


def _voltage_from_digits(digits: str) -> Decimal:
    """'920' -> Decimal('0.920'), '9200' -> Decimal('0.9200') (== 0.920, 자릿수 무관하게 정확히 비교 가능)."""
    return Decimal(digits) / (Decimal(10) ** len(digits))


def parse_pdk_filename(filename: str) -> dict | None:
    """
    PDK/DK 파일명을 파싱해서 {"voltage": Decimal, "temperature": int}를 반환.
    명명 규칙에 맞지 않으면 None. voltage의 자릿수(3자리/4자리)는 매칭에 영향을 주지
    않는다 - Decimal로 정확한 수치 비교를 하므로 0.920과 0.9200은 같은 값으로 취급된다.
    """
    from step1_setup.field_defs import strip_pdk_extension

    stem = strip_pdk_extension(filename)
    if stem is None:
        return None
    match = _PDK_STEM_PATTERN.match(stem)
    if not match:
        return None
    voltage = _voltage_from_digits(match.group("volt"))
    temperature = _parse_temperature_token(match.group("temp"))
    return {"voltage": voltage, "temperature": temperature}


def parse_dbs_filename(filename: str) -> dict | None:
    """
    DBS output(.mt0) 파일명을 파싱해서 {"voltage": Decimal, "temperature": int}를 반환.
    명명 규칙에 맞지 않으면 None.
    """
    from step1_setup.field_defs import DBS_FILE_EXTENSION

    stem = _strip_known_extension(filename, [DBS_FILE_EXTENSION])
    if stem is None:
        return None
    match = _DBS_STEM_PATTERN.match(stem)
    if not match:
        return None
    voltage = _voltage_from_digits(match.group("volt"))
    temperature = _parse_temperature_token(match.group("temp"))
    return {"voltage": voltage, "temperature": temperature}


_NAMING_MISMATCH_REASON = "Filename does not match the expected naming convention."


def compute_pairs(pdk_files: list[str], dbs_files: list[str]) -> dict:
    """
    PDK/DK 파일 목록과 DBS output 파일 목록을 파일명에서 파싱한 voltage+temperature
    기준으로 자동 페어링한다.

    1:1이 안 되는 경우(짝이 아예 없거나, 여러 개가 동시에 매칭되는 경우)는 에러가
    아니라 unmatched 목록(warning)으로 분류되고 생성 대상에서 제외된다.

    Returns:
        {
            "pairs": [
                {"pdk_file": str, "dbs_file": str, "voltage": float, "temperature": int},
                ...
            ],
            "unmatched_pdk": [(filename, reason_str), ...],
            "unmatched_dbs": [(filename, reason_str), ...],
        }
    """
    pdk_by_key: dict[tuple[Decimal, int], list[str]] = {}
    unmatched_pdk: list[tuple[str, str]] = []
    for f in pdk_files:
        parsed = parse_pdk_filename(f)
        if parsed is None:
            unmatched_pdk.append((f, _NAMING_MISMATCH_REASON))
            continue
        key = (parsed["voltage"], parsed["temperature"])
        pdk_by_key.setdefault(key, []).append(f)

    dbs_by_key: dict[tuple[Decimal, int], list[str]] = {}
    unmatched_dbs: list[tuple[str, str]] = []
    for f in dbs_files:
        parsed = parse_dbs_filename(f)
        if parsed is None:
            unmatched_dbs.append((f, _NAMING_MISMATCH_REASON))
            continue
        key = (parsed["voltage"], parsed["temperature"])
        dbs_by_key.setdefault(key, []).append(f)

    pairs: list[dict] = []

    # Decimal은 자릿수(정밀도)가 달라도 값이 같으면 ==/hash가 같지만, 정렬 시 서로
    # 다른 타입과 섞이지 않도록 key를 (voltage, temperature) 그대로 정렬 기준으로 사용.
    for key in sorted(set(pdk_by_key) | set(dbs_by_key)):
        pdk_group = pdk_by_key.get(key, [])
        dbs_group = dbs_by_key.get(key, [])

        if len(pdk_group) == 1 and len(dbs_group) == 1:
            voltage, temperature = key
            pairs.append({
                "pdk_file": pdk_group[0],
                "dbs_file": dbs_group[0],
                "voltage": float(voltage),
                "temperature": temperature,
            })
        elif not pdk_group:
            reason = "No matching PDK/DK file (voltage/temperature) was found."
            unmatched_dbs += [(f, reason) for f in dbs_group]
        elif not dbs_group:
            reason = "No matching DBS output file (voltage/temperature) was found."
            unmatched_pdk += [(f, reason) for f in pdk_group]
        else:
            reason = "Multiple files share this voltage/temperature; a 1:1 pair could not be formed."
            unmatched_pdk += [(f, reason) for f in pdk_group]
            unmatched_dbs += [(f, reason) for f in dbs_group]

    pairs.sort(key=lambda p: p["pdk_file"])
    unmatched_pdk.sort(key=lambda item: item[0])
    unmatched_dbs.sort(key=lambda item: item[0])

    return {"pairs": pairs, "unmatched_pdk": unmatched_pdk, "unmatched_dbs": unmatched_dbs}
