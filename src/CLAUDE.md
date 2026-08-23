# CLAUDE.md — Liberty Generator

이 문서는 이 프로젝트(반도체 IP characterization용 liberty 파일 생성기)의 현재 기준
설계 문서다. `src_CLAUDE.md`(과거 버전)와 내용이 충돌하면 **이 문서가 우선**한다.

## 프로젝트 목적

기존 Perl+Python 파이프라인(`DKgen_bst`류 스크립트 + `make_liberty.py`)을 대체하는
Python 기반 liberty 파일 생성기. 기존 파이프라인의 한계:
- 한 번에 최대 4개(bst/bst_tiv/wst/wst_tiv)까지만 생성 가능
- liberty를 바로 안 만들고 `.udc`/`.pdt`/pg_pin 중간 파일을 거쳐야 함
- `atop`이라는 특정 IP에 하드코딩되어 있음

새 파이프라인 목표: PDK/DK 파일 개수만큼(제한 없이) liberty를 한 번에 생성, 중간 파일
없이 메모리에서 바로 조립, 특정 IP에 종속되지 않는 범용 구조.

## 입력

1. **PDK Folder**: `.lib` PDK/DK 파일들이 있는 폴더
2. **DBS Simulation Folder**: `.mt0` DBS output 파일들이 있는 폴더
3. **Port List (Excel)**: 핀 정보 (`Port` 컬럼이 `PORT`/`PWR`/`GND` 중 하나로 각 행을
   I/O·전원·접지 핀으로 분류)

## 파일명 규칙 (중요 — Step2 자동 페어링의 기반)

- **PDK/DK**: `{prefix}_{min|max}_0p{voltage3자리}v_{temperature}c.lib`
  예: `cs17lpv_sc_min_0p920v_m40c.lib`
- **DBS output**: `{prefix}_0p{voltage3자리}v_{temperature}c.mt0`
  예: `cs17lpv_sc_0p920v_m40c.mt0`
- `0p{XXX}v` → `0.XXX` (`0p920v` → `0.920`)
- temperature: `m{n}` → `-n`, `m` 없으면 그대로 양수 (`m40` → `-40`, `25` → `25`)
- `{prefix}`와 `min`/`max` 토큰은 페어링에 쓰이지 않음 — **voltage+temperature 숫자값만
  같으면 pair**로 인정 (2026-08 확정)

## Step 1 — Setup & Validate

PDK Folder / DBS Simulation Folder / Port List Excel 3개 경로 입력 및 검증. 변경 없음.

## Step 2 — UDC Settings (2026-08 전면 재설계)

**더 이상 사용자가 UDC 항목을 수동으로 하나씩 만들지 않는다.** 대신:

1. **공통 필드** (전체 조합에 1번만 입력): `area`, `width`, `height`, `static_current`,
   `cell_name`, `MC/HDA/OUT Timing State`
2. **자동 페어링**: PDK Folder의 `.lib` 파일들과 DBS Folder의 `.mt0` 파일들을 파일명에서
   파싱한 voltage+temperature가 일치하는 것끼리 자동으로 pair 생성. 파싱된 값이 그대로
   해당 pair의 `nom_voltage`/`nom_temperature`가 됨 (별도 입력 불필요).
3. **Validate**: PDK/DBS 폴더를 다시 스캔해 pair를 재계산, 몇 개의 1:1 pair가 유효한지
   표시. 1:1이 안 되는 파일은 에러가 아니라 **warning**으로 표시하고 생성 대상에서 제외.
4. **Voltage Condition**: 유효한 pair마다 사용자가 `bst`/`wst`/`tiv` 중 하나를 자유롭게
   선택 (PDK 파일명의 min/max와 무관, 제한 없음).

## Step 3 — Constants & Pin Settings

### Constants (2026-08 재설계)
- 스칼라 필드: `class`(기본 `"analog"`), `process_prefix`(기본 `"sec"`, 신규 — liberty
  벤더 커스텀 attribute 접두어, cell/pin 작성 라운드부터 실사용), `output_prefix`(신규 —
  출력 파일명에 사용, 아래 참고)
- **삭제된 필드**: `DKgen_ver`, `portdesc_make`, `mt_make`, `mt_cnt_ref_output`,
  `mt_cnt_ref_input` (liberty 파일 내용에 안 쓰이는 것으로 확인 완료 — 원본 스크립트에서
  주석/로그 전용이거나 별도 문서 생성/검증 임계값 용도였음)
- **Voltage Condition 테이블**: 더 이상 공정(technology)별 다중 행 테이블이 아님. 단일
  행으로, `BST High/Mid/Low`, `WST High/Mid/Low`, `TIV High/Mid/Low` 9칸을 사용자가
  직접 입력 (숫자만, 단위 없음). 코드에 기본값 하드코딩 안 함, config에만 저장. `TIV`는
  예전 "plain"(기술별 매칭용) 컬럼 자리를 대체.
- Port List의 Volts 컬럼과 매칭하는 로직(구 `build_pg_pin_rows`)은 **폐기**. voltage_map
  값은 이제 Step2에서 선택한 Voltage Condition으로 이 단일 테이블에서 직접 조회.

### Pin Settings
변경 없음 (`Virtual Power`, `Enable signal`, `Power down control signal`,
`DBS output signal`).

## 출력 파일명

```
{output_prefix}lpv_{cell_name}_{DBS 파일명에서 .mt0 뺀 것}.lib
```

liberty 내부의 `library (...)` 이름도 이 파일명에서 `.lib`만 뺀 문자열과 동일.

## Step 4 — Liberty 생성 (현재 구현 범위: `library ~ default_operating_conditions`)

cell/pin 본문(timing table 등)은 아직 미구현 (원본 스크립트의 해당 부분 이식 대기 중).

### 처리 순서
1. **Block 1 (헤더 주석)**: 기존과 동일한 포맷, `GENERATE OPTION` 블록만 완전히 삭제.
2. **Block 2-(1) (library 선언 + PDK 본문)**: 우리 쪽 `date`/`revision`/`comment`를 먼저
   쓴 뒤, PDK/DK 파일을 줄 단위로 스트리밍하며 `library (...) {` 다음부터 `voltage_map`
   직전까지 그대로 복사. **PDK 자체의 `date`/`revision`/`comment` 줄(줄 첫 토큰 기준)은
   순서/위치에 상관없이 만날 때마다 개별적으로 스킵** (중복 방지, 2026-08 확정).
3. **Block 2-(2) (voltage_map)**: Step2에서 이 pair에 선택된 Voltage Condition에 따라
   Step3 단일 테이블의 해당 3칸(High/Mid/Low)을 가져와 4줄을 **항상 전부** 작성
   (`VDD_low`, `VDD_high`, `VDD_middle`, `VSS_low_vmin`). `low_vmin`은 원본 Perl에서
   세 전압 레벨 블록 전부 `vmin: 0.00` 하드코딩으로 확인됨 → **항상 0.00 고정**.
4. **Block 2-(3) (operating_conditions)**: `nom_temperature`/`nom_voltage`는 Step2에서
   파일명 파싱으로 얻은 값. 괄호 안 library명은 PDK 파일도 우리 출력 파일도 아닌,
   **PDK 파일 내부 자신의 `operating_conditions(library명) { ... }` 선언에서 추출한 값**
   (voltage_map 근처에 위치, 스트리밍 중 계속 찾다가 발견하면 멈춤).

### 결측 데이터 처리
하드코딩되는 부분(예: `vmin: 0.00`, `process: 1.000`)을 제외하고, PDK 파일에서 기대한
값/줄을 못 찾으면 예외를 던지지 않고 빈 자리로 두되, 무엇이 어느 파일에서 빠졌는지
주석으로 표시:
```
####### operating_conditions library name is missing in {pdk_filename} #########
operating_conditions (<NOT_FOUND_IN_PDK>) {
```

### 성능/안정성
- PDK/DK 파일이 30만 줄 이상일 수 있음 → **`readlines()`로 전체를 메모리에 올리지 않고
  줄 단위로 스트리밍**, `voltage_map` 발견 즉시 읽기 중단.
- 여러 liberty를 동시에(병렬로) 생성하지 않음 — **한 번에 하나씩 순차 처리** (Step4 UI의
  1초 간격 tick 방식 유지).

## 아직 안 한 것 (TODO)
- Config export/import 기능, 프로그램 시작 시 초기화 — 코드에 TODO만 남김, 미구현.
- Cell/pin 본문 작성 (원본 스크립트 이식 대기).
- `process_prefix` 필드의 실사용 (cell/pin 작성 라운드부터).

## 실행 환경
- PyQt5는 Anaconda Python 3.7.6 (`/appl/CAEutil/LINUX/local/Anaconda/Anaconda3.7`)에서만
  동작 확인됨. `run_generator.sh`가 자동으로 이 환경으로 실행.
- `$DISPLAY` 필요 (X11 forwarding).