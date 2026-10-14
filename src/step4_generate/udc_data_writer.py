"""
udc_data_writer.py

Step4 Generate 때 liberty와 함께 output path에 쓰는 UDC sweep 데이터 파일 (2026-10 추가).
DBS output(.mt0)의 slope/cload 값을 파일에 적힌 순서 그대로 HSPICE `.data` 블록으로
옮겨 적은 텍스트 파일이다 - vim으로 열어 복사해 쓰는 용도라 확장자는 .txt로 한다.

파일명: UDC_{DBS 파일명에서 .mt0 뺀 것}.txt

    ****  UDC condition applied
    .data sweep_data slope Cload
    +	0.00113118n	0.000416157p
    ...
    .enddata

slope는 초 -> ns(×1e9, 'n'), cload는 F -> pF(×1e12, 'p')로 바꿔 쓴다. 부동소수점 오차가
끼지 않도록 .mt0에 적힌 원본 텍스트를 Decimal로 자릿수만 옮긴다(유효숫자 그대로).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from step4_generate.mt0_reader import COL_AXIS_COLUMN, ROW_AXIS_COLUMN, read_mt0_columns

_HEADER_LINES = ("****  UDC condition applied", ".data sweep_data slope Cload")
_FOOTER_LINE = ".enddata"
_SLOPE_EXPONENT = 9    # 초 -> ns
_CLOAD_EXPONENT = 12   # F -> pF


def build_udc_filename(dbs_filename: str) -> str:
    stem = dbs_filename
    if stem.lower().endswith(".mt0"):
        stem = stem[: -len(".mt0")]
    return f"UDC_{stem}.txt"


def _scaled(raw: str, exponent: int) -> str:
    value = Decimal(raw).scaleb(exponent).normalize()
    return format(value, "f")


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
            f"+\t{_scaled(r[slope_key], _SLOPE_EXPONENT)}n\t{_scaled(r[cload_key], _CLOAD_EXPONENT)}p"
            for r in parsed["rows"]
        ]
    except InvalidOperation:
        return out_path, f"non-numeric slope/cload value in '{dbs_filename}'"

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join([*_HEADER_LINES, *lines, _FOOTER_LINE]) + "\n")
    except OSError as e:
        return out_path, str(e)
    return out_path, None
