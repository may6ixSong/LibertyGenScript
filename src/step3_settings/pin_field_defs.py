"""
pin_field_defs.py

Step 3 'Constants & Pin Settings' 화면의 Pin 설정 정의.

2026-08 추가 (연계 입력 필드): 아래 세 개의 pin 입력은 각각 "그 pin을 입력했기 때문에
추가로 같이 입력해야 하는" 하위 필드들을 갖는다. 화면에서도 상위 pin 바로 아래에
들여쓰기 + 세로선으로 묶어서 표시한다 (settings_view._build_linked_group).

  1. Virtual Power (power gate)
       └ Enable Signal for power gate      (와일드카드 허용, 기존과 동일하게 사용)
       └ Virtual Power Switch Function     (와일드카드 불가 - block4 switch_function)
       └ Virtual Power PG Function         (와일드카드 불가 - block4 pg_function)
  2. Power down control signal
       └ rise power / fall power / when    (block5의 {prefix}_acore_internal_power)
  3. DBS output pin
       └ power_down_function (선택 입력)    (block5 pin() 본문 - 인식된 pin 전체 공통
                                             1개, 비어 있으면 줄 자체를 쓰지 않음)
       └ timing_sense / timing_type        (block5 timing{} - 인식된 pin 전체 공통 1쌍)
       └ (Check 후) 인식된 pin마다 related pin  (block5 timing{} related_bus_pins)

DBS output pin은 Port List 파일이 바뀌면 같은 와일드카드라도 인식되는 pin 집합이
달라지므로, Step3 Validate 전에 반드시 "Check DBS Output Pins"를 먼저 눌러 현재 Port
List 기준으로 pin 목록을 다시 뽑아야 한다 (expand_dbs_output_pins).
"""

from __future__ import annotations

import fnmatch
import re

from step1_setup.port_list_reader import list_pins_by_port_type, strip_bit_range_suffix

VIRTUAL_POWER_KEY = "virtual_power"
ENABLE_SIGNAL_KEY = "enable_signal"
VIRTUAL_POWER_SWITCH_FUNCTION_KEY = "virtual_power_switch_function"
VIRTUAL_POWER_PG_FUNCTION_KEY = "virtual_power_pg_function"

POWER_DOWN_KEY = "power_down_signal"
POWER_DOWN_RISE_POWER_KEY = "power_down_rise_power"
POWER_DOWN_FALL_POWER_KEY = "power_down_fall_power"
POWER_DOWN_WHEN_KEY = "power_down_when"

DBS_OUTPUT_KEY = "dbs_output_signal"
# 인식된 DBS output pin 전체 공통 1개(pin마다가 아님), Parallel/Serial(및 Serial
# Cluster 선택)과 무관하게 항상 같은 자리에 쓰인다 - block5의 각 DBS output pin
# pin() 본문에서 {process_prefix}_input_signal_level 바로 다음 줄로 `power_down_function
# : "..."` 을 쓴다(block5_writer._write_pin_body). **선택 입력** - 비워두면 그 줄 자체를
# 쓰지 않고, Validate도 이 필드가 비어있다고 에러로 보지 않는다(다른 DBS 하위 필드와
# 달리 필수 목록에 없음).
DBS_POWER_DOWN_FUNCTION_KEY = "dbs_power_down_function"
DBS_TIMING_SENSE_KEY = "dbs_timing_sense"
DBS_TIMING_TYPE_KEY = "dbs_timing_type"
# {인식된 DBS output pin name: related pin} - "Check DBS Output Pins"로 뽑은 pin마다 하나씩.
# 2026-08부터 이 값은 더 이상 사용자가 편집하지 않고, Check 시점에 Port List의
# 'Related Pin' 컬럼 값으로 고정된다(settings_view._fill_related_pin_table).
DBS_RELATED_PINS_KEY = "dbs_related_pins"
# {인식된 DBS output pin name: str(Number of Col)} - 2026-08 추가 → 2026-08 재설계.
# 화면 라벨은 "Number of Col (#)"(옛 "Bit Depth"/"Split into (bits)"). Related Pin의
# 총 Bits를 이 값으로 나눈 몫이 cluster 개수이고(quotient = Related Pin bits / 이 값),
# 그 cluster 개수로 DBS output pin 자신의 총 Bits를 나눈 몫이 cluster당 DBS output pin
# Bit Depth다 - 두 나눗셈 다 사용자가 직접 입력하지 않고 자동 계산이며, 어느 한쪽이든
# 나누어떨어지지 않으면 에러(settings_validator._validate_dbs_related_pins). Data
# Transfer Type이 Parallel일 때만 쓰인다.
DBS_BIT_SPLIT_KEY = "dbs_output_bit_split"

# 2026-08 추가 - Data Transfer Type: DBS output pin을 block5에 어떻게 쓸지 결정하는
# 전역 선택(인식된 pin 전체 공통, pin마다 다르지 않음).
#   - Parallel (DTBUS): 위 DBS_BIT_SPLIT_KEY로 쪼개서 pin()을 여러 개(cluster 개수만큼)
#     쓴다(2026-08 DBS output pin bit 분할 기능 그대로).
#   - Serial (ADBUS): quotient가 항상 1 - 이 기능이 생기기 전과 동일하게 pin() 하나만
#     쓴다. Bit Depth 입력 자체가 없고, Related Pin만 그대로 보여준다.
DBS_TRANSFER_TYPE_KEY = "dbs_data_transfer_type"
DBS_TRANSFER_TYPE_PARALLEL = "parallel"
DBS_TRANSFER_TYPE_SERIAL = "serial"
# 기본값은 Serial - 이 기능이 없던 예전과 같은 동작(quotient=1)이 기본이 되도록.
DBS_TRANSFER_TYPE_DEFAULT = DBS_TRANSFER_TYPE_SERIAL

# 2026-08 추가 - Serial(ADBUS)에서의 Cluster 선택("Split Serial"): Serial을 고른 뒤
# 추가로 한 번 더 고르는 전역 선택(인식된 pin 전체 공통).
#   - 1 (기본값): 이 기능이 생기기 전과 완전히 동일 - quotient 항상 1, Related Pin은
#     Port List 값 그대로.
#   - More than 1: Parallel처럼 Number of Col(#)을 입력받되(전체 공통 1개), Related
#     Pin은 Port List 컬럼이 아니라 사용자가 입력하는 와일드카드(예: "RD_EN_*[12:0]")로
#     Port List pin name 중 일치하는 pin 전체를 찾는다. DBS output pin의 총 Bits를
#     그 Number of Col로 나눈 몫이 cluster 개수이고(Parallel과 반대로 DBS output pin
#     쪽을 나눔), 그 개수만큼 와일드카드로 매치된 Related Pin이 있어야 한다. DBS
#     output pin이 Top/Bottom 2개로 인식된 경우, 매치된 Related Pin을 '*'가 매치한
#     숫자값의 홀/짝으로 나눠 Top은 홀수만, Bottom은 짝수만 쓴다(Top/Bottom 판별은
#     classify_wildcard_side 참고).
DBS_SERIAL_CLUSTER_MODE_KEY = "dbs_serial_cluster_mode"
DBS_SERIAL_CLUSTER_SINGLE = "single"
DBS_SERIAL_CLUSTER_MULTI = "multi"
DBS_SERIAL_CLUSTER_MODE_DEFAULT = DBS_SERIAL_CLUSTER_SINGLE

# Serial Cluster가 "More than 1"일 때만 쓰이는 전역(인식된 pin 전체 공통) 입력 두 개.
DBS_SERIAL_NUM_COL_KEY = "dbs_serial_num_col"
DBS_SERIAL_RELATED_PATTERN_KEY = "dbs_serial_related_pattern"

# 기본값: 2026-08 이전에 block5_writer.py / block5 timing{}에 하드코딩되어 있던 값들.
# 이제는 전부 사용자 입력이고, 아래 값들은 그 입력의 초기값(default)으로만 쓰인다.
POWER_DOWN_RISE_POWER_DEFAULT = "30000000.0000"
POWER_DOWN_FALL_POWER_DEFAULT = "0.0"
POWER_DOWN_WHEN_DEFAULT = "1"
DBS_TIMING_SENSE_DEFAULT = "non_unate"
DBS_TIMING_TYPE_DEFAULT = "combinational"

# Virtual Power 는 Port List의 'Port' 컬럼이 이 값인 행들 중에서 선택
VIRTUAL_POWER_PORT_TYPE = "PWR"
# Enable signal은 'Port' 컬럼이 이 값인 행들의 Pin name과 매치되어야 함 (2026-08부터
# Power down control signal 등과 동일하게 와일드카드(*) 패턴 허용 - split_pattern_and_range +
# fnmatch로 매칭)
ENABLE_SIGNAL_PORT_TYPE = "PORT"
# DBS output pin 와일드카드가 인식하는 대상: block5에서 실제로 pin()/bus()로 쓰이는
# 행들과 동일하게 Port=="PORT"인 행들만 (2026-08 확정)
DBS_OUTPUT_PORT_TYPE = "PORT"

# 와일드카드 패턴 뒤에 "[0:8511]" 같은 범위 표기가 붙을 수 있음.
# 이 범위는 실제 pin name 매칭에는 쓰지 않고, 화면 표시/추후 생성 단계 참고용으로만 분리.
_RANGE_SUFFIX_PATTERN = re.compile(r"^(.*?)(\[[^\]]*\])?$")


def split_pattern_and_range(text: str) -> tuple[str, str]:
    """
    'OUT_ADC_*[0:8511]' -> ('OUT_ADC_*', '[0:8511]')
    'ABC_ABC_*' -> ('ABC_ABC_*', '')
    """
    match = _RANGE_SUFFIX_PATTERN.match((text or "").strip())
    if not match:
        return (text or "").strip(), ""
    pattern = (match.group(1) or "").strip()
    range_part = (match.group(2) or "").strip()
    return pattern, range_part


def expand_dbs_output_pins(port_list_file: str, dbs_output_text: str) -> list[str]:
    """
    DBS output pin 입력(와일드카드 가능)을 현재 Port List 파일 기준으로 펼쳐서, 실제로
    매치되는 Port=="PORT" pin 이름 목록을 Port List에 나온 순서 그대로 반환한다.

    Port List 파일이 바뀌면 같은 패턴이라도 결과가 달라질 수 있으므로, Step3에서
    Validate 하기 전에 반드시 이 함수로 pin 목록을 다시 뽑아야 한다(그래야 pin마다
    related pin을 빠짐없이 입력받을 수 있다).
    """
    pattern, _range_part = split_pattern_and_range(dbs_output_text)
    if not pattern:
        return []
    pins = list_pins_by_port_type(port_list_file, DBS_OUTPUT_PORT_TYPE)
    return [p for p in pins if fnmatch.fnmatchcase(p, pattern)]


# ---------------------------------------------------------------------------
# 2026-08 추가 - Serial Cluster "More than 1" (Split Serial): 숫자만 매칭하는
# 와일드카드(Related Pin) + DBS output pin의 Top/Bottom 판별. block5_writer.py(step4)와
# settings_validator.py/settings_view.py(step3)가 모두 이 두 헬퍼를 공유한다.
# ---------------------------------------------------------------------------


def _split_single_wildcard(pattern: str) -> tuple[str, str] | None:
    """pattern에 '*'가 정확히 1개 있으면 (prefix, suffix)를, 아니면 None을 반환."""
    if pattern.count("*") != 1:
        return None
    prefix, suffix = pattern.split("*", 1)
    return prefix, suffix


def match_digit_wildcard(pattern_text: str, candidate_pin_names: list[str]) -> list[tuple[int, str]]:
    """
    Split Serial의 Related Pin 와일드카드(예: 'RD_EN_*[12:0]')를 candidate_pin_names
    (순서 유지, 보통 Port=="PORT" pin 이름 목록) 중에서 찾는다.

    - '*'는 정확히 1개여야 한다(그 외는 매치 없음으로 취급).
    - '*'가 매치하는 조각은 숫자로만 이루어져야 한다("*는 숫자만 허용하고, 문자는
      무시해야 해" - 문자가 섞인 이름은 대상에서 제외).
    - 뒤에 붙는 '[MSB:LSB]' 같은 범위 표기(있다면)는 DBS output pin 와일드카드와 같은
      관례로 실제 매칭에는 쓰지 않고 화면 표시/입력 편의용으로만 뗀다
      (split_pattern_and_range). 매칭 자체는 대괄호를 뗀 base name으로 한다.

    Returns: (와일드카드가 매치한 숫자값, Port List의 전체 pin 이름) 쌍을 숫자값
             오름차순으로 정렬한 목록.
    """
    pattern, _range_part = split_pattern_and_range(pattern_text)
    split = _split_single_wildcard(pattern)
    if split is None:
        return []
    prefix, suffix = split

    results: list[tuple[int, str]] = []
    for full_name in candidate_pin_names:
        base_name = strip_bit_range_suffix(full_name)
        if not base_name.startswith(prefix) or not base_name.endswith(suffix):
            continue
        middle = base_name[len(prefix): len(base_name) - len(suffix)]
        if middle.isdigit():
            results.append((int(middle), full_name))
    results.sort(key=lambda pair: pair[0])
    return results


def match_digit_wildcard_pins(port_list_file: str, pattern_text: str) -> list[tuple[int, str]]:
    """match_digit_wildcard()를 현재 Port List의 Port=="PORT" pin 전체를 대상으로 실행."""
    candidates = list_pins_by_port_type(port_list_file, DBS_OUTPUT_PORT_TYPE)
    return match_digit_wildcard(pattern_text, candidates)


def classify_wildcard_side(pattern: str, pin_name: str) -> str | None:
    """
    Split Serial에서 인식된 DBS output pin이 2개(Top/Bottom)일 때 어느 쪽인지 판별한다.

    pattern은 이미 split_pattern_and_range로 범위 표기를 뗀 DBS output pin 와일드카드
    (예: 'ABC_*')다. 그 '*'가 pin_name(대괄호를 뗀 base name)에서 실제로 매치한 조각이
    정확히 'T' 또는 'B'(대소문자 무관)일 때만 판별 가능하다 - 그 외(조각이 T/B가
    아니거나, pattern에 '*'가 정확히 1개가 아닌 경우)는 None(판별 불가)을 반환한다.
    """
    split = _split_single_wildcard(pattern)
    if split is None:
        return None
    prefix, suffix = split
    base_name = strip_bit_range_suffix(pin_name)
    if not base_name.startswith(prefix) or not base_name.endswith(suffix):
        return None
    fragment = base_name[len(prefix): len(base_name) - len(suffix)].strip().upper()
    if fragment == "T":
        return "top"
    if fragment == "B":
        return "bottom"
    return None
