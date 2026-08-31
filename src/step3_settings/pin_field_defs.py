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
       └ timing_sense / timing_type        (block5 timing{} - 인식된 pin 전체 공통 1쌍)
       └ (Check 후) 인식된 pin마다 related pin  (block5 timing{} related_bus_pins)

DBS output pin은 Port List 파일이 바뀌면 같은 와일드카드라도 인식되는 pin 집합이
달라지므로, Step3 Validate 전에 반드시 "Check DBS Output Pins"를 먼저 눌러 현재 Port
List 기준으로 pin 목록을 다시 뽑아야 한다 (expand_dbs_output_pins).
"""

from __future__ import annotations

import fnmatch
import re

from step1_setup.port_list_reader import list_pins_by_port_type

VIRTUAL_POWER_KEY = "virtual_power"
ENABLE_SIGNAL_KEY = "enable_signal"
VIRTUAL_POWER_SWITCH_FUNCTION_KEY = "virtual_power_switch_function"
VIRTUAL_POWER_PG_FUNCTION_KEY = "virtual_power_pg_function"

POWER_DOWN_KEY = "power_down_signal"
POWER_DOWN_RISE_POWER_KEY = "power_down_rise_power"
POWER_DOWN_FALL_POWER_KEY = "power_down_fall_power"
POWER_DOWN_WHEN_KEY = "power_down_when"

DBS_OUTPUT_KEY = "dbs_output_signal"
DBS_TIMING_SENSE_KEY = "dbs_timing_sense"
DBS_TIMING_TYPE_KEY = "dbs_timing_type"
# {인식된 DBS output pin name: related pin} - "Check DBS Output Pins"로 뽑은 pin마다 하나씩.
# 2026-08부터 이 값은 더 이상 사용자가 편집하지 않고, Check 시점에 Port List의
# 'Related Pin' 컬럼 값으로 고정된다(settings_view._fill_related_pin_table).
DBS_RELATED_PINS_KEY = "dbs_related_pins"
# {인식된 DBS output pin name: str(bit 수)} - 2026-08 추가. 이 DBS output pin의 총
# Bits를 몇 bit씩 쪼개 block5에 여러 pin() 범위로 나눠 쓸지(quotient = 총 bits /
# 이 값). Related Pin이 그 quotient로 다시 나뉜 bit 수는 자동 계산이며 사용자가
# 직접 입력하지 않는다(settings_validator._validate_dbs_related_pins).
DBS_BIT_SPLIT_KEY = "dbs_output_bit_split"

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
