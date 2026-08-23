"""
pin_field_defs.py

Step 3 'Constants & Pin Settings' 화면의 Pin 설정 섹션 정의.
"""

from __future__ import annotations

import re

VIRTUAL_POWER_KEY = "virtual_power"
ENABLE_SIGNAL_KEY = "enable_signal"
POWER_DOWN_KEY = "power_down_signal"
DBS_OUTPUT_KEY = "dbs_output_signal"

# Virtual Power 는 Port List의 'Port' 컬럼이 이 값인 행들 중에서 선택
VIRTUAL_POWER_PORT_TYPE = "PWR"
# Enable signal은 'Port' 컬럼이 이 값인 행들의 Pin name과 매치되어야 함 (2026-08부터
# Power down control signal 등과 동일하게 와일드카드(*) 패턴 허용 - split_pattern_and_range +
# fnmatch로 매칭)
ENABLE_SIGNAL_PORT_TYPE = "PORT"

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