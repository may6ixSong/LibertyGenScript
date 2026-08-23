"""
missing_data.py

PDK/DK 파일 또는 Port List에서 기대한 값/줄을 못 찾았을 때 공통으로 쓰는 표시 규칙.
예외를 던지지 않고 빈 자리로 남기되, 사람이 바로 알아볼 수 있게
"####### ... is missing in {source} #########" 주석 + `<NOT_FOUND_IN_...>` 토큰으로
표시한다 (block2/block3/block4 어디서든 동일한 규칙 사용).

2026-08 추가: block4의 pg_pin은 값이 PDK가 아니라 Port List Excel에서 오므로,
출처가 다름을 알 수 있게 별도 토큰(PORT_LIST_NOT_FOUND_TOKEN)을 둔다.
"""

from __future__ import annotations

NOT_FOUND_TOKEN = "<NOT_FOUND_IN_PDK>"
PORT_LIST_NOT_FOUND_TOKEN = "<NOT_FOUND_IN_PORTLIST>"

# 우리가 새로 쓰는 모든 구조적 블록의 들여쓰기 기준: 항상 2칸 단위
# (레거시 script가 tab/2칸/4칸을 뒤섞어 쓰던 것을 통일함, 2026-08 확정).
# PDK/DK 파일이나 Port List Excel에서 읽어온 값도 원본 들여쓰기는 버리고 텍스트만
# 가져와 아래 기준으로 다시 들여쓴다.
INDENT_1 = "  "      # 2 spaces - library { ... } 바로 아래 (voltage_map, cell, type 등)
INDENT_2 = "    "    # 4 spaces - 그 안의 한 단계 더 (cell 안의 pg_pin/pin/bus, operating_conditions 안의 process 등)
INDENT_3 = "      "  # 6 spaces - 그보다 한 단계 더 (pg_pin/pin 안의 속성, bus 안의 bus_type/pin 등)
INDENT_4 = "        "  # 8 spaces - bus 안에 있는 pin{}의 속성 (library > cell > bus > pin, 4단계)
INDENT_5 = "          "    # 10 spaces - bus > pin > timing{} 의 속성 (5단계)
INDENT_6 = "            "  # 12 spaces - timing{} > cell_rise/fall(){} 안의 values(...) 줄 (6단계)


def write_missing_comment(f_out, description: str, source: str) -> None:
    f_out.write(f"####### {description} is missing in {source} #########\n")
