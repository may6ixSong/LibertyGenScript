"""
file_scanner.py

PDK 폴더의 *.lib 파일, DBS Simulation 폴더의 *.mt0 파일 목록을 찾는 로직.
GUI에 의존하지 않는 순수 함수로 작성.
"""

from __future__ import annotations

from pathlib import Path

from step1_setup.field_defs import DBS_FILE_EXTENSION, is_pdk_filename


def list_pdk_lib_files(pdk_folder: str) -> list[str]:
    if not pdk_folder or not Path(pdk_folder).is_dir():
        return []
    return sorted(
        p.name for p in Path(pdk_folder).iterdir() if p.is_file() and is_pdk_filename(p.name)
    )


def list_dbs_mt0_files(dbs_folder: str) -> list[str]:
    if not dbs_folder or not Path(dbs_folder).is_dir():
        return []
    return sorted(p.name for p in Path(dbs_folder).glob(f"*{DBS_FILE_EXTENSION}"))