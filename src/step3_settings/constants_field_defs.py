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

Power Type 정책 (2026-08 재설계 - 개수 무제한 + voltage(digital) 필드 추가):
  예전에는 Power Type 개수가 2~3개로 제한되고, 대표 전압(0.8V/2.2V/1.8V)이 코드에
  고정되어 block4의 매칭 임계값으로 그대로 쓰였다. 이제 **Power Type 개수는 최소 1개,
  최대 제한 없음**이고, Power Type마다 **name**(기존)뿐 아니라 **voltage (digital)**
  값도 사용자가 직접 입력한다(둘 다 condition 구분 없이 Power Type당 하나씩). 이
  voltage(digital) 값이 Port List Volts 값과의 매칭 임계값 역할을 대신한다:
    - block4 pg_pin의 voltage_name: 일치하면 그 Power Type의 name으로 치환
      (liberty_assembler.build_job의 voltage_name_thresholds, block4_writer 참고)
    - block5 pin()의 input_signal_level: 일치하면 **이 liberty가 선택한 voltage
      condition**의 같은 Power Type Type[N] 값으로 치환
      (input_signal_level_thresholds, block5_writer 참고)
  기존 config(voltage(digital) 필드가 없음)를 읽을 때는 Power Type1/2/3에 한해 예전
  고정값(0.8/2.2/1.8)을 그대로 seed해서, 사용자가 새 필드를 손대지 않으면 기존과 같은
  생성 결과가 나오도록 한다(settings_manager._default_voltage_map).
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
POWER_TYPE_COUNT_MIN = 1
# UI(QSpinBox)에 필요한 상한일 뿐 - 데이터 모델 자체는 이 값에 묶이지 않는다
# (2026-08: 예전의 고정 상한 3을 없애고 "사실상 무제한"으로 취급).
POWER_TYPE_COUNT_UI_MAX = 999
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

# 예전에 Power Type1/2/3의 '대표 전압'으로 코드에 고정되어 있던 값
# (block4 매칭 임계값이자 condition 칸의 초기값이었다). 2026-08 재설계로 두 역할 모두
# 사용자가 직접 입력하는 필드(voltage(digital) / condition의 Type[N] 값)로 바뀌었고,
# 이 상수는 이제 **첫 화면에 채워줄 seed 값**으로만 쓰인다 - 기존 config를 마이그레이션
# 하거나(voltage(digital) 필드가 없던 config) 기본 condition(BST/WST/TIV)을 새로 만들 때,
# 사용자가 손대지 않아도 예전과 같은 매칭 결과가 나오도록 하기 위함이다.
LEGACY_POWER_TYPE_SEED_VOLTAGE = {1: 0.8, 2: 2.2, 3: 1.8}

# Port List Volts 값 / Power Type voltage(digital) 값끼리 "같다"고 볼 허용 오차.
# block4(voltage_name 치환)와 block5(input_signal_level 치환) 매칭, Voltage Map
# Validate의 voltage(digital) 중복 검사가 모두 이 값을 공유한다.
VOLTAGE_MATCH_TOLERANCE = 1e-3


def power_type_label(type_index: int) -> str:
    return f"Power Type{type_index}"


def condition_value_key(type_index: int) -> str:
    """condition 하나 안에서 Power Type 하나의 전압 값 key ('type1', 'type2', ...)."""
    return f"type{type_index}"


def legacy_voltage_map_value_key(group: str, type_index: int) -> str:
    """2026-08 이전 config의 값 key ('bst_type1' 등) - 마이그레이션 전용."""
    return f"{group.lower()}_type{type_index}"


def voltage_map_name_key(type_index: int) -> str:
    """Power Type마다 하나뿐인 voltage name 필드 key (condition 무관)."""
    return f"power_type{type_index}_name"


def voltage_map_digital_voltage_key(type_index: int) -> str:
    """
    Power Type마다 하나뿐인 voltage(digital) 필드 key (condition 무관, 2026-08 추가).
    Port List Volts 값과 매칭시키는 임계값 - block4의 voltage_name 치환과 block5의
    input_signal_level 치환 둘 다 이 값을 기준으로 삼는다.
    """
    return f"power_type{type_index}_digital_voltage"


def new_condition(name: str = "", values: dict | None = None) -> dict:
    """
    voltage condition 하나. values에 없는 Power Type은 그냥 빈 값으로 취급된다
    (Power Type 개수에 상한이 없어져 미리 다 채워둘 수 없다 - 화면에서 값을 읽을 때
    항상 `values.get(key, "")`처럼 기본값과 함께 읽으므로 없어도 문제없다).
    """
    return {
        CONDITION_ID_KEY: uuid.uuid4().hex,
        CONDITION_NAME_KEY: str(name),
        CONDITION_VALUES_KEY: {
            str(k): str(v) for k, v in (values or {}).items() if v is not None
        },
    }


def default_conditions() -> list[dict]:
    """
    config에 아무것도 없을 때 쓰는 기본 condition 3개 (BST / WST / TIV). Power Type1~3
    값은 예전 고정 대표 전압으로 seed한다(그 이상 Power Type은 사용자가 채워야 함).
    """
    seed = {
        condition_value_key(i): str(v) for i, v in LEGACY_POWER_TYPE_SEED_VOLTAGE.items()
    }
    return [new_condition(name, seed) for name in DEFAULT_CONDITION_NAMES]


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
    """저장된 Power Type 개수를 허용 범위(최소 1, 상한 없음)로 보정해서 반환."""
    try:
        count = int(voltage_map.get(POWER_TYPE_COUNT_KEY, POWER_TYPE_COUNT_DEFAULT))
    except (TypeError, ValueError):
        count = POWER_TYPE_COUNT_DEFAULT
    return max(POWER_TYPE_COUNT_MIN, count)
