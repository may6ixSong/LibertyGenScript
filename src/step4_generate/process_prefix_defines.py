"""
process_prefix_defines.py

이 생성기가 `{process_prefix}_*`로 쓰는 모든 커스텀 attribute/group을 library 헤더에
`define`/`define_group`으로 등록한다.

예전에는 PDK/DK 파일이 이 define들을 이미 갖고 있다고 그냥 가정했다(block1~5 어디도
define을 직접 안 씀). 그런데 PDK마다 실제로 어떤 process_prefix 커스텀 attribute를
정의해뒀는지가 다르다 - 예를 들어 `{process_prefix}_class`/`{process_prefix}_cell_type`
은 정의해둔 PDK가 `{process_prefix}_width`/`{process_prefix}_height`는 정의해두지 않은
경우가 실제로 있었다. 정의되지 않은 채로 cell{}/pin{}에서 그 attribute를 쓰면 Liberty
컴파일러가 "The '{attribute}' attribute/group name cannot be specified here."로 거부하고
.db 변환이 실패한다(2026-08 확인).

그래서 이제 이 생성기가 스스로 쓰는 attribute는 전부 스스로 define해서, 어떤 PDK를
쓰든 항상 유효하도록 한다. **단, PDK가 이미 같은 이름으로 define해둔 게 있으면 그
줄은 건너뛰고 없는 것만 새로 쓴다** (2026-08 추가 - PDK가 이미 정의해둔 define을 우리가
또 통째로 다시 쓰면, 그 PDK가 우리가 모르는 더 구체적인/다른 설정으로 정의해뒀을 수
있는 define을 덮어써 버릴 위험이 있어서다. `_collect_pdk_defined_names()`가 block2가
이미 읽어온 PDK 본문(`sections["body_lines"]`)에서 `define`/`define_group` 줄만 걸러
이름을 모아두면, `write_process_prefix_defines()`가 그 이름들은 건너뛴다).

**이 목록은 block4_writer.py / block5_writer.py가 실제로 `{process_prefix}_*`로 쓰는
모든 줄과 정확히 일치해야 한다** - 두 파일 중 하나에서 `{process_prefix}_` 로 시작하는
줄을 추가/삭제/이름변경하면 반드시 이 목록도 같이 맞춰야 한다 (src/CLAUDE.md의
"`{process_prefix}_*` custom attribute 목록 동기화" 절 참고 - Claude Code로 이
코드베이스를 고칠 때 항상 지켜야 하는 규칙으로 적어뒀다).
"""

from __future__ import annotations

import re

from step4_generate.missing_data import INDENT_1

# (attribute 이름의 process_prefix 뒷부분, 소속 그룹, 값 타입).
# 그룹은 표준 Liberty 그룹("cell"/"pin")이거나, 아래 _CUSTOM_GROUPS에 있는 커스텀
# 그룹 이름의 뒷부분(그 경우 실제 그룹 이름도 "{process_prefix}_그 이름"이 된다).
_ATTRIBUTES: list[tuple[str, str, str]] = [
    # block4_writer.py write_block4() - cell{} 직속 속성
    ("class", "cell", "string"),
    ("cell_type", "cell", "string"),
    ("width", "cell", "float"),
    ("height", "cell", "float"),
    ("voltage", "cell", "string"),
    ("temperature", "cell", "string"),
    # block5_writer.py _write_pin_body() - pin(){} 직속 속성
    ("pin_type", "pin", "string"),
    ("input_signal_level", "pin", "float"),
    # block5_writer.py _write_pin_body() - {process_prefix}_acore_internal_power{} 안 속성
    ("acore_rise_power", "acore_internal_power", "float"),
    ("acore_fall_power", "acore_internal_power", "float"),
    ("acore_when", "acore_internal_power", "string"),
    # block5_writer.py _write_pdt_pin_block() - {process_prefix}_pdt_pin(){} 안 속성
    ("pdt_pin_type", "pdt_pin", "string"),
    ("pdt_related_pin", "pdt_pin", "string"),
]

# (커스텀 그룹 이름의 process_prefix 뒷부분, 그 그룹이 실제로 나타나는 부모 그룹).
# define_group은 그 그룹 안 속성을 define하기 전에 먼저 등록돼 있어야 하므로
# _ATTRIBUTES보다 항상 먼저 쓴다.
_CUSTOM_GROUPS: list[tuple[str, str]] = [
    ("acore_internal_power", "pin"),  # block5_writer.py의 sec_acore_internal_power("pin") { ... }
    ("pdt_pin", "cell"),  # block5_writer.py의 sec_pdt_pin(pin) { ... }
]


_DEFINE_LINE_PATTERN = re.compile(r"^(define_group|define)\s*\(([^)]*)\)")


def _collect_pdk_defined_names(body_lines: list[str]) -> set[str]:
    """
    block2가 이미 읽어온 PDK 본문(pdk_stream_reader.read_pdk_library_sections()의
    `body_lines`, 첫 cell 선언 전까지의 내용)에서 `define(...)`/`define_group(...)`
    줄만 걸러, 각 줄의 첫 번째 인자(attribute/group 이름)를 모아 반환한다. 따옴표로
    감싼 이름("sec_voltage")과 안 감싼 이름(sec_voltage) 둘 다 처리한다.
    """
    defined: set[str] = set()
    for line in body_lines:
        match = _DEFINE_LINE_PATTERN.match(line.strip())
        if not match:
            continue
        first_arg = match.group(2).split(",")[0].strip().strip('"').strip("'")
        if first_arg:
            defined.add(first_arg)
    return defined


def write_process_prefix_defines(
    f_out, process_prefix: str, pdk_body_lines: list[str] | None = None,
) -> None:
    """
    이 job의 process_prefix로 위 _CUSTOM_GROUPS/_ATTRIBUTES를 전부 define_group/define
    문으로 써서 library 헤더에 등록한다. define_group을 먼저 쓰고(그 그룹을 참조하는
    define이 나중에 나오므로), 그 다음 모든 define을 쓴다.

    pdk_body_lines를 주면(block2_writer.py가 PDK 본문을 넘겨줌) 그 안에서 이미
    define/define_group된 이름은 건너뛰고, 없는 것만 새로 쓴다 - PDK가 이미 정의해둔
    걸 우리가 또 그대로 덮어쓰지 않기 위함이다.
    """
    already_defined = _collect_pdk_defined_names(pdk_body_lines or [])

    for group_suffix, parent_group in _CUSTOM_GROUPS:
        group_name = f"{process_prefix}_{group_suffix}"
        if group_name in already_defined:
            continue
        f_out.write(f"{INDENT_1}define_group({group_name}, {parent_group}) ;\n")
    for attr_suffix, group, value_type in _ATTRIBUTES:
        attr_name = f"{process_prefix}_{attr_suffix}"
        if attr_name in already_defined:
            continue
        group_name = group if group in ("cell", "pin") else f"{process_prefix}_{group}"
        f_out.write(f"{INDENT_1}define({attr_name}, {group_name}, {value_type}) ;\n")
    f_out.write("\n")
