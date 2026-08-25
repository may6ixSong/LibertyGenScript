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
  출력 파일명에 사용, 아래 참고), `DFF Cell Name`, `LUT Table`,
  `Worst case primitive liberty`
- **`LUT Table`**: 예전 화면 라벨 `Primitive Cell Name`을 이름만 바꾼 것 (config key는
  호환 때문에 `primitive_cell_name` 그대로). block3의 `lu_table_template`
  index_1/index_2를 PDK/DK 파일에서 찾을 때, `cell (DFF Cell Name)` 선언 다음으로 이
  이름이 처음 등장하는 `cell_rise`/`cell_fall` 블록을 쓴다.
- **`Worst case primitive liberty`** (신규): 드롭다운. 후보는 **Step2에서 DBS output과
  1:1 pair가 성립한 PDK 파일들뿐**이다. 위 `lu_table_template`은 **pair마다 각자의
  PDK에서 찾지 않고, 여기서 고른 PDK 하나에서 실행당 딱 한 번만 읽어 생성하는 모든
  liberty에 그대로 재사용**한다 (2026-08 확정).
- **삭제된 필드**: `DKgen_ver`, `portdesc_make`, `mt_make`, `mt_cnt_ref_output`,
  `mt_cnt_ref_input` (liberty 파일 내용에 안 쓰이는 것으로 확인 완료 — 원본 스크립트에서
  주석/로그 전용이거나 별도 문서 생성/검증 임계값 용도였음)
- **Voltage Map** (2026-08 재설계, 구 "Voltage Condition"): `BST`/`WST`/`TIV` 세 그룹
  각각에 대해 `Power Type1`~`PowerType{N}` 전압 값을 세로로 입력받는다 (숫자만, 단위
  없음). `N`(Power Type 개수)은 화면의 스핀박스로 **2~3 사이 조절 가능**(기본 3) —
  과제에 따라 Power Type이 2개(예전 표현으로 "High/Low"만)뿐일 수 있기 때문. 예전
  "High/Mid/Low"는 정확한 용어가 아니라서 폐기했고, 각 Power Type 라벨에는 그 type의
  TIV 대표 전압을 괄호로 표시한다(`Power Type1 (0.8V)` / `Power Type2 (2.2V)` /
  `Power Type3 (1.8V)`) — 실제 BST/WST/TIV 값은 사용자가 자유롭게 조정 가능하고, 이
  대표값은 이름을 정하기 위해 고른 값일 뿐이다. 값 입력 필드는 이 대표값으로 미리
  채워진 채 시작한다(과거 "전부 빈 값" 방침에서 변경). 저장 key: `voltage_map` =
  `{power_type_count, values: {bst_type1, ..., tiv_type3}, names: {power_type1_name,
  ...}}` (`step3_settings/constants_field_defs.py`).
- Power Type마다 **voltage name**도 하나씩 입력받는다 (BST/WST/TIV 공통 - group별로
  따로 있지 않음). 이 이름은 block2의 `voltage_map` 이름과 block4 pg_pin의
  `voltage_name`을 매칭시키는 데 쓰인다 (아래 Step4 참고).
- Port List의 Volts 컬럼과 매칭하는 로직(구 `build_pg_pin_rows`)은 **폐기**. block2의
  voltage_map 값은 이제 Step2에서 선택한 bst/wst/tiv 그룹에 따라 이 Voltage Map
  표에서 직접 조회.

### Pin Settings (2026-08 연계 입력 추가)
상위 pin 입력 3개는 각각 "그 pin을 입력했기 때문에 같이 입력해야 하는" 하위 필드를
갖는다. 화면에서도 상위 pin 바로 아래에 세로선 + 들여쓰기로 묶어서 보여준다.

1. **Virtual Power (power gate)** (Port List의 PWR pin 드롭다운)
   - `Enable Signal for power gate` — 와일드카드 허용 (기존과 동일하게 사용)
   - `Virtual Power Switch Function` — **와일드카드 불가**. block4 pg_pin의
     `switch_function` 값으로 그대로 들어감.
   - `Virtual Power PG Function` — **와일드카드 불가**. block4 pg_pin의 `pg_function`
     값으로 그대로 들어감. (이 둘은 예전에 코드에 하드코딩되어 TODO로 남아 있던 값이다.)
2. **Power down control signal** (와일드카드 허용)
   - `rise power` / `fall power` / `when` — block5의
     `{prefix}_acore_internal_power` 블록에 들어감. 기본값은 예전 하드코딩 값
     (`30000000.0000` / `0.0` / `"1"`).
3. **DBS output pin** (와일드카드 허용)
   - `timing_sense` / `timing_type` — 인식된 DBS output pin **전체 공통 1쌍**,
     block5의 `timing()` 블록에 들어감. 기본값은 예전 하드코딩 값
     (`non_unate` / `combinational`).
   - 인식된 pin마다 `related pin` 하나씩 — block5 `timing()`의 `related_bus_pins`.

**Check가 Validate보다 항상 먼저 (2026-08 확정)**: Port List 파일이 바뀌면 같은
와일드카드라도 인식되는 DBS output pin 집합이 달라진다. 그래서 화면에
`1) Check DBS Output Pins` 버튼을 두고, 이걸 눌러 **현재 Port List 기준으로 pin을 다시
펼친 뒤에야** 각 pin의 related pin을 입력할 수 있고 `2) Validate` 버튼이 열린다. DBS
output pin 입력을 고치거나 화면을 다시 열면(Step1에서 Port List를 바꿨을 수 있으므로)
Check 결과는 무효가 되고 Validate가 다시 잠긴다. 와일드카드가 인식하는 대상은
block5에서 실제로 `pin()`/`bus()`로 쓰이는 행들과 동일하게 `Port == "PORT"`인 행뿐이다.

### Step 3 Validate 검사 항목
- Constants: `class` / `process_prefix` / `output_prefix` / `DFF Cell Name` /
  `LUT Table`이 비어있지 않은지, `Worst case primitive liberty`가 선택돼 있고 **현재
  1:1 pair가 성립하는 PDK 목록 안에 있는지**, Voltage Map의 BST/WST/TIV x
  Power Type1..N(현재 power type 개수만큼만) 값이 전부 채워진 숫자인지, 그 개수만큼의
  voltage name이 전부 채워져 있는지.
- Pin: 위의 모든 하위 필드가 비어있지 않은지(rise/fall power는 숫자인지), 와일드카드
  불가 필드에 `*`가 없는지, Virtual Power가 PWR pin인지, Enable/Power down 패턴이 실제
  pin과 매치되는지.
- DBS output pin의 related pin: **① Check로 인식해 둔 pin 집합이 지금 Port List로 다시
  펼친 결과와 같은지** (다르면 "다시 Check" 에러), ② 각 related pin이 비어있지 않은지,
  ③ Port List에 실제 존재하는 Pin name인지, ④ **그 DBS output pin이 있는 Port List 행의
  `Related Pin` 컬럼 값과 정확히 일치하는지** (예: 입력이 `A`인데 Port List 값이 `AA`면
  에러, `A`라는 pin이 Port List에 아예 없어도 에러).

## 출력 파일명

```
{output_prefix}lpv_{cell_name}_{DBS 파일명에서 .mt0 뺀 것}.lib
```

liberty 내부의 `library (...)` 이름도 이 파일명에서 `.lib`만 뺀 문자열과 동일.

## Step 4 — Liberty 생성

### 처리 순서
1. **Block 1 (헤더 주석)**: 기존과 동일한 포맷, `GENERATE OPTION` 블록만 완전히 삭제.
2. **Block 2-(1) (library 선언 + PDK 본문)**: 우리 쪽 `date`/`revision`/`comment`를 먼저
   쓴 뒤, PDK/DK 파일을 줄 단위로 스트리밍하며 `library (...) {` 다음부터 `voltage_map`
   직전까지 그대로 복사. **PDK 자체의 `date`/`revision`/`comment` 줄(줄 첫 토큰 기준)은
   순서/위치에 상관없이 만날 때마다 개별적으로 스킵** (중복 방지, 2026-08 확정).
3. **Block 2-(2) (voltage_map)** (2026-08 Voltage Map 재설계): Step2에서 이 pair에
   선택된 bst/wst/tiv 그룹에 따라 Step3 Voltage Map 표의 해당 그룹 Power Type1..N
   값을 가져와, **power type 개수만큼의 VDD 줄 + VSS 1줄**을 항상 전부 작성한다.
   VDD 줄은 `voltage_map (VDD_{power type voltage name}, {value}) ;` 형태로, 이름은
   Step3에서 그 Power Type에 입력한 voltage name을 그대로 쓴다(값이 아니라 이름만 -
   block4 pg_pin의 `voltage_name`과 정확히 일치해야 하므로). VSS 줄은 기존과 동일
   (`voltage_map (VSS_0.00000, 0.00000) ;`, 하드코딩).
4. **Block 2-(3) (operating_conditions)**: `nom_temperature`/`nom_voltage`는 Step2에서
   파일명 파싱으로 얻은 값. 괄호 안 library명은 PDK 파일도 우리 출력 파일도 아닌,
   **PDK 파일 내부 자신의 `operating_conditions(library명) { ... }` 선언에서 추출한 값**
   (voltage_map 근처에 위치, 스트리밍 중 계속 찾다가 발견하면 멈춤).
5. **Block 4 pg_pin의 `voltage_name`** (2026-08 Voltage Map 재설계): 예전에는 항상
   Port List Volts 값을 그대로 포맷(`VDD_0.80000`)해서 썼지만, 이제 그 Volts 값이
   Power Type 대표 전압(0.8V/2.2V/1.8V, power type 개수가 2면 1.8V는 매칭 대상에서
   제외)과 일치하면 그 Power Type의 voltage name을 대신 쓴다(`VDD_{voltage name}` -
   block2가 쓴 voltage_map 이름과 정확히 같아야 리버티 문법상 유효하므로). 일치하는
   Power Type이 없으면 기존처럼 `VDD_{value}` 그대로. 매칭 기준은 **고정 임계값**이며
   Step3에서 BST/WST/TIV 표의 값을 조정해도 바뀌지 않는다 (`block4_writer.py`의
   `_voltage_name_text`, `liberty_assembler.build_job`의 `voltage_name_thresholds`).

### 결측 데이터 처리
하드코딩되는 부분(예: `vmin: 0.00`, `process: 1.000`)을 제외하고, PDK 파일에서 기대한
값/줄을 못 찾으면 예외를 던지지 않고 빈 자리로 두되, 무엇이 어느 파일에서 빠졌는지
주석으로 표시:
```
####### operating_conditions library name is missing in {pdk_filename} #########
operating_conditions (<NOT_FOUND_IN_PDK>) {
```

### 성능/안정성 (2026-08 재설계)
- PDK/DK 파일이 30만 줄 이상일 수 있음 → **`readlines()`로 전체를 메모리에 올리지 않고
  줄 단위로 스트리밍**하며, 필요한 걸 다 얻는 즉시 읽기를 중단한다.
- PDK 읽기는 두 갈래로 완전히 분리되어 있다 (`pdk_stream_reader.py`):
  1. `read_pdk_library_sections(pdk_path)` — **liberty 하나당 한 번**, block2용.
     library 선언 / 본문 / `operating_conditions` 이름 / `input_voltage` /
     `output_voltage`만 필요하고 이것들은 전부 첫 `cell (...)` 선언보다 앞에 있으므로,
     **첫 cell 선언을 만나는 즉시 중단**한다. 파일의 대부분(cell 본문 수십만 줄)은 아예
     읽지 않는다.
  2. `read_lut_table_sections(pdk_path, dff, lut)` — **실행당 한 번**, block3용.
     Step3에서 고른 worst case PDK 하나에서만 읽고, index_1/index_2를 찾는 즉시 중단.
     결과는 모든 job이 그대로 재사용한다.
- `write_liberty_file()`은 block2를 다 쓴 직후 `sections.clear()`로 PDK에서 읽어온 값
  (특히 `body_lines`)을 즉시 놓아준다 — block5의 timing 표 작성이 그 뒤에 이어지므로
  그때까지 붙들고 있을 이유가 없다.
- 여러 liberty를 동시에(병렬로) 생성하지 않음 — **한 번에 하나씩 순차 처리** (Step4 UI의
  1초 간격 tick 방식 유지).

## 아직 안 한 것 (TODO)
- Config export/import 기능, 프로그램 시작 시 초기화 — 코드에 TODO만 남김, 미구현.
- block5의 `#max_capacitance : No Answer;` — 실제로 어떤 값을 써야 하는지 아직 확인
  안 됨 (코드에 TODO 주석으로 남아 있음).

(해결됨) block4 pg_pin의 `switch_function` / `pg_function` 하드코딩 TODO — 2026-08에
Step3 Pin Settings의 연계 입력으로 대체되어 제거됨.

## 실행 환경
- PyQt5는 Anaconda Python 3.7.6 (`/appl/CAEutil/LINUX/local/Anaconda/Anaconda3.7`)에서만
  동작 확인됨. `run_generator.sh`가 자동으로 이 환경으로 실행.
- `$DISPLAY` 필요 (X11 forwarding).