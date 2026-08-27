# Generator 사용법

## 폴더 구조

```
generator/
├── run_generator.sh      # 실행 진입점 (소스로 바로 실행할 때)
├── build_exe.sh            # 배포용 폴더로 빌드 (선택사항, 아래 참고)
├── config/                  # 설정 저장 위치 (소스 실행이든 빌드된 exe든 동일하게 여기 사용)
│   └── user_config.json
├── output/                  # 실행마다 자동으로 비워지고 새 결과물로 채워짐 (직접 손대지 말 것)
├── dist/                     # build_exe.sh 결과물이 생기는 곳 (dist/liberty_generator/ 폴더)
└── src/                       # 소스 코드
    ├── main.py                 # 진입점 (GUI 실행)
    ├── runtime_paths.py         # 소스 실행/빌드된 exe 실행 모두에서 경로를 올바르게 찾는 헬퍼
    ├── gui_app.py                # 메인 윈도우 조립 (탭 구성, 저장/생성 버튼)
    ├── gui_global_tab.py         # '전역 설정' 탭 (입력 경로, Constant 값)
    ├── gui_config_tab.py         # 'Config 목록' 탭 (생성 파일 목록 + 설정 20개 + Pin 목록)
    ├── gui_checker_tab.py        # '검사' 탭 (유효성 검사 결과 표시)
    ├── field_defs.py             # 모든 입력 필드 정의 (Constant/Setting 이름은 여기서만 수정)
    ├── config_manager.py         # 설정 저장/로드
    ├── validator.py              # 유효성 검사 로직 (checker)
    ├── generator_core.py         # 실제 산출물 생성 로직
    ├── scrollable_frame.py       # 재사용 가능한 스크롤 폼 위젯
    ├── CLAUDE.md                  # Claude Code 작업 규칙
    └── README.md                 # 이 문서
```

## GUI 구성

- **전역 설정 탭**: Input Folder 1/2, Excel 입력 파일 경로 + Constant 값(전역 공통)
- **Config 목록 탭**: 생성할 파일(config)을 추가/복제/삭제하며 관리. 각 config는 설정 20개
  (그중 하나는 Input Folder 1의 `.A` 파일 중에서 선택하는 드롭다운)와 Pin 목록(이름-값 쌍, 개수 자유)을 가짐
- **검사 탭**: "검사 실행" 버튼으로 전역 설정/각 config의 누락값, 경로 존재 여부, 폴더 내 파일 존재 여부,
  선택한 `.A` 파일이 실제로 존재하는지 등을 한 번에 확인

하단 "검사 후 생성" 버튼은 검사를 통과해야만 실제 생성 로직을 실행합니다.

## 실행 방법 (두 가지)

### 1) 소스로 바로 실행 (개발/테스트용)

`generator` 폴더에서:
```bash
./run_generator.sh
```
PyQt5가 설치된 Anaconda Python(`/appl/CAEutil/LINUX/local/Anaconda/Anaconda3.7`)이
필요함 (VWP에 이미 확인됨).

### 2) 빌드해서 폴더째 배포 (python/pip 전혀 불필요)

이 Anaconda 환경에 PyInstaller가 이미 설치되어 있어, python/pip 없이도 동작하는
독립 실행 폴더를 만들 수 있습니다.

```bash
./build_exe.sh
```
빌드가 끝나면 `dist/liberty_generator/` 폴더가 생깁니다. 이 폴더 안에 실행파일과
필요한 라이브러리가 전부 들어있으니, **폴더 전체를** 다른 사람에게 복사해주면 됩니다.
받는 사람은 python도 PyQt5도 몰라도 폴더 안의 실행파일만 실행하면 됩니다:
```bash
cd liberty_generator
chmod +x liberty_generator
./liberty_generator
```
실행하면 그 폴더 안에 `config/`, `output/` 폴더가 자동으로 생깁니다.
폴더 안의 나머지 파일들은 실행에 필요한 라이브러리이므로 지우거나 옮기면 안 됩니다.

묶어서 전달하려면:
```bash
tar czf liberty_generator.tar.gz -C dist liberty_generator
```

**참고**: 빌드(`build_exe.sh`)는 이 Anaconda 환경이 있어야 하지만, 빌드된 결과물
(`dist/liberty_generator/`)은 그 환경 없이도 독립적으로 동작합니다. 코드를 수정할
때마다 `build_exe.sh`를 다시 실행해서 새로 빌드해야 합니다.

**주의**: 재빌드하면 `dist/liberty_generator/` 폴더를 통째로 지우고 다시 만듭니다.
그 안에서 앱을 실행해 저장해둔 `config/`는 빌드 스크립트가 자동으로 백업했다가
복원해주지만, `output/`은 사라집니다 (어차피 실행할 때마다 새로 채워지는 폴더입니다).

**빌드가 느리다면**: `build_exe.sh` 안의 `EXCLUDES` 목록으로 Anaconda에 깔린
numpy/scipy/matplotlib 등을 의존성 그래프에서 빼고 있습니다. 빌드된 앱이
`No module named XXX`로 죽는다면 그 모듈만 목록에서 빼면 됩니다.

### "허가 거부(Permission denied)"가 뜨는 경우

최초 1회 실행권한 부여:
```bash
chmod +x run_generator.sh
```

`chmod` 이후에도 안 되면 (디렉토리가 noexec로 마운트된 경우), 실행권한 없이:
```bash
sh run_generator.sh
```

### Anaconda python을 못 찾는다는 에러가 뜨는 경우

```bash
find /appl -maxdepth 4 -iname "Anaconda*" 2>/dev/null
```
로 실제 경로를 확인한 뒤, `run_generator.sh`와 `build_exe.sh` 안의 경로를 수정.

## 다른 사람에게 복사해줄 때

`generator` 폴더 전체를 그대로 복사해서 전달하면 됩니다. 받은 사람은:
1. `chmod +x run_generator.sh` (최초 1회)
2. `./run_generator.sh`

설정값(`config/user_config.json`)은 폴더 안에 있으므로, 각자 처음 실행 시 자기 환경에 맞는 경로를 다시 입력해서 저장하면 됩니다.

## 동작 방식

1. GUI 실행 시 이전에 저장된 값이 자동으로 채워짐 (`config/user_config.json`)
2. "전역 설정" 탭에서 경로/Constant 입력, "Config 목록" 탭에서 생성할 파일 개수만큼 config를 추가하고 각각의 설정/Pin 입력
3. "검사" 탭에서 "검사 실행"으로 누락값/경로 오류 등을 미리 확인 가능
4. "저장" — 현재 화면의 모든 값을 `config/user_config.json`에 저장
5. "검사 후 생성" — 저장 후 자동으로 검사를 실행하고, 통과하면 `generator_core.run_generation()` 호출
   - 실행 시작 시 `output/` 폴더를 항상 먼저 비움
   - config 개수만큼 산출물 파일이 `output/` 폴더에 생성됨
   - 검사에 실패하면 생성하지 않고 어떤 문제인지 안내

## 개발 참고

- `generator_core.py`에 실제 생성 로직 구현 (현재는 TODO 자리와 테스트용 요약 파일 생성만 있음)
- Claude Code로 추가 모듈을 생성할 경우, `src/` 폴더를 프로젝트 루트로 잡고 작업할 것
- GUI는 PyQt5 사용. Anaconda Python 3.7.6에 이미 설치되어 있어 추가 설치 불필요
  (시스템 기본 `python3`/`python3.11`에는 PyQt5 없음 — 반드시 Anaconda python으로 실행)
- Python 3.7 호환을 위해 `list[dict]`, `int | None` 같은 최신 타입힌트를 쓰는 파일 맨 위에는
  `from __future__ import annotations`가 있어야 함
