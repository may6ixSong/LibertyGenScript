"""
udc_data_writer.py

slope/cload sweep 데이터를 HSPICE `.data` 블록 텍스트 파일로 쓴다 - vim으로 열어 복사해
쓰는 용도라 확장자는 .txt로 한다.

    ****  UDC condition applied
    .data sweep_data slope Cload
    +	0.00113118n	0.000416157p
    ...
    .enddata

Step1 Sweep Data export (2026-11, optional): PDK 파일마다 `lu_table_template`
index_1(slope, ns) / index_2(cload, pF)를 읽어, slope 바깥 루프 x cload 안쪽 루프
순서(= .mt0 레코드 순서)로 모든 조합을 쓴다. 파일명 `SweepData_{PDK 파일명에서 .lib*
확장자 뺀 것}.txt`. PDK 값은 이미 ns/pF이므로 단위 변환은 없고, 부동소수점 오차가 끼지
않도록 원본 텍스트를 Decimal로 자릿수만 옮긴다.

(변경 이력) 2026-10에는 Step4 Generate가 liberty와 함께 .mt0의 slope/cload로
`UDC_{mt0 이름}.txt`도 썼으나, 2026-11에 liberty 생성 단계에서는 txt를 쓰지 않도록
빼고(worst case 포함) 이 Step1 export만 남겼다.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from step1_setup.field_defs import strip_pdk_extension
from step4_generate.pdk_stream_reader import parse_index_tokens, read_lut_table_sections

_HEADER_LINES = ("****  UDC condition applied", ".data sweep_data slope Cload")
_FOOTER_LINE = ".enddata"
SWEEP_DATA_PREFIX = "SweepData_"


def _plain_number(raw: str) -> str:
    """원본 숫자 텍스트를 지수 표기 없이 쓴다(유효숫자 그대로, 끝의 0만 정리)."""
    return format(Decimal(raw).normalize(), "f")


def _data_line(slope: str, cload: str) -> str:
    return f"+\t{slope}n\t{cload}p"


def _write_data_file(out_path: str, lines: list[str]) -> str | None:
    """헤더 + 데이터 줄 + .enddata를 쓴다. 실패하면 이유, 성공하면 None."""
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join([*_HEADER_LINES, *lines, _FOOTER_LINE]) + "\n")
    except OSError as e:
        return str(e)
    return None


# ---------------------------------------------------------------------------
# Step1 Sweep Data export (2026-11): PDK index_1/index_2 -> .txt
# ---------------------------------------------------------------------------
def build_sweep_data_filenames(pdk_filenames: list[str]) -> dict[str, str]:
    """
    PDK 파일명 -> `SweepData_{stem}.txt`. stem은 `.lib*` 확장자를 뗀 이름이다.
    `a.lib`와 `a.lib_css_tn`처럼 stem이 겹치면 서로 덮어쓰지 않도록, 겹치는 파일들은
    확장자까지 포함한 전체 이름('.' -> '_')을 stem으로 쓴다.
    """
    stems = {name: strip_pdk_extension(name) or name for name in pdk_filenames}
    counts: dict[str, int] = {}
    for stem in stems.values():
        counts[stem] = counts.get(stem, 0) + 1
    result = {}
    for name, stem in stems.items():
        if counts[stem] > 1:
            stem = name.replace(".", "_")
        result[name] = f"{SWEEP_DATA_PREFIX}{stem}.txt"
    return result


def write_sweep_data_from_pdk(
    pdk_path: str, pdk_filename: str, dff_cell_name: str, lut_table_name: str, out_path: str,
) -> str | None:
    """
    PDK 하나의 index_1(slope) x index_2(cload) 조합을 out_path에 쓴다. 예외를 던지지 않는다.
    Returns: 실패 이유, 성공하면 None.
    """
    try:
        sections = read_lut_table_sections(pdk_path, dff_cell_name, lut_table_name)
    except OSError as e:
        return f"could not read '{pdk_filename}': {e}"

    if not sections["dff_found"]:
        return f"DFF Cell Name '{dff_cell_name}' not found in '{pdk_filename}'"
    if not sections["primitive_found"]:
        return f"LUT Table '{lut_table_name}' not found after cell '{dff_cell_name}' in '{pdk_filename}'"

    slopes = parse_index_tokens(sections["index_1_line"])
    cloads = parse_index_tokens(sections["index_2_line"])
    if not slopes or not cloads:
        return f"index_1/index_2 not found for LUT Table '{lut_table_name}' in '{pdk_filename}'"

    try:
        slope_text = [_plain_number(v) for v in slopes]
        cload_text = [_plain_number(v) for v in cloads]
    except InvalidOperation:
        return f"non-numeric index_1/index_2 value in '{pdk_filename}'"

    # .mt0와 같은 순서: slope(index_1)가 바깥 루프, cload(index_2)가 안쪽 루프.
    lines = [_data_line(s, c) for s in slope_text for c in cload_text]
    return _write_data_file(out_path, lines)


def export_sweep_data_from_pdks(
    pdk_folder: str, pdk_filenames: list[str], dff_cell_name: str, lut_table_name: str,
    output_dir: str,
) -> list[tuple[str, str, str | None]]:
    """
    PDK 파일마다 Sweep Data 파일을 하나씩 쓴다. 하나가 실패해도 나머지는 계속 쓴다.

    Returns:
        PDK마다 (PDK 파일명, 쓴 파일 경로, None 또는 실패 이유).
    """
    filenames = build_sweep_data_filenames(pdk_filenames)
    results = []
    for name in pdk_filenames:
        out_path = str(Path(output_dir) / filenames[name])
        error = write_sweep_data_from_pdk(
            str(Path(pdk_folder) / name), name, dff_cell_name, lut_table_name, out_path,
        )
        results.append((name, out_path, error))
    return results
