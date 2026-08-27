"""
constants_field_defs.py

Constants(Step 3) 정의 + Voltage Map(2026-08 Step 2로 이동) 데이터 모델.

기존 `DKgen_ver`/`portdesc_make`/`mt_make`/`mt_cnt_ref_output`/`mt_cnt_ref_input` 필드는
liberty 파일 내용에 쓰이지 않는 것으로 확인되어 전부 삭제했다 (원본 스크립트에서
주석/로그 전용이거나 별도 문서 생성/검증 임계값 용도였음).

Voltage Map (2026-08 사용자 정의 condition 재설계):
  예전에는 `BST`/`WST`/`TIV` **세 그룹으로 고정**되어 있었지만, 이제는 사용자가 voltage
  condition을 원하는 만큼 추가/삭제하고 이름도 직접 정한다 (config에 아무것도 없을 때만
  기본값으로 BST/WST/TIV 세 개가 만들어진다). 화면은 Step 3이 아니라 **Step 2 왼쪽 열**
  (Common Fields 아래)에 있고, Step 2의 각 liberty setting은 여기서 정의한 condition
  중 하나를 골라 그 값으로 voltage_map을 쓴다.

  condition 하나 = {"id": 화면/저장에서 행을 구분하는 용도, "name": 사용자가 정한 이름,
                    "values": {"type1": 값, "type2": 값, ...}}

Power Type 정책은 기존 그대로다: Power Type 개수는 2~3개로 사용자가 조절 가능(기본 3),
Power Type별 대표 전압(0.8V/2.2V/1.8V)은 block4에서 Port List Volts 값을 Power Type에
매칭시키는 고정 임계값으로도 쓰인다 (settings_validator/liberty_assembler/
block4_writer 참고). Power Type별 voltage name(리버티 voltage_map/pg_pin에 쓰일 이름)도
condition 구분 없이 Power Type마다 하나씩만 존재한다.
"""

from __future__ import annotations

import uuid

# ---------------------------------------------------------------------------
# 단순 스칼라 상수: (key, label, kind, default)
#   kind: "text"         - 자유 입력
#         "pdk_dropdown" - PDK Folder 안에서 Step2 페어링에 성공한 PDK 파일 중 하나를
#                          고르는 드롭다운 (settings_view에서 화면을 열 때마다 채움)
# ---------------------------------------------------------------------------
SCALAR_CONSTANT_DEFS = [
    ("class", "class", "text", "analog"),
    # process_prefix: liberty의 벤더 커스텀 attribute 접두어.
    ("process_prefix", "process_prefix", "text", "sec"),
    # output_prefix: liberty 출력 파일명에 쓰임
    # ({output_prefix}lpv_{cell_name}_{DBS 파일명에서 .mt0 뺀 것}.lib)
    ("output_prefix", "output_prefix", "text", ""),
    # 2026-08 추가 (block3): lu_table_template의 index_1/index_2 값을 PDK/DK 파일에서
    # 그대로 복사해오기 위해 필요한 두 이름. PDK/DK 파일 안에서 "cell (DFF명)" 선언을
    # 먼저 찾고, 그 다음부터 "LUT Table"명이 처음 등장하는 cell_rise/cell_fall
    # 블록의 index_1/index_2 줄을 그대로 복사한다.
    #
    # primitive_cell_name: 2026-08 화면 라벨이 "Primitive Cell Name" -> "LUT Table"로
    # 바뀌었다. 저장된 config(step3_settings.json)와의 호환을 위해 내부 key 이름은
    # 그대로 두고 라벨만 바꾼다.
    ("dff_cell_name", "DFF Cell Name", "text", ""),
    ("primitive_cell_name", "LUT Table", "text", ""),
    # 2026-08 추가 (block3): lu_table_template은 pair마다 각자의 PDK에서 찾는 게 아니라,
    # 여기서 고른 "worst case" PDK 하나에서만 찾아서 생성하는 모든 liberty에 동일하게
    # 쓴다. 드롭다운 후보는 Step2에서 DBS output과 1:1 pair가 성립한 PDK 파일들뿐이다.
    # block5의 max_capacitance 값(index_2의 마지막 값)도 이 파일에서 온다.
    ("worst_case_pdk", "Worst case primitive liberty", "pdk_dropdown", ""),
]

# ---------------------------------------------------------------------------
# Voltage Map: 사용자 정의 voltage condition x Power Type1..N
# ---------------------------------------------------------------------------
POWER_TYPE_COUNT_KEY = "power_type_count"
POWER_TYPE_COUNT_MIN = 2
POWER_TYPE_COUNT_MAX = 3
POWER_TYPE_COUNT_DEFAULT = 3

VOLTAGE_CONDITIONS_KEY = "conditions"
CONDITION_ID_KEY = "id"
CONDITION_NAME_KEY = "name"
CONDITION_VALUES_KEY = "values"

# config에 voltage condition이 하나도 없을 때만 쓰이는 기본 이름 3개
# (2026-08 이전에는 이 세 개가 코드에 고정되어 있었다).
DEFAULT_CONDITION_NAMES = ["BST", "WST", "TIV"]

# 2026-08 이전 config(step3_settings.json)의 값 key 접두어. 지금은 저장하지 않고,
# 예전 config를 읽어 condition 목록으로 옮길 때(마이그레이션)만 쓴다.
LEGACY_VOLTAGE_MAP_GROUPS = ["BST", "WST", "TIV"]
LEGACY_VOLTAGE_MAP_VALUES_KEY = "values"

# Power Type별 대표(TIV) 전압값. (a) condition x Power Type 칸의 초기 기본값,
# (b) block4에서 Port List Volts 값을 Power Type에 매칭시키는 고정 임계값, 두 곳에
# 쓰인다. 실제 표의 값은 사용자가 자유롭게 조정할 수 있고, 이 값이 바뀌어도 (b)의
# 매칭 기준은 이 대표값 그대로 고정이다.
POWER_TYPE_DEFAULT_VOLTAGE = {1: 0.8, 2: 2.2, 3: 1.8}


def power_type_label(type_index: int) -> str:
    return f"Power Type{type_index} ({POWER_TYPE_DEFAULT_VOLTAGE[type_index]}V)"


def condition_value_key(type_index: int) -> str:
    """condition 하나 안에서 Power Type 하나의 전압 값 key ('type1', 'type2', ...)."""
    return f"type{type_index}"


def legacy_voltage_map_value_key(group: str, type_index: int) -> str:
    """2026-08 이전 config의 값 key ('bst_type1' 등) - 마이그레이션 전용."""
    return f"{group.lower()}_type{type_index}"


def voltage_map_name_key(type_index: int) -> str:
    """Power Type마다 하나뿐인 voltage name 필드 key (condition 무관)."""
    return f"power_type{type_index}_name"


def new_condition(name: str = "", values: dict | None = None) -> dict:
    """
    voltage condition 하나. 값은 항상 POWER_TYPE_COUNT_MAX(=3)개를 들고 있는다 -
    Power Type 개수를 3->2->3으로 바꿔도 이미 입력해 둔 Power Type3 값이 날아가지
    않도록 하기 위해서다(화면에 보이고 검증되는 건 그 시점의 개수만큼뿐).
    """
    base = {
        condition_value_key(i): str(POWER_TYPE_DEFAULT_VOLTAGE[i])
        for i in range(1, POWER_TYPE_COUNT_MAX + 1)
    }
    if values:
        for key, value in values.items():
            if key in base and value is not None:
                base[key] = str(value)
    return {
        CONDITION_ID_KEY: uuid.uuid4().hex,
        CONDITION_NAME_KEY: str(name),
        CONDITION_VALUES_KEY: base,
    }


def default_conditions() -> list[dict]:
    """config에 아무것도 없을 때 쓰는 기본 condition 3개 (BST / WST / TIV)."""
    return [new_condition(name) for name in DEFAULT_CONDITION_NAMES]


def condition_names(voltage_map: dict) -> list[str]:
    """Voltage Map에 정의된 condition 이름 목록 (빈 이름은 제외, 입력 순서 유지)."""
    result = []
    for condition in voltage_map.get(VOLTAGE_CONDITIONS_KEY, []) or []:
        name = str(condition.get(CONDITION_NAME_KEY, "")).strip()
        if name:
            result.append(name)
    return result


def find_condition(voltage_map: dict, name: str) -> dict | None:
    """
    이름으로 condition 하나를 찾는다. 대소문자는 무시한다 - 예전 config에는
    'bst'처럼 소문자로 저장돼 있고 지금 기본 이름은 'BST'이기 때문.
    """
    target = str(name or "").strip().lower()
    if not target:
        return None
    for condition in voltage_map.get(VOLTAGE_CONDITIONS_KEY, []) or []:
        if str(condition.get(CONDITION_NAME_KEY, "")).strip().lower() == target:
            return condition
    return None


def power_type_count_of(voltage_map: dict) -> int:
    """저장된 Power Type 개수를 허용 범위로 보정해서 반환."""
    try:
        count = int(voltage_map.get(POWER_TYPE_COUNT_KEY, POWER_TYPE_COUNT_DEFAULT))
    except (TypeError, ValueError):
        count = POWER_TYPE_COUNT_DEFAULT
    return max(POWER_TYPE_COUNT_MIN, min(POWER_TYPE_COUNT_MAX, count))


VOLTAGE_MAP_NAME_FIELD_DEFS = [
    (voltage_map_name_key(i), i) for i in range(1, POWER_TYPE_COUNT_MAX + 1)
]
