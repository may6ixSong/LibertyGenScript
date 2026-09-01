"""
block5_writer.py

Block 5 작성: cell{} 안에 두 가지를 이어서 쓴다 (block4가 cell{}을 연 상태로
이어지므로, 닫는 중괄호는 여기서도 쓰지 않고 liberty_writter.py가 block5까지 다 쓴
뒤에 처리한다):

  1. Port List에서 Port=="PORT"인 핀들을 pin()/bus()로 쓴다 (먼저):
  2. {process_prefix}_pdt_pin(...) - Port List에서 Port=="PWR"/"GND"인 핀들
     (pin()/bus() 다음에 이어서 씀, 2026-08 확정). PWR 먼저, 그 다음 GND, 각 그룹
     내부는 Port List에 나온 순서 그대로. pin_type은 PWR이면 "power", GND면
     "ground". related_pin은 이 핀을 Related Power(PWR) / Related ground(GND)
     컬럼 값으로 쓰고 있는 다른 행들의 Pin name을 콤마로 나열(PWR은 Related Power만,
     GND는 Related ground만 봄 - 서로 교차 X). 관련된 핀이 하나도 없으면
     related_pin 줄 자체를 쓰지 않는다(2026-08 확정).

- Bits==1: `pin({pin name}) { ... }` 하나만 쓴다.
- Bits>1 : `bus({pin name에서 [MSB:LSB] 뺀 것}) { bus_type : ... ; pin({pin name
           그대로, [MSB:LSB] 포함}) { ... } }` 형태로 감싸서 쓴다. bus_type이
           가리키는 이름은 block3의 type_bus 이름과 동일하다.
- direction은 Port List의 I/O 컬럼 값(I/O)을 보고 input/output으로 정한다.

pin() 몸체 내용은 pin name이 아래 중 어디에 매치되는지에 따라 달라진다(우선순위,
2026-08 확정 - 여러 개 동시에 매치될 수 있어 순서를 정했다. 실제로는 서로 겹치지
않는 이름을 쓰는 게 일반적이라 우선순위가 문제될 일은 거의 없을 것):
  1. Step3 Enable Signal for power gate(와일드카드) - always_on/switch_pin 포맷
  2. Step3 DBS output signal(와일드카드) - max_capacitance + timing{} 블록
     (cell_fall/cell_rise/rise_transition/fall_transition, 이 job의 DBS output
     (.mt0) 파일에서 tplh/tphl/tr/tf 값을 읽어와 채움)
  3. Step3 Power down control signal(와일드카드) - {prefix}_acore_internal_power 추가
  4. 그 외 - 표준 포맷

값이 Port List/DBS 파일에서 파싱되지 않는 경우는 예외를 던지지 않고 missing_data.py
규칙대로 표시한다.

2026-08 수정 (Step3 연계 입력 반영):
  - DBS output pin의 timing{} 안 related_bus_pins는 Step3에서 "Check DBS Output Pins"로
    인식한 pin마다 사용자가 직접 입력한 related pin을 쓴다(job["dbs_related_pins"]).
    Step3 Validate가 이 값이 Port List에 실제 존재하는 pin이고 그 pin 행의 'Related Pin'
    컬럼 값과 정확히 일치하는지까지 검사한다. 입력이 없는 예외적인 경우에만 Port List의
    'Related Pin' 컬럼 값으로 폴백한다.
  - timing_sense / timing_type도 하드코딩이 아니라 Step3 입력값(인식된 DBS output pin
    전체 공통 1쌍)을 쓴다.
  - Power down control signal 매치 pin의 {prefix}_acore_internal_power 안 rise/fall
    power와 when 역시 Step3 입력값을 쓴다(예전 하드코딩 값이 그 입력의 기본값이다).

2026-08 수정: DBS output signal 매치 pin의 timing 표(cell_fall/cell_rise/
rise_transition/fall_transition)는 PDK/DK 파일과 완전히 무관하다는 피드백을 반영해,
PDK/DK 파일의 DFF/primitive cell 검색 결과(sections)에 대한 의존을 전부 제거했다.
표의 행/열 크기는 이제 순전히 DBS output(.mt0) 파일 자체에서
derive_table_shape()로 추론한다. 이에 따라 이 파일 전체에서 더 이상 `sections`
파라미터를 받지 않는다.

2026-08 재설계 (input_signal_level): 예전에는 Port List 'Volts' 컬럼 값(핀별)을 그대로
포맷해서 썼다. 그런데 한 번의 실행에서 생성하는 여러 liberty가 같은 Port List를
공유하다 보니, 서로 다른 voltage corner로 생성되는 liberty들끼리도 이 값이 항상
똑같이 나오는 문제가 있었다. 이제 block4의 pg_pin voltage_name 치환과 같은 방식으로
Power Type의 voltage(digital) 값에 매칭시키되, 치환 결과는 다르다:
  - Port List Volts 값이 이 job의 어느 Power Type 'voltage(digital)' 값과 일치하면,
    **이 job이 선택한 voltage condition**의 같은 Power Type Type[N] 값(사용자가
    Voltage Map의 condition 표에 입력한 실제 숫자, 예: worst case로 올린 0.85)으로
    치환해서 쓴다(job["input_signal_level_thresholds"], liberty_assembler.build_job
    참고) - block4처럼 이름으로 바꾸는 게 아니라 값 자체를 그 condition의 값으로
    바꾼다는 점이 다르다.
  - 일치하는 Power Type이 없으면 기존처럼 Port List Volts 값을 그대로 쓴다.
  자리수는 그대로 %0.5f.

2026-08 추가 (DBS output pin bit 분할) → 2026-08 재설계(Number of Col) + Serial
Cluster "More than 1"(Split Serial) 추가: DBS output signal과 매치되고 Bits > 1인
(=bus로 쓰이는) pin은 예전에는 bus() 안에 pin() 하나만 썼다. 이제 bus() 안에 **여러
개의 pin() 범위**(예: `pin(BUS[12:0])`, `pin(BUS[25:13])`, ...)를 이어서 쓸 수 있고,
그 몫(cluster 개수)을 어떻게 구하고 related_bus_pins를 무엇으로 채우는지는 Data
Transfer Type + (Serial일 때) Serial Cluster 선택에 따라 갈린다
(`_dbs_bit_split_groups()`가 `_parallel_split_groups()`/`_serial_split_groups()`로
위임):

  - **Parallel(DTBUS)**: Step3에서 pin마다 입력한 "Number of Col(#)"(옛 "Bit
    Depth"/"Split into (bits)")으로 **Related Pin의 총 Bits**를 나눈 몫이 cluster
    개수다(2026-08 재설계 - 예전에는 DBS output pin 쪽을 나눴었다). 그 DBS output
    pin 자신의 총 Bits를 그 cluster 개수로 나눈 몫이 cluster당 DBS output pin 자신의
    Bit Depth(자동 계산). related_bus_pins는 Related Pin 하나를 그 몫만큼 슬라이스한
    범위다.
  - **Serial(ADBUS) + Serial Cluster "More than 1"(2026-08 추가, Split Serial)**:
    전체 공통 "Number of Col(#)"으로 이 DBS output pin 자신의 총 Bits를 나눈 몫이
    cluster 개수다(Parallel과 반대 - 옛 방식과 같은 계산이다). related_bus_pins는
    Related Pin 하나를 슬라이스하는 게 아니라, 전체 공통 Related Pin 와일드카드
    (예: 'ABC_*[12:0]', '*'는 숫자만 매칭)로 Port==PORT pin 중 매치된 개별 pin들을
    '*' 숫자값 오름차순으로 cluster에 배정한다. 인식된 DBS output pin이 Top/Bottom
    2개면 그 중 '*'가 매치한 숫자값이 홀수인 것만 Top에, 짝수인 것만 Bottom에 쓴다 -
    Top/Bottom 판별은 DBS output pin 와일드카드의 '*'가 그 pin에서 실제로 매치한
    조각이 정확히 'T'/'B'인지로 한다(`pin_field_defs.classify_wildcard_side`).
  - **Serial(ADBUS) + Serial Cluster "1"(기본값)**: 이 분할 기능이 생기기 전과 완전히
    동일 - 몫은 항상 1, pin() 하나만 쓰고 related_bus_pins는 Related Pin 전체.

나눠떨어지지 않는 조합/필요한 입력이 비어 있는 경우는 Step3 Validate가 이미
막으므로(settings_validator._validate_dbs_related_pins) 여기서는 그 계산을
방어적으로 다시 수행하고, 실패하면 쪼개지 않고 원래 범위 1개로 폴백한다. **각
cluster의 pin() 몸체는 pin_name과 related_bus_pins만 다르고 나머지
(capacitance/max_capacitance/related_power_pin/related_ground_pin/
input_signal_level, 그리고 timing() 안의 timing_sense/timing_type/cell_fall/
cell_rise/rise_transition/fall_transition 표 전부)는 동일하게 반복해서 쓴다** - 이
job의 DBS output(.mt0) 파일에서 읽는 값 자체가 cluster와 무관하게 하나이기 때문
(job["dbs_bit_split"]/job["dbs_serial_num_col"]/job["dbs_serial_related_pattern"]/
job["pin_bit_info"], liberty_assembler.build_job 참고). Bits==1인 DBS output
pin(bus가 아니라 pin() 하나만 쓰는 경우)은 애초에 쪼갤 대상이 아니므로 이 분할
로직이 적용되지 않는다.
"""

from __future__ import annotations

import fnmatch

from step1_setup.port_list_reader import parse_bit_range, strip_bit_range_suffix
from step3_settings.constants_field_defs import VOLTAGE_MATCH_TOLERANCE
from step3_settings.pin_field_defs import (
    DBS_SERIAL_CLUSTER_MULTI, DBS_TRANSFER_TYPE_PARALLEL, DBS_TRANSFER_TYPE_SERIAL,
    classify_wildcard_side, match_digit_wildcard,
)
from step4_generate.missing_data import (
    INDENT_2, INDENT_3, INDENT_4, PORT_LIST_NOT_FOUND_TOKEN, write_missing_comment,
)
from step4_generate.mt0_reader import build_timing_table, derive_table_shape
from step4_generate.pdk_stream_reader import parse_index_last_value

# cell_fall/cell_rise/rise_transition/fall_transition 순서와, 각각이 .mt0 파일의
# 어느 컬럼에서 오는지 매핑 (2026-08 확정: tplh->cell_rise, tphl->cell_fall,
# tr->rise_transition, tf->fall_transition). 쓰는 순서는 사용자 예시와 동일하게
# cell_fall을 먼저 쓴다.
_TIMING_ENTRIES = [
    ("cell_fall", "tphl"),
    ("cell_rise", "tplh"),
    ("rise_transition", "tr"),
    ("fall_transition", "tf"),
]


_strip_bit_range_suffix = strip_bit_range_suffix  # 2026-08: port_list_reader로 이동, 이름만 유지


def _matches_pattern(pin_name: str, pattern: str) -> bool:
    if not pattern:
        return False
    return fnmatch.fnmatchcase(pin_name, pattern)


def _text_or_missing(f_out, value: str, description: str, pdk_filename: str) -> str:
    value = (value or "").strip()
    if not value:
        write_missing_comment(f_out, description, pdk_filename)
        return PORT_LIST_NOT_FOUND_TOKEN
    return value


def _cap_text(value: float | None) -> str:
    return PORT_LIST_NOT_FOUND_TOKEN if value is None else "%0.6f" % value


def _volts_text(value: float | None) -> str:
    return PORT_LIST_NOT_FOUND_TOKEN if value is None else "%0.5f" % value


def _input_signal_level_text(pin_volts: float | None, job: dict) -> str:
    """
    input_signal_level 값 (모듈 docstring "2026-08 재설계 (input_signal_level)" 참고).
    Port List Volts 값이 이 job의 어느 Power Type voltage(digital)과 일치하면 이
    job이 선택한 voltage condition의 같은 Power Type Type[N] 값으로, 일치하지 않으면
    Port List Volts 값 그대로 (둘 다 %0.5f).
    """
    if pin_volts is not None:
        for threshold, condition_value in (job.get("input_signal_level_thresholds") or {}).items():
            if abs(pin_volts - threshold) < VOLTAGE_MATCH_TOLERANCE:
                return _volts_text(condition_value)
    return _volts_text(pin_volts)


def _direction_text(f_out, pin: dict, pdk_filename: str) -> str:
    io_value = (pin.get("io") or "").strip().upper()
    if io_value.startswith("I"):
        return "input"
    if io_value.startswith("O"):
        return "output"
    write_missing_comment(f_out, f"I/O value for pin '{pin['pin_name']}' (Port List)", pdk_filename)
    return PORT_LIST_NOT_FOUND_TOKEN


def _write_values_table(f_out, table: list[list[str]] | None, indent: str) -> None:
    f_out.write(f"{indent}values (")
    if table is None:
        f_out.write(f'"{PORT_LIST_NOT_FOUND_TOKEN}");\n')
        return
    row_texts = ['"' + " " + ", ".join(row) + '"' for row in table]
    for i, row_text in enumerate(row_texts):
        is_last = i == len(row_texts) - 1
        f_out.write(row_text if i == 0 else f"{indent}         {row_text}")
        f_out.write(");\n" if is_last else ",\\\n")


def _write_timing_block(
    f_out, pin: dict, job: dict, indent_decl: str, related_override: str | None = None,
) -> None:
    """
    DBS output signal과 매치된 pin의 timing() { ... } 블록. 값은 전부 이 job의 DBS
    output(.mt0) 파일에서만 읽어온다 - PDK/DK 파일은 전혀 참조하지 않는다(표의
    행/열 크기도 .mt0 파일 자체의 slope/cload 컬럼에서 derive_table_shape()로
    추론함).

    related_override(2026-08 추가): DBS output pin bit 분할로 여러 pin() 범위를 쓸
    때, 그룹마다 계산된 related_bus_pins 범위 문자열을 그대로 전달받아 쓴다
    (_dbs_bit_split_groups). None이면 예전과 동일하게 job/Port List에서 related pin
    전체를 읽어 쓴다(분할 대상이 아닌 pin, 또는 분할 설정이 없어 폴백한 경우).
    """
    cell_name = job["cell_name"]
    pdk_filename = job["pdk_filename"]
    dbs_filename = job["dbs_filename"]
    dbs_path = job["dbs_path"]
    template_name = f"{cell_name}_{cell_name}_out"

    body_indent = indent_decl + "  "
    table_indent = body_indent + "  "

    if related_override is not None:
        related_pin_value = related_override
    else:
        # Step3에서 이 pin에 대해 직접 입력받은 related pin이 우선 (Step3 Validate가
        # Port List와의 일치까지 이미 확인함). 값이 없으면 Port List의 'Related Pin'
        # 컬럼으로 폴백.
        related_pin_value = (job.get("dbs_related_pins") or {}).get(pin["pin_name"], "")
        if not str(related_pin_value).strip():
            related_pin_value = pin.get("related_pin", "")
    related_pin = _text_or_missing(
        f_out, related_pin_value, f"Related Pin for pin '{pin['pin_name']}' (Step 3 / Port List)", pdk_filename,
    )

    row_count, col_count, shape_error = derive_table_shape(dbs_path)

    f_out.write(f"{indent_decl}timing () {{\n")
    f_out.write(f'{body_indent}related_bus_pins : "{related_pin}";\n')
    f_out.write(f"{body_indent}timing_sense : {job['dbs_timing_sense']};\n")
    f_out.write(f"{body_indent}timing_type : {job['dbs_timing_type']};\n")

    for liberty_key, mt0_column in _TIMING_ENTRIES:
        if shape_error:
            table, reason = None, shape_error
        else:
            table, reason = build_timing_table(dbs_path, mt0_column, row_count, col_count)

        if table is None:
            f_out.write(
                f"{body_indent}####### {mt0_column} timing table (DBS output "
                f"'{dbs_filename}') is missing - reason: {reason} #########\n"
            )
        f_out.write(f"{body_indent}{liberty_key}({template_name}) {{\n")
        _write_values_table(f_out, table, table_indent)
        f_out.write(f"{body_indent}}}\n")

    f_out.write(f"{indent_decl}}}\n")


def _max_capacitance_value(lut_sections: dict) -> str | None:
    """
    max_capacitance 값 = worst case PDK에서 읽어 온 lu_table_template index_2의
    **맨 끝 값** (2026-08 확정). index_2를 못 찾았으면 None.
    """
    return parse_index_last_value((lut_sections or {}).get("index_2_line"))


def _write_max_capacitance(f_out, job: dict, lut_sections: dict, body_indent: str) -> None:
    value = _max_capacitance_value(lut_sections)
    if value is None:
        # index_2를 못 찾은 경우에만 예전처럼 주석으로 남긴다 - 값을 지어내지 않는다.
        write_missing_comment(
            f_out,
            "index_2 (max_capacitance source) of the lu_table_template",
            job.get("worst_case_pdk_filename", job["pdk_filename"]),
        )
        f_out.write(f"{body_indent}#max_capacitance : No Answer;\n")
        return
    f_out.write(f"{body_indent}max_capacitance : {value} ;\n")


def _classify_pin_kind(pin_name: str, job: dict) -> str:
    """
    pin_name이 Step3의 어느 연계 입력(와일드카드)에 매치되는지 우선순위대로 판단.
    write_block5의 분할 여부 결정과 _write_pin_body의 몸체 포맷 결정이 같은 결과를
    써야 하므로(2026-08 DBS output pin bit 분할 추가로 분리됨) 한 곳으로 모았다.
    """
    if _matches_pattern(pin_name, job["enable_signal_pattern"]):
        return "enable_signal"
    if _matches_pattern(pin_name, job["dbs_output_pattern"]):
        return "dbs_output"
    if _matches_pattern(pin_name, job["power_down_pattern"]):
        return "power_down"
    return "standard"


def _write_pin_body(
    f_out, pin: dict, job: dict, lut_sections: dict, body_indent: str, pin_type_value: str,
    kind: str, related_override: str | None = None,
) -> None:
    pdk_filename = job["pdk_filename"]
    process_prefix = job["process_prefix"]
    pin_name = pin["pin_name"]

    direction = _direction_text(f_out, pin, pdk_filename)
    cap_text = _cap_text(pin["cap"])
    related_power = _text_or_missing(
        f_out, pin["related_power"], f"Related Power for pin '{pin_name}' (Port List)", pdk_filename,
    )
    related_ground = _text_or_missing(
        f_out, pin["related_ground"], f"Related ground for pin '{pin_name}' (Port List)", pdk_filename,
    )
    # 모듈 docstring "2026-08 재설계 (input_signal_level)" 참고.
    volts_text = _input_signal_level_text(pin["volts"], job)

    f_out.write(f"{body_indent}{process_prefix}_pin_type : {pin_type_value} ;\n")
    f_out.write(f"{body_indent}direction : {direction} ;\n")

    if kind == "enable_signal":
        f_out.write(f"{body_indent}always_on : true ;\n")
        f_out.write(f"{body_indent}switch_pin : true ;\n")
        f_out.write(f"{body_indent}capacitance : {cap_text} ;\n")
        f_out.write(f"{body_indent}related_power_pin : {related_power} ;\n")
        f_out.write(f"{body_indent}related_ground_pin : {related_ground} ;\n")
        f_out.write(f"{body_indent}{process_prefix}_input_signal_level : {volts_text} ;\n")
        return

    if kind == "dbs_output":
        f_out.write(f"{body_indent}capacitance : {cap_text} ;\n")
        # 2026-08 확정: max_capacitance는 worst case PDK의 lu_table_template index_2
        # 마지막 값을 그대로 쓴다 (예전엔 값을 몰라 "No Answer" 주석이었다).
        _write_max_capacitance(f_out, job, lut_sections, body_indent)
        f_out.write(f"{body_indent}related_power_pin : {related_power} ;\n")
        f_out.write(f"{body_indent}related_ground_pin : {related_ground} ;\n")
        f_out.write(f"{body_indent}{process_prefix}_input_signal_level : {volts_text} ;\n")
        f_out.write("\n")
        _write_timing_block(f_out, pin, job, body_indent, related_override=related_override)
        return

    f_out.write(f"{body_indent}capacitance : {cap_text} ;\n")
    f_out.write(f"{body_indent}related_power_pin : {related_power} ;\n")
    f_out.write(f"{body_indent}related_ground_pin : {related_ground} ;\n")
    f_out.write(f"{body_indent}{process_prefix}_input_signal_level : {volts_text} ;\n")

    if kind == "power_down":
        inner_body = body_indent + "  "
        f_out.write(f'{body_indent}{process_prefix}_acore_internal_power("{pin_name}") {{\n')
        f_out.write(f"{inner_body}{process_prefix}_acore_rise_power : {job['power_down_rise_power']} ;\n")
        f_out.write(f"{inner_body}{process_prefix}_acore_fall_power : {job['power_down_fall_power']} ;\n")
        f_out.write(f'{inner_body}{process_prefix}_acore_when : "{job["power_down_when"]}" ;\n')
        f_out.write(f"{body_indent}}}\n")


def _write_pin_block(
    f_out, pin: dict, job: dict, lut_sections: dict, decl_indent: str, body_indent: str,
    pin_type_value: str, kind: str | None = None, related_override: str | None = None,
) -> None:
    if kind is None:
        kind = _classify_pin_kind(pin["pin_name"], job)
    f_out.write(f"{decl_indent}pin({pin['pin_name']}) {{\n")
    _write_pin_body(f_out, pin, job, lut_sections, body_indent, pin_type_value, kind, related_override)
    f_out.write(f"{decl_indent}}}\n")


def _parallel_split_groups(
    pin_name: str, base_name: str, total_bits: int, dbs_lsb: int, related_raw: str, job: dict,
) -> list[tuple[str, str]] | None:
    """
    Data Transfer Type이 Parallel(DTBUS)일 때의 분할 (2026-08 재설계 - "Number of Col"
    이 Related Pin 쪽을 나눈다, 옛 "Bit Depth"는 DBS output pin 쪽을 나눴었다):

    - Related Pin의 총 Bits를 Step3의 "Number of Col(#)"으로 나눈 몫이 cluster 개수.
    - 그 DBS output pin 자신의 총 Bits를 그 cluster 개수로 나눈 몫이 cluster당
      DBS output pin 자신의 Bit Depth(사용자가 입력하지 않고 자동 계산).

    나눠떨어지지 않으면 None(호출부가 폴백 처리).
    """
    if not related_raw:
        return None
    related_base = _strip_bit_range_suffix(related_raw)
    related_info = (job.get("pin_bit_info") or {}).get(related_base)
    if related_info is None:
        return None
    related_bits = related_info["bits"]
    related_lsb = related_info["lsb"]

    col_text = str((job.get("dbs_bit_split") or {}).get(pin_name, "")).strip()
    try:
        col_count = int(col_text) if col_text else None
    except ValueError:
        return None
    if not col_count or col_count <= 0 or col_count > related_bits:
        return None
    if related_bits % col_count != 0:
        return None
    cluster_count = related_bits // col_count
    if cluster_count <= 1:
        return None
    if total_bits % cluster_count != 0:
        return None
    per_cluster_dbs = total_bits // cluster_count
    related_per_group = col_count

    groups = []
    for i in range(cluster_count):
        g_dbs_lsb = dbs_lsb + i * per_cluster_dbs
        g_dbs_msb = g_dbs_lsb + per_cluster_dbs - 1
        g_related_lsb = related_lsb + i * related_per_group
        g_related_msb = g_related_lsb + related_per_group - 1
        groups.append((
            f"{base_name}[{g_dbs_msb}:{g_dbs_lsb}]",
            f"{related_base}[{g_related_msb}:{g_related_lsb}]",
        ))
    return groups


def _serial_split_groups(
    pin_name: str, base_name: str, total_bits: int, dbs_lsb: int, job: dict,
) -> list[tuple[str, str]] | None:
    """
    Data Transfer Type이 Serial(ADBUS)이고 Serial Cluster가 "More than 1"(Split
    Serial)일 때의 분할 (2026-08 추가):

    - 이 DBS output pin 자신의 총 Bits를 전체 공통 "Number of Col(#)"으로 나눈 몫이
      cluster 개수(Parallel과 반대로 DBS output pin 쪽을 나눈다).
    - related_bus_pins는 Related Pin 하나를 슬라이스하는 게 아니라, 전체 공통 Related
      Pin 와일드카드로 매치된 개별 pin들을 그대로 cluster 순서에 배정한다('*'가 매치한
      숫자값 오름차순). 인식된 DBS output pin이 2개(Top/Bottom)면 그 중 홀수(Top)/
      짝수(Bottom)만 쓴다(classify_wildcard_side).

    필요한 조건이 하나라도 안 맞으면 None(호출부가 폴백 처리) - Step3 Validate가 이미
    막아야 하지만 방어적으로 다시 계산한다.
    """
    col_text = str(job.get("dbs_serial_num_col", "")).strip()
    try:
        col_count = int(col_text) if col_text else None
    except ValueError:
        return None
    if not col_count or col_count <= 0 or total_bits <= 1:
        return None
    if total_bits % col_count != 0:
        return None
    cluster_count = total_bits // col_count
    if cluster_count <= 1:
        return None

    related_pattern_text = str(job.get("dbs_serial_related_pattern", "")).strip()
    if not related_pattern_text:
        return None
    candidate_names = [p["pin_name"] for p in (job.get("port_pins") or [])]
    matched = match_digit_wildcard(related_pattern_text, candidate_names)
    if not matched:
        return None

    recognized_pins = job.get("dbs_recognized_pins") or []
    if len(recognized_pins) >= 2:
        dbs_pattern = job.get("dbs_output_pattern", "")
        side = classify_wildcard_side(dbs_pattern, pin_name)
        if side is None:
            return None
        parity = 1 if side == "top" else 0
        selected = [name for value, name in matched if value % 2 == parity]
    else:
        selected = [name for _value, name in matched]

    if len(selected) != cluster_count:
        return None

    groups = []
    for i in range(cluster_count):
        g_dbs_lsb = dbs_lsb + i * col_count
        g_dbs_msb = g_dbs_lsb + col_count - 1
        groups.append((f"{base_name}[{g_dbs_msb}:{g_dbs_lsb}]", selected[i]))
    return groups


def _dbs_bit_split_groups(pin: dict, job: dict) -> list[tuple[str, str]]:
    """
    DBS output pin(bus, bits > 1)을 여러 (pin() 선언용 이름, related_bus_pins 값) 쌍의
    목록으로 쪼갠다. 무엇을 어떻게 쪼갤지는 Data Transfer Type + (Serial일 때) Serial
    Cluster 선택에 따라 갈린다 - 각각 `_parallel_split_groups`/`_serial_split_groups`
    참고. 조건이 하나라도 안 맞으면(나눠떨어지지 않거나 필요한 입력이 비어 있으면)
    쪼개지 않고 원래 pin 이름 + related pin 전체 1개짜리 목록으로 폴백한다
    (missing_data 정책과 동일하게, 값을 지어내지 않고 그대로 통과시켜 사람이 알아볼
    수 있게 남긴다). Serial Cluster "1"(기본값)이면 이 DBS output pin bit 분할 기능이
    생기기 전과 완전히 동일한 동작(cluster 1개, quotient 1)이 그대로 유지된다.
    """
    pin_name = pin["pin_name"]
    total_bits = pin["bits"]
    base_name = _strip_bit_range_suffix(pin_name)
    _dbs_msb, dbs_lsb = parse_bit_range(pin_name, total_bits)

    related_raw = (job.get("dbs_related_pins") or {}).get(pin_name, "")
    if not str(related_raw).strip():
        related_raw = pin.get("related_pin", "")
    related_raw = str(related_raw).strip()

    fallback = [(pin_name, related_raw)]

    transfer_type = job.get("dbs_data_transfer_type")
    if transfer_type == DBS_TRANSFER_TYPE_PARALLEL:
        groups = _parallel_split_groups(pin_name, base_name, total_bits, dbs_lsb, related_raw, job)
        return groups if groups is not None else fallback

    if transfer_type == DBS_TRANSFER_TYPE_SERIAL and job.get("dbs_serial_cluster_mode") == DBS_SERIAL_CLUSTER_MULTI:
        groups = _serial_split_groups(pin_name, base_name, total_bits, dbs_lsb, job)
        return groups if groups is not None else fallback

    return fallback


def _write_pdt_pin_block(f_out, pin: dict, pin_type: str, process_prefix: str) -> None:
    """
    {process_prefix}_pdt_pin(...) 블록 하나. PWR pin은 "power", GND pin은 "ground"
    로 pin_type을 쓴다. related_pin은 이 핀을 Related Power(PWR)/Related ground
    (GND) 컬럼 값으로 쓰고 있는 다른 Port List 행들의 Pin name을 콤마로 나열한다.
    나열할 때 'A[1:0]'처럼 bit range가 붙은 이름은 그 [MSB:LSB] 부분을 잘라내고
    순수 pin name만 적는다(2026-08 확정 - related_pin 표시에서만 그렇고, bus 핀
    자체의 pin()/bus() 선언에 쓰이는 전체 이름(bit range 포함)은 그대로 유지됨 -
    port_list_reader.py의 원본 데이터는 건드리지 않고 여기서 표시할 때만 잘라냄).
    관련된 핀이 하나도 없으면 related_pin 줄 자체를 아예 쓰지 않는다.
    """
    related_pins = [_strip_bit_range_suffix(name) for name in (pin.get("related_pins") or [])]
    f_out.write(f"{INDENT_2}{process_prefix}_pdt_pin({pin['pin_name']}) {{\n")
    f_out.write(f"{INDENT_3}{process_prefix}_pdt_pin_type : {pin_type} ;\n")
    if related_pins:
        related_text = ", ".join(related_pins)
        f_out.write(f'{INDENT_3}{process_prefix}_pdt_related_pin : "{related_text}" ;\n')
    f_out.write(f"{INDENT_2}}}\n")


def write_block5(f_out, job: dict, lut_sections: dict) -> None:
    """
    Args:
        job: liberty_assembler.build_job()의 결과 (cell_name, process_prefix,
             port_pins, pwr_pins, gnd_pins, enable_signal_pattern,
             power_down_pattern, power_down_rise_power/fall_power/when,
             dbs_output_pattern, dbs_related_pins, dbs_bit_split, pin_bit_info,
             dbs_timing_sense/timing_type, dbs_path 포함).
        lut_sections: pdk_stream_reader.read_lut_table_sections()의 결과(worst case
             PDK에서 실행당 한 번 읽음). DBS output pin의 max_capacitance 값을 여기
             index_2의 마지막 값에서 가져온다.
    """
    cell_name = job["cell_name"]
    process_prefix = job["process_prefix"]

    # 2026-08 확정: pin()/bus() 를 먼저 전부 쓰고, 그 다음에
    # {process_prefix}_pdt_pin(...) (PWR 먼저, 그 다음 GND, 각 그룹 내부는 Port
    # List에 나온 순서 그대로)을 이어서 쓴다.
    for pin in job["port_pins"]:
        bits = pin["bits"]
        if bits == 1:
            _write_pin_block(f_out, pin, job, lut_sections, INDENT_2, INDENT_3, "data")
            continue

        base_name = _strip_bit_range_suffix(pin["pin_name"])
        bus_type = f"bus_0_{bits - 1}_{bits}_{cell_name}"
        f_out.write(f"{INDENT_2}bus({base_name}) {{\n")
        f_out.write(f"{INDENT_3}bus_type : {bus_type} ;\n")

        kind = _classify_pin_kind(pin["pin_name"], job)
        if kind == "dbs_output":
            # Step3의 설정(Data Transfer Type + Serial Cluster)에 맞춰 여러 pin() 범위로
            # 나눠 쓴다 - 모듈 docstring "DBS output pin bit 분할" 절 참고.
            for pin_label, related_label in _dbs_bit_split_groups(pin, job):
                split_pin = dict(pin)
                split_pin["pin_name"] = pin_label
                _write_pin_block(
                    f_out, split_pin, job, lut_sections, INDENT_3, INDENT_4, "data_bus",
                    kind="dbs_output", related_override=related_label,
                )
        else:
            _write_pin_block(f_out, pin, job, lut_sections, INDENT_3, INDENT_4, "data_bus", kind=kind)

        f_out.write(f"{INDENT_2}}}\n")

    for pin in job["pwr_pins"]:
        _write_pdt_pin_block(f_out, pin, "power", process_prefix)
    for pin in job["gnd_pins"]:
        _write_pdt_pin_block(f_out, pin, "ground", process_prefix)
