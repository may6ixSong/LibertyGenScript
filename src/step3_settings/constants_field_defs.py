"""
constants_field_defs.py

Step 3 'Constants & Pin Settings' 화면의 Constants 섹션 정의 (2026-08 전면 재설계,
2026-08 Voltage Map 재설계).

기존 `DKgen_ver`/`portdesc_make`/`mt_make`/`mt_cnt_ref_output`/`mt_cnt_ref_input` 필드는
liberty 파일 내용에 쓰이지 않는 것으로 확인되어 전부 삭제했다 (원본 스크립트에서
주석/로그 전용이거나 별도 문서 생성/검증 임계값 용도였음).

Voltage Map(구 "Voltage Condition")은 BST/WST/TIV 세 그룹 각각에 대해 "Power Type"별
전압 값을 입력받는다. Power Type 개수는 2~3개로 사용자가 조절 가능(기본 3개)하며,
기존의 High/Mid/Low라는 이름은 정확한 용어가 아니어서 Power Type1/2/3으로 이름을
바꿨다. 각 Power Type 라벨에는 그 type의 TIV 대표 전압값을 괄호로 표시한다
(Power Type1 (0.8V) / Power Type2 (2.2V) / Power Type3 (1.8V)) - 실제 BST/WST/TIV별
값은 사용자가 자유롭게 조정 가능하고, 이 대표값은 이름을 정하기 위해 고른 값일 뿐이다.
이 대표값은 block4에서 Port List Volts 값을 Power Type에 매칭시키는 고정 임계값으로도
쓰인다 (settings_validator/liberty_assembler/block4_writer 참고).

Power Type별로 voltage name(리버티 voltage_map/pg_pin에 쓰일 이름)도 별도로 입력받는다
- 이 이름은 BST/WST/TIV 구분 없이 Power Type마다 하나씩만 존재한다.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 단순 스칼라 상수: (key, label, kind, default)
#   kind: "text"         - 자유 입력
#         "pdk_dropdown" - PDK Folder 안에서 Step2 페어링에 성공한 PDK 파일 중 하나를
#                          고르는 드롭다운 (settings_view에서 화면을 열 때마다 채움)
# ---------------------------------------------------------------------------
SCALAR_CONSTANT_DEFS = [
    ("class", "class", "text", "analog"),
    # process_prefix: liberty의 벤더 커스텀 attribute 접두어. 이번 라운드(block1+block2,
    # library~default_operating_conditions) 범위에서는 실제로 쓰이지 않는다 (PDK 파일
    # 내용을 그대로 복사하는 구간에 이미 자기 접두어가 박혀있기 때문). 다음 라운드
    # (cell/pin 작성)에서 쓰일 예정이라 입력 필드만 미리 만들어 둔다.
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
    ("worst_case_pdk", "Worst case primitive liberty", "pdk_dropdown", ""),
]

# ---------------------------------------------------------------------------
# Voltage Map (구 Voltage Condition): BST/WST/TIV x Power Type1..N.
# ---------------------------------------------------------------------------
VOLTAGE_MAP_GROUPS = ["BST", "WST", "TIV"]

POWER_TYPE_COUNT_KEY = "power_type_count"
POWER_TYPE_COUNT_MIN = 2
POWER_TYPE_COUNT_MAX = 3
POWER_TYPE_COUNT_DEFAULT = 3

# Power Type별 대표(TIV) 전압값. (a) BST/WST/TIV x Power Type 칸의 초기 기본값,
# (b) block4에서 Port List Volts 값을 Power Type에 매칭시키는 고정 임계값, 두 곳에
# 쓰인다. 실제 BST/WST/TIV 표의 값은 사용자가 자유롭게 조정할 수 있고, 이 값이 바뀌어도
# (b)의 매칭 기준은 이 대표값 그대로 고정이다.
POWER_TYPE_DEFAULT_VOLTAGE = {1: 0.8, 2: 2.2, 3: 1.8}


def power_type_label(type_index: int) -> str:
    return f"Power Type{type_index} ({POWER_TYPE_DEFAULT_VOLTAGE[type_index]}V)"


def voltage_map_value_key(group: str, type_index: int) -> str:
    """BST/WST/TIV 표에서 (그룹, Power Type) 하나의 전압 값 필드 key."""
    return f"{group.lower()}_type{type_index}"


def voltage_map_name_key(type_index: int) -> str:
    """Power Type마다 하나뿐인 voltage name 필드 key (그룹 무관)."""
    return f"power_type{type_index}_name"


# 항상 POWER_TYPE_COUNT_MAX(=3) 만큼 정의해 둔다. 화면에 실제로 보이고 검증되는 건
# 그 시점의 power_type_count 만큼뿐이지만, 설정을 3->2->3으로 바꿔도 이미 입력해 둔
# Power Type3 값이 날아가지 않도록 필드 정의/저장 구조 자체는 항상 최대 개수로 둔다.
VOLTAGE_MAP_VALUE_FIELD_DEFS = [
    (voltage_map_value_key(group, i), group, i)
    for group in VOLTAGE_MAP_GROUPS
    for i in range(1, POWER_TYPE_COUNT_MAX + 1)
]

VOLTAGE_MAP_NAME_FIELD_DEFS = [
    (voltage_map_name_key(i), i) for i in range(1, POWER_TYPE_COUNT_MAX + 1)
]
