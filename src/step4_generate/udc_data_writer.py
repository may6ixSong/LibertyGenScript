"""
udc_data_writer.py

slope/cload sweep 데이터를 HSPICE `.data` 블록 텍스트 파일로 쓴다 - vim으로 열어 복사해
쓰는 용도라 확장자는 .txt로 한다.

    ****  UDC condition applied
    .data sweep_data slope Cload
    +	0.00113118n	0.000416157p
    ...
    .enddata

두 가지 경로가 있다:
1. Step4 Generate (2026-10): DBS output(.mt0)의 slope/cload를 파일에 적힌 순서 그대로
   옮겨 쓴다. 파일명 `UDC_{DBS 파일명에서 .mt0 뺀 것}.txt`. slope는 초 -> ns(×1e9),
   cload는 F -> pF(×1e12)로 바꾼다.
2. Step1 Sweep Data export (2026-11, optional): PDK 파일마다 `lu_table_template`
   index_1(slope, ns) / index_2(cload, pF)를 읽어, slope 바깥 루프 x cload 안쪽 루프
   순서(= .mt0 레코드 순서)로 모든 조합을 쓴다. 파일명 `SweepData_{PDK 파일명에서
   .lib* 확장자 뺀 것}.txt`. PDK 값은 이미 ns/pF이므로 단위 변환은 없다.

두 경로 모두 부동소수점 오차가 끼지 않도록 원본 텍스트를 Decimal로 자릿수만 옮긴다.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from step1_setup.field_defs import strip_pdk_extension
from step4_generate.mt0_reader import COL_AXIS_COLUMN, ROW_AXIS_COLUMN, read_mt0_columns
from step4_generate.pdk_stream_reader import parse_index_tokens, read_lut_table_sections

_HEADER_LINES = ("****  UDC condition applied", ".data sweep_data slope Cload")
_FOOTER_LINE = ".enddata"
_SLOPE_EXPONENT = 9    # 초 -> ns
_CLOAD_EXPONENT = 12   # F -> pF
SWEEP_DATA_PREFIX = "SweepData_"


def build_udc_filename(dbs_filename: str) -> str:
    stem = dbs_filename
    if stem.lower().endswith(".mt0"):
        stem = stem[: -len(".mt0")]
    return f"UDC_{stem}.txt"


def _scaled(raw: str, exponent: int) -> str:
    value = Decimal(raw).scaleb(exponent).normalize()
    return format(value, "f")


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


def write_udc_data_file(dbs_path: str, dbs_filename: str, output_dir: str) -> tuple[str, str | None]:
    """
    .mt0의 slope/cload로 output_dir에 UDC 데이터 파일을 쓴다. 예외를 던지지 않는다.

    Returns:
        (쓴 파일 경로, None) 또는 (파일 경로, 실패 이유).
    """
    out_path = str(Path(output_dir) / build_udc_filename(dbs_filename))
    parsed = read_mt0_columns(dbs_path)
    if not parsed["columns"]:
        return out_path, f"could not parse a header from '{dbs_filename}'"

    lookup = {c.strip().lower(): c for c in parsed["columns"]}
    slope_key, cload_key = lookup.get(ROW_AXIS_COLUMN), lookup.get(COL_AXIS_COLUMN)
    if slope_key is None or cload_key is None or not parsed["rows"]:
        return out_path, f"slope/cload columns could not be read from '{dbs_filename}'"

    try:
        lines = [
            _data_line(_scaled(r[slope_key], _SLOPE_EXPONENT), _scaled(r[cload_key], _CLOAD_EXPONENT))
            for r in parsed["rows"]
        ]
    except InvalidOperation:
        return out_path, f"non-numeric slope/cload value in '{dbs_filename}'"

    return out_path, _write_data_file(out_path, lines)


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
        slope_text = [_scaled(v, 0) for v in slopes]
        cload_text = [_scaled(v, 0) for v in cloads]
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
