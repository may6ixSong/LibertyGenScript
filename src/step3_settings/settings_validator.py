"""
settings_validator.py

Step 3 Constants(output_prefix / DFF Cell Name / LUT Table / Worst case primitive
liberty) + Pin 설정(및 각 pin에 연계된 하위 필드)에 대한 유효성 검사와, Step 2로 옮겨진
Voltage Map(사용자 정의 voltage condition x Power Type)에 대한 유효성 검사
(validate_voltage_map - Step 2 Validate에서 호출). GUI에 의존하지 않는 순수 함수로 작성.

2026-08 수정: 이전에는 Pin 설정만 검사 대상이었으나, 다음 값들이 비어 있으면 이후
단계(liberty 파일명/voltage_map/block3 lu_table_template/block4 cell·pg_pin/block5
timing·internal_power)를 만들 수 없으므로 이제 Validate 단계에서 함께 걸러낸다:
  - output_prefix (출력 파일명에 쓰임)
  - DFF Cell Name / LUT Table (block3의 lu_table_template index_1/index_2를
    PDK/DK 파일에서 찾아오는 데 쓰임)
  - Worst case primitive liberty (그 lu_table_template을 어느 PDK에서 가져올지 -
    Step2의 liberty setting들이 고른 PDK 파일 중 하나여야 함)
  - class / process_prefix (block4의 cell 속성에 쓰임 - {process_prefix}_class 등)
  - Pin 설정의 모든 하위 필드 (switch_function/pg_function, rise·fall power/when,
    timing_sense/timing_type, 인식된 DBS output pin마다의 related pin)

DBS output pin의 related pin 검사(2026-08 확정 → 2026-08 자동 채움 도입 →
2026-08 bit 분할 추가 → 2026-08 Data Transfer Type 추가 → 2026-08 재설계(Number of
Col) + Serial Cluster "More than 1"(Split Serial) 추가):
  1. "Check DBS Output Pins"로 인식해 둔 pin 집합이 지금 Port List로 다시 펼친 결과와
     동일해야 한다 (Port List 파일이 바뀌면 인식 결과가 달라지므로, 다르면 다시 Check).
  2. 각 related pin은 비어 있으면 안 되고,
  3. Port List에 실제로 존재하는 Pin name이어야 한다.
  4. (Data Transfer Type이 Parallel일 때만 검사, 2026-08 재설계) 그 DBS output pin의
     Bits가 1보다 크면(=block5에서 bus로 쓰임), Related Pin의 Bits가 Step3에서 입력한
     "Number of Col(#)"(옛 "Bit Depth"/"Split into (bits)") 값으로 정확히 나누어떨어져야
     한다(나눠떨어진 몫 = cluster 개수 = block5가 쓸 pin() 개수 - **Related Pin 쪽을
     나눈다는 점이 옛 규칙과 반대**). 그리고 그 DBS output pin 자신의 Bits가 그 몫으로
     정확히 나누어떨어져야 한다(나눠떨어진 몫이 cluster당 DBS output pin 자신의 Bit
     Depth - 사용자가 직접 입력하지 않고 자동 계산됨). 어느 한쪽이라도 나누어떨어지지
     않으면 에러. **Data Transfer Type이 Serial이면 이 4번 규칙 자체를 건너뛴다.**
  5. (Data Transfer Type이 Serial이고 Serial Cluster가 "More than 1"일 때만, 2026-08
     추가 → 2026-08 재설계 - `_validate_serial_split`) 공통 "Number of Col(#)"은
     인식된 pin 전체 공통 1개지만, Related Pin은 **인식된 DBS output pin마다 독립적인
     와일드카드**다(옛 Top/Bottom 홀짝 분배 방식은 폐기 - "DBS output pin이 1개일 때가
     총 N벌"이라고 생각하면 된다). 인식된 pin마다: 그 pin의 Bits가 공통 Number of
     Col로 나누어떨어져야(몫 = 그 pin의 cluster 개수) 하고, 그 pin 자신의 Related Pin
     와일드카드로 Port==PORT pin 중 일치하는 pin이 있어야 하며(`match_digit_wildcard_pins`,
     '*'는 숫자만 매칭), 매치된 개수가 정확히 그 cluster 개수와 같아야 한다(다른 DBS
     output pin의 매치 결과와는 무관하게 독립적으로 검사). Serial Cluster가
     "1"(기본값)이면 이 5번 규칙도 건너뛴다 - 이 기능이 생기기 전과 완전히 동일하다.

  (변경 이력) 예전에는 여기에 "그 DBS output pin이 있는 Port List 행의 'Related Pin'
  컬럼 값과 정확히 일치해야 한다"는 4번째 규칙이 있었다. "Check DBS Output Pins"를
  누르면 각 pin의 Related Pin이 Port List의 'Related Pin' 컬럼 값으로 **자동
  채워지고**(settings_view._fill_related_pin_table), 한때는 표에서 직접 다른 pin으로
  고쳐 쓸 수도 있었다. 2026-08 bit 분할 추가와 함께 Related Pin은 다시 Port List
  값으로 **고정**(수정 불가)되었으므로, 여기 3번 규칙("Port List에 실제 존재하는
  pin")은 사실상 Port List 데이터 자체의 무결성 검사가 되었다(사용자 입력 오류를
  막는 용도가 아님, Serial Cluster "More than 1"의 Related Pin은 이 규칙과 별개로
  와일드카드 매칭 자체가 존재 확인을 겸한다).

Data Transfer Type(2026-08 추가): Parallel(DTBUS) / Serial(ADBUS) 중 선택하는 전역
설정(인식된 pin 전체 공통) - pin_field_defs.DBS_TRANSFER_TYPE_KEY. Parallel이면 위
4번 규칙대로 Number of Col/cluster 분할을 검사하고, Serial이면 Serial Cluster
선택(pin_field_defs.DBS_SERIAL_CLUSTER_MODE_KEY)에 따라 "1"이면 이 기능이 생기기
전과 동일하게(quotient 항상 1) 검사를 건너뛰고, "More than 1"이면 위 5번 규칙을
따른다.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from step1_setup.port_list_reader import (
    list_all_pin_bit_info, list_all_pin_names, list_pins_by_port_type, list_port_pins_detailed,
    strip_bit_range_suffix,
)
from step3_settings.constants_field_defs import (
    CONDITION_NAME_KEY, CONDITION_VALUES_KEY, VOLTAGE_CONDITIONS_KEY, VOLTAGE_MATCH_TOLERANCE,
    condition_value_key, power_type_count_of, power_type_label, voltage_map_digital_voltage_key,
    voltage_map_name_key,
)
from step3_settings.pin_field_defs import (
    DBS_BIT_SPLIT_KEY, DBS_OUTPUT_KEY, DBS_RELATED_PINS_KEY, DBS_SERIAL_CLUSTER_MODE_DEFAULT,
    DBS_SERIAL_CLUSTER_MODE_KEY, DBS_SERIAL_CLUSTER_MULTI, DBS_SERIAL_NUM_COL_KEY,
    DBS_SERIAL_RELATED_PATTERN_KEY, DBS_TIMING_SENSE_KEY, DBS_TIMING_TYPE_KEY,
    DBS_TRANSFER_TYPE_DEFAULT, DBS_TRANSFER_TYPE_KEY, DBS_TRANSFER_TYPE_PARALLEL,
    DBS_TRANSFER_TYPE_SERIAL, ENABLE_SIGNAL_KEY, ENABLE_SIGNAL_PORT_TYPE,
    POWER_DOWN_FALL_POWER_KEY, POWER_DOWN_KEY, POWER_DOWN_RISE_POWER_KEY, POWER_DOWN_WHEN_KEY,
    VIRTUAL_POWER_KEY, VIRTUAL_POWER_PG_FUNCTION_KEY, VIRTUAL_POWER_PORT_TYPE,
    VIRTUAL_POWER_SWITCH_FUNCTION_KEY, expand_dbs_output_pins, match_digit_wildcard_pins,
    split_pattern_and_range,
)

_REQUIRED_TEXT_SCALARS = [
    ("class", "class"),
    ("process_prefix", "process_prefix"),
    ("output_prefix", "output_prefix"),
    ("dff_cell_name", "DFF Cell Name"),
    ("primitive_cell_name", "LUT Table"),
]

_WORST_CASE_PDK_KEY = "worst_case_pdk"
_WORST_CASE_PDK_LABEL = "Worst case primitive liberty"

# 비어 있으면 안 되는 pin 하위 필드 (key, 화면 라벨, 와일드카드 허용 여부)
_REQUIRED_PIN_TEXT_FIELDS = [
    (ENABLE_SIGNAL_KEY, "Enable Signal for power gate", True),
    (VIRTUAL_POWER_SWITCH_FUNCTION_KEY, "Virtual Power Switch Function", False),
    (VIRTUAL_POWER_PG_FUNCTION_KEY, "Virtual Power PG Function", False),
    (POWER_DOWN_KEY, "Power down control signal", True),
    (POWER_DOWN_WHEN_KEY, "Power down control signal - when", False),
    (DBS_OUTPUT_KEY, "DBS output pin", True),
    (DBS_TIMING_SENSE_KEY, "DBS output pin - timing_sense", False),
    (DBS_TIMING_TYPE_KEY, "DBS output pin - timing_type", False),
]

# 비어 있으면 안 되고 숫자로도 읽혀야 하는 pin 하위 필드
_REQUIRED_PIN_NUMBER_FIELDS = [
    (POWER_DOWN_RISE_POWER_KEY, "Power down control signal - rise power"),
    (POWER_DOWN_FALL_POWER_KEY, "Power down control signal - fall power"),
]


def validate_constants(scalars: dict, paired_pdk_files: list[str] | None = None) -> list[str]:
    """
    class / process_prefix / output_prefix / DFF Cell Name / LUT Table(비어있으면 출력
    파일명 또는 block3를 만들 수 없음)과 Worst case primitive liberty(lu_table_template과
    block5 max_capacitance를 가져올 PDK)가 채워져 있는지 검사.

    Voltage Map은 화면이 Step 2로 옮겨졌으므로 여기서 검사하지 않는다
    (validate_voltage_map 참고).

    Args:
        paired_pdk_files: Step2의 liberty setting들이 고른 PDK 파일명 목록.
            None이면 "Step2 목록과 대조"는 건너뛰고 비어있는지만 검사한다.
    """
    errors: list[str] = []

    for key, label in _REQUIRED_TEXT_SCALARS:
        value = str(scalars.get(key, "")).strip()
        if not value:
            errors.append(f"{label} is empty.")

    worst_case_pdk = str(scalars.get(_WORST_CASE_PDK_KEY, "")).strip()
    if not worst_case_pdk:
        errors.append(f"{_WORST_CASE_PDK_LABEL} is not selected.")
    elif paired_pdk_files is not None and worst_case_pdk not in paired_pdk_files:
        errors.append(
            f"{_WORST_CASE_PDK_LABEL} '{worst_case_pdk}' is not one of the PDK files "
            "selected by the Step 2 liberty settings. Select it again."
        )

    return errors


def validate_voltage_map(voltage_map: dict) -> list[str]:
    """
    Voltage Map 검사 (2026-08: 화면이 Step 2 왼쪽 열로 옮겨져 Step 2 Validate에서 호출됨
    → 2026-08 Power Type 개수 무제한 + voltage(digital) 필드 추가).

      - voltage condition이 최소 1개는 있어야 하고,
      - condition 이름이 비어 있으면 안 되며 서로 중복되어도 안 된다
        (Step 2의 liberty setting이 이름으로 condition을 고르기 때문. 대소문자만 다른
        이름도 같은 이름으로 본다),
      - 각 condition의 Power Type1..N(현재 Power Type 개수만큼) 값이 전부 채워진
        숫자여야 하고,
      - 그 개수만큼의 Power Type name이 전부 채워져 있어야 하고,
      - 그 개수만큼의 Power Type voltage(digital)이 전부 채워진 숫자여야 하며, 서로
        VOLTAGE_MATCH_TOLERANCE 이내로 겹치면 안 된다(겹치면 Port List Volts 값이
        어느 Power Type에 매칭되는지 모호해진다).
    """
    errors: list[str] = []

    power_type_count = power_type_count_of(voltage_map)
    conditions = voltage_map.get(VOLTAGE_CONDITIONS_KEY) or []
    if not conditions:
        errors.append(
            "No voltage condition has been added to the Voltage Map. Add at least one "
            "(each liberty setting selects one of them)."
        )
        return errors

    seen_names: dict[str, int] = {}
    for index, condition in enumerate(conditions):
        name = str(condition.get(CONDITION_NAME_KEY, "")).strip()
        label = f"Voltage condition #{index + 1}"
        if not name:
            errors.append(f"{label} has no name.")
        else:
            label = f"Voltage condition '{name}'"
            first_index = seen_names.setdefault(name.lower(), index)
            if first_index != index:
                errors.append(
                    f"{label} has the same name as voltage condition #{first_index + 1}. "
                    "Voltage condition names must be unique."
                )

        values = condition.get(CONDITION_VALUES_KEY) or {}
        for type_index in range(1, power_type_count + 1):
            value = str(values.get(condition_value_key(type_index), "")).strip()
            value_label = f"{label} {power_type_label(type_index)}"
            if not value:
                errors.append(f"{value_label} is empty.")
                continue
            try:
                float(value)
            except ValueError:
                errors.append(f"{value_label} is not a valid number: {value!r}")

    names = voltage_map.get("names", {}) or {}
    for type_index in range(1, power_type_count + 1):
        value = str(names.get(voltage_map_name_key(type_index), "")).strip()
        if not value:
            errors.append(f"Voltage Map {power_type_label(type_index)} name is empty.")

    # 2026-08 추가: Power Type별 voltage(digital) - Port List Volts 값을 Power Type에
    # 매칭시키는 임계값. 서로 겹치면(오차 범위 안에 들어오면) 어느 Power Type으로
    # 매칭될지 모호해지므로 중복도 함께 막는다.
    digital_voltages = voltage_map.get("digital_voltages", {}) or {}
    seen_digital: list[tuple[int, float]] = []
    for type_index in range(1, power_type_count + 1):
        text = str(digital_voltages.get(voltage_map_digital_voltage_key(type_index), "")).strip()
        label = f"Voltage Map {power_type_label(type_index)} voltage (digital)"
        if not text:
            errors.append(f"{label} is empty.")
            continue
        try:
            value = float(text)
        except ValueError:
            errors.append(f"{label} is not a valid number: {text!r}")
            continue
        for other_index, other_value in seen_digital:
            if abs(value - other_value) < VOLTAGE_MATCH_TOLERANCE:
                errors.append(
                    f"{label} ({value}) is too close to "
                    f"{power_type_label(other_index)} voltage (digital) ({other_value}) - "
                    "each Power Type's voltage (digital) must be distinguishable so a Port "
                    "List Volts value matches exactly one Power Type."
                )
        seen_digital.append((type_index, value))

    return errors


def _validate_serial_split(pins: dict, recognized: list[str], dbs_bits_by_name: dict, port_list_file: str) -> list[str]:
    """
    Serial(ADBUS) + Serial Cluster "More than 1"(Split Serial) 검사 (2026-08 재설계 -
    Top/Bottom 홀짝 분배 방식 폐기, 자세한 규칙은 이 모듈 docstring "Serial Cluster"
    절 참고).

    - 전체 공통 'Number of Col (#)'는 인식된 pin 전체에 하나.
    - Related Pin은 **인식된 DBS output pin마다 독립적인 와일드카드**
      (`pin_field_defs.DBS_SERIAL_RELATED_PATTERN_KEY`, {pin name: 와일드카드} dict).
    - 인식된 pin마다 독립적으로 검사한다("DBS output pin이 1개일 때가 총 N벌"):
      그 pin의 총 Bits가 공통 Number of Col로 나누어떨어져야 하고(몫 = cluster
      개수, pin은 1비트를 넘어야 함), 그 pin 자신의 Related Pin 와일드카드로 매치된
      pin이 있어야 하며, 매치된 개수가 정확히 그 cluster 개수와 같아야 한다. 다른
      DBS output pin의 매치 결과와는 서로 무관하다.
    """
    errors: list[str] = []

    col_text = str(pins.get(DBS_SERIAL_NUM_COL_KEY, "")).strip()
    if not col_text:
        errors.append("'Number of Col' is empty.")
        return errors
    try:
        col_count = int(col_text)
    except ValueError:
        errors.append(f"'Number of Col' value '{col_text}' is not a whole number.")
        return errors
    if col_count <= 0:
        errors.append("'Number of Col' must be a positive whole number.")
        return errors

    related_pattern_map = pins.get(DBS_SERIAL_RELATED_PATTERN_KEY)
    if not isinstance(related_pattern_map, dict):
        related_pattern_map = {}

    for pin_name in recognized:
        dbs_bits = dbs_bits_by_name.get(pin_name)
        if dbs_bits is None:
            errors.append(f"DBS output pin '{pin_name}': Bits value could not be read from the Port List.")
            continue
        if dbs_bits <= 1:
            errors.append(
                f"DBS output pin '{pin_name}' has only 1 bit and cannot use Serial Cluster "
                "'More than 1'."
            )
            continue
        if col_count > dbs_bits or dbs_bits % col_count != 0:
            errors.append(
                f"DBS output pin '{pin_name}': its {dbs_bits} bits do not divide evenly by "
                f"'Number of Col' ({col_count})."
            )
            continue
        cluster_count = dbs_bits // col_count

        related_pattern = str(related_pattern_map.get(pin_name, "")).strip()
        if not related_pattern:
            errors.append(f"DBS output pin '{pin_name}': 'Related Pin (wildcard)' is empty.")
            continue
        matched = match_digit_wildcard_pins(port_list_file, related_pattern)
        if len(matched) != cluster_count:
            errors.append(
                f"DBS output pin '{pin_name}': Related Pin pattern '{related_pattern}' matched "
                f"{len(matched)} pin(s), but {cluster_count} are required "
                "(this pin's Bits / Number of Col)."
            )

    return errors


def _validate_dbs_related_pins(pins: dict, port_list_file: str) -> list[str]:
    """
    "Check DBS Output Pins"로 인식해 둔 DBS output pin마다의 related pin +
    (2026-08 추가) bit 분할 설정 검사. (자세한 규칙은 이 모듈 docstring 참고)
    """
    errors: list[str] = []

    related_map = pins.get(DBS_RELATED_PINS_KEY)
    if not isinstance(related_map, dict):
        related_map = {}
    split_map = pins.get(DBS_BIT_SPLIT_KEY)
    if not isinstance(split_map, dict):
        split_map = {}
    transfer_type = str(pins.get(DBS_TRANSFER_TYPE_KEY, DBS_TRANSFER_TYPE_DEFAULT))
    is_parallel = transfer_type == DBS_TRANSFER_TYPE_PARALLEL
    is_serial = transfer_type == DBS_TRANSFER_TYPE_SERIAL

    recognized = expand_dbs_output_pins(port_list_file, pins.get(DBS_OUTPUT_KEY, ""))
    if not recognized:
        errors.append(
            "DBS output pin pattern matched no PORT pins. Run 'Check DBS Output Pins' "
            "again after fixing the pattern or the Port List."
        )
        return errors

    if set(related_map) != set(recognized):
        errors.append(
            "The DBS output pins recognized from the current Port List differ from the "
            "checked list (%d checked / %d recognized now). Run 'Check DBS Output Pins' again."
            % (len(related_map), len(recognized))
        )
        return errors

    all_pin_names = set(list_all_pin_names(port_list_file))
    dbs_bits_by_name = {p["pin_name"]: p["bits"] for p in list_port_pins_detailed(port_list_file)}
    pin_bit_info = list_all_pin_bit_info(port_list_file)

    for pin_name in recognized:
        value = str(related_map.get(pin_name, "")).strip()
        if not value:
            errors.append(f"Related Pin for DBS output pin '{pin_name}' is empty.")
            continue
        # 존재 확인은 전체 이름(스칼라 pin은 이 자체가 base name)과 base name(bracket
        # 제거) 둘 다로 본다 - bus pin의 Related Pin 값은 관례상 '[MSB:LSB]' 없이 base
        # name만 적히므로(Bits는 그 base name으로 Port List를 다시 찾아서 읽음), 전체
        # 이름만 보면 항상 "존재하지 않음"으로 잘못 걸러진다.
        if value not in all_pin_names and strip_bit_range_suffix(value) not in pin_bit_info:
            errors.append(
                f"Related Pin '{value}' (for DBS output pin '{pin_name}') is not a pin in the Port List."
            )
            continue

        if not is_parallel:
            # Serial(ADBUS) Cluster: 1 (또는 그 외 값): quotient는 항상 1 - Number of
            # Col을 입력받지도 검사하지도 않는다. Serial Cluster "More than 1"은 pin마다가
            # 아니라 전체 공통 설정이므로 아래에서 한 번만 검사한다.
            continue

        dbs_bits = dbs_bits_by_name.get(pin_name)
        if dbs_bits is None:
            errors.append(f"DBS output pin '{pin_name}': Bits value could not be read from the Port List.")
            continue
        if dbs_bits <= 1:
            # 1비트 pin은 block5에서 bus()로 쪼개 쓰지 않으므로 분할 설정 자체가 없다.
            continue

        related_base = strip_bit_range_suffix(value)
        related_info = pin_bit_info.get(related_base)
        if related_info is None:
            errors.append(
                f"Related Pin '{value}' (for DBS output pin '{pin_name}') has no readable Bits "
                "value in the Port List, so it cannot be split alongside the DBS output pin."
            )
            continue
        related_bits = related_info["bits"]
        if related_bits <= 1:
            errors.append(
                f"DBS output pin '{pin_name}': Related Pin '{value}' has only 1 bit, so it "
                "cannot be split into columns."
            )
            continue

        col_text = str(split_map.get(pin_name, "")).strip()
        if not col_text:
            errors.append(f"DBS output pin '{pin_name}': 'Number of Col' is empty.")
            continue
        try:
            col_count = int(col_text)
        except ValueError:
            errors.append(
                f"DBS output pin '{pin_name}': 'Number of Col' value '{col_text}' is not "
                "a whole number."
            )
            continue
        if col_count <= 0 or col_count > related_bits:
            errors.append(
                f"DBS output pin '{pin_name}': 'Number of Col' must be between 1 and "
                f"{related_bits} (Related Pin's Bits, got {col_count})."
            )
            continue
        if related_bits % col_count != 0:
            errors.append(
                f"DBS output pin '{pin_name}': Related Pin '{value}' has {related_bits} bits, "
                f"which do not divide evenly by {col_count} columns."
            )
            continue

        cluster_count = related_bits // col_count
        if dbs_bits % cluster_count != 0:
            errors.append(
                f"DBS output pin '{pin_name}': its {dbs_bits} bits do not divide evenly across "
                f"the {cluster_count} cluster(s) produced by 'Number of Col' "
                f"({dbs_bits} / {cluster_count} is not a whole number)."
            )

    if is_serial:
        cluster_mode = str(pins.get(DBS_SERIAL_CLUSTER_MODE_KEY, DBS_SERIAL_CLUSTER_MODE_DEFAULT))
        if cluster_mode == DBS_SERIAL_CLUSTER_MULTI:
            errors += _validate_serial_split(pins, recognized, dbs_bits_by_name, port_list_file)

    return errors


def validate_output_path(output_path: str) -> list[str]:
    """
    Output Path 검사 (2026-08 추가): 예전에는 Validate를 통과해야만 Output Path
    입력칸/Browse가 열렸으므로 경로 자체는 따로 검사하지 않았다. 이제 Output Path는
    Validate 전에도 자유롭게 입력/변경할 수 있으므로, Validate가 그 값이 실제로
    존재하는 폴더인지 확인한다. 아직 아무것도 입력하지 않았으면(빈 값) 이 시점에는
    에러로 보지 않는다 - Generate 버튼은 어차피 경로가 채워지고 실제로 존재해야만
    열린다(settings_view._update_generate_button_state).
    """
    value = str(output_path or "").strip()
    if not value:
        return []
    if not Path(value).is_dir():
        return [f"Output Path does not exist: {value}"]
    return []


def validate_pin_settings(pins: dict, port_list_file: str) -> list[str]:
    errors: list[str] = []

    virtual_power = str(pins.get(VIRTUAL_POWER_KEY, "")).strip()
    if not virtual_power:
        errors.append("Virtual Power is not selected.")

    for key, label, allows_wildcard in _REQUIRED_PIN_TEXT_FIELDS:
        value = str(pins.get(key, "")).strip()
        if not value:
            errors.append(f"{label} is empty.")
        elif not allows_wildcard and "*" in value:
            errors.append(f"{label} does not allow a wildcard (*): {value!r}")

    for key, label in _REQUIRED_PIN_NUMBER_FIELDS:
        value = str(pins.get(key, "")).strip()
        if not value:
            errors.append(f"{label} is empty.")
            continue
        try:
            float(value)
        except ValueError:
            errors.append(f"{label} is not a valid number: {value!r}")

    if errors:
        # 비어있는 값이 있으면 port list 대조가 의미 없으므로 여기서 마무리
        return errors

    pwr_pins = list_pins_by_port_type(port_list_file, VIRTUAL_POWER_PORT_TYPE)
    if virtual_power not in pwr_pins:
        errors.append(f"Virtual Power '{virtual_power}' was not found among PWR pins.")

    port_pins = list_pins_by_port_type(port_list_file, ENABLE_SIGNAL_PORT_TYPE)
    enable_signal = str(pins.get(ENABLE_SIGNAL_KEY, "")).strip()
    enable_pattern, _ = split_pattern_and_range(enable_signal)
    if not any(fnmatch.fnmatchcase(p, enable_pattern) for p in port_pins):
        errors.append(f"Enable signal pattern '{enable_signal}' matched no PORT pins.")

    all_pins = list_all_pin_names(port_list_file)
    power_down = str(pins.get(POWER_DOWN_KEY, "")).strip()
    power_down_pattern, _ = split_pattern_and_range(power_down)
    if not any(fnmatch.fnmatchcase(p, power_down_pattern) for p in all_pins):
        errors.append(f"Power down control signal pattern '{power_down}' matched no pins.")

    errors += _validate_dbs_related_pins(pins, port_list_file)

    return errors
