"""
runtime_paths.py

PyInstaller로 빌드된 단일 실행파일(frozen)과 소스코드 직접 실행, 두 경우 모두에서
config/output 폴더 위치를 올바르게 찾기 위한 헬퍼.

- 소스 실행: 이 파일이 있는 src/ 의 부모 폴더(generator/)를 앱 루트로 사용
- PyInstaller onefile 실행: __file__ 은 임시 추출 경로(sys._MEIPASS)를 가리켜서 사용 불가.
  대신 실행파일 자체가 위치한 폴더(sys.executable의 부모)를 앱 루트로 사용.
  -> 실행파일을 어디로 옮겨도, 그 옆에 config/output 폴더가 자동 생성됨.
"""

import sys
from pathlib import Path


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
