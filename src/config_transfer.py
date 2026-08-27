"""
config_transfer.py

Step1(user_config.json) + Step2(udc_settings.json) + Step3(step3_settings.json,
Voltage Map 포함) 세 config 파일을 파일 하나로 export/import 하는 기능 (2026-08 추가,
src/CLAUDE.md TODO 해결).

- export_config(): 세 manager의 load_*()로 정규화된 현재 값을 읽어 하나의 JSON으로
  묶어 쓴다. load_*()를 거치므로 기본값 병합/옛 포맷 이관이 이미 적용된 값이 저장된다.
- import_config(): 반대로 그 JSON의 각 section을 해당 manager의 save_*()로 그대로
  써 넣는다. 각 파일을 다시 읽을 때(다음 load_*() 호출, 예: Step1 Import 직후 화면
  갱신이나 Step2/3 화면을 다시 만들 때) 그 manager의 정규화 로직이 다시 적용되므로,
  가져온 파일이 일부 필드가 없거나 옛 포맷이어도 안전하게 기본값과 병합된다.
- 가져온 경로(PDK/DBS 폴더, Port List 파일 등)가 지금 이 환경에 실제로 존재하는지는
  여기서 검사하지 않는다 - 파일이 옮겨졌을 수도 있으므로, 예전과 동일하게 각 Step의
  Validate가 그 역할을 그대로 담당한다(2026-08 확정: import 후에도 validate는 원래
  그대로 다시 진행).
"""

from __future__ import annotations

import json
from pathlib import Path

from step1_setup import config_manager
from step2_udc import udc_manager
from step3_settings import settings_manager

EXPORT_FORMAT_NAME = "liberty_generator_config"
EXPORT_FORMAT_VERSION = 1
DEFAULT_EXPORT_BASENAME = "liberty_generator_config"
EXPORT_FILE_EXTENSION = ".json"

_USER_CONFIG_KEY = "user_config"
_UDC_SETTINGS_KEY = "udc_settings"
_STEP3_SETTINGS_KEY = "step3_settings"


def build_export_payload() -> dict:
    return {
        "format": EXPORT_FORMAT_NAME,
        "version": EXPORT_FORMAT_VERSION,
        _USER_CONFIG_KEY: config_manager.load_config(),
        _UDC_SETTINGS_KEY: udc_manager.load_state(),
        _STEP3_SETTINGS_KEY: settings_manager.load_settings(),
    }


def export_config(dest_path: str) -> None:
    """현재 저장돼 있는 config 3종을 dest_path 하나의 JSON 파일로 묶어 쓴다."""
    payload = build_export_payload()
    path = Path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def import_config(src_path: str) -> None:
    """
    src_path의 JSON을 읽어 config 3종 파일을 덮어쓴다. 인식되는 section이 하나도
    없으면 ValueError를 던진다(잘못된 파일을 조용히 무시하지 않기 위해).
    """
    with open(src_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise ValueError("Invalid config file: expected a JSON object at the top level.")

    sections = {
        _USER_CONFIG_KEY: config_manager.save_config,
        _UDC_SETTINGS_KEY: udc_manager.save_state,
        _STEP3_SETTINGS_KEY: settings_manager.save_settings,
    }

    imported_any = False
    for key, save_fn in sections.items():
        section = payload.get(key)
        if isinstance(section, dict):
            save_fn(section)
            imported_any = True

    if not imported_any:
        raise ValueError(
            "Invalid config file: no recognized sections "
            f"({', '.join(sections)}) were found."
        )
