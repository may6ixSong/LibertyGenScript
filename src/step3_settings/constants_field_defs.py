"""
constants_field_defs.py

Step 3 'Constants & Pin Settings' 화면의 Constants 섹션 정의 (2026-08 전면 재설계).

기존 `DKgen_ver`/`portdesc_make`/`mt_make`/`mt_cnt_ref_output`/`mt_cnt_ref_input` 필드는
liberty 파일 내용에 쓰이지 않는 것으로 확인되어 전부 삭제했다 (원본 스크립트에서
주석/로그 전용이거나 별도 문서 생성/검증 임계값 용도였음).

Voltage Condition은 더 이상 공정(technology)별 다중 행 테이블이 아니라, 한 번만
입력하는 단일 행(BST/WST/TIV 각 High/Mid/Low = 9칸)이다.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 단순 스칼라 상수: (key, label, kind, default)
#   kind: "text"  (전부 텍스트 - 숫자/불리언 상수는 이번 재설계에서 전부 삭제됨)
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
    # 먼저 찾고, 그 다음부터 "primitive cell명"이 처음 등장하는 cell_rise/cell_fall
    # 블록의 index_1/index_2 줄을 그대로 복사한다.
    ("dff_cell_name", "DFF Cell Name", "text", ""),
    ("primitive_cell_name", "Primitive Cell Name", "text", ""),
]

# ---------------------------------------------------------------------------
# Voltage Condition: 단일 행, BST/WST/TIV x High/Mid/Low = 9칸.
# 코드에 기본값을 하드코딩하지 않는다 (전부 빈 값으로 시작, config에만 저장).
# TIV는 예전 "plain"(기술별/Port List Volts 컬럼 매칭용) 컬럼 자리를 대체한다 - 그
# 매칭 로직은 폐기되었고, 이제 Step2에서 선택한 Voltage Condition으로 이 테이블에서
# 직접 조회한다.
# ---------------------------------------------------------------------------
VOLTAGE_CONDITION_GROUPS = ["BST", "WST", "TIV"]
VOLTAGE_CONDITION_LEVELS = ["High", "Mid", "Low"]


def voltage_condition_field_key(group: str, level: str) -> str:
    return f"{group.lower()}_{level.lower()}"


# (field_key, 화면에 보일 컬럼 라벨) - 화면/저장 양쪽에서 공용으로 쓰는 컬럼 순서.
VOLTAGE_CONDITION_FIELD_DEFS = [
    (voltage_condition_field_key(group, level), f"{group} {level}")
    for group in VOLTAGE_CONDITION_GROUPS
    for level in VOLTAGE_CONDITION_LEVELS
]
