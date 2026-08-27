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

1. **PDK Folder**: `.lib` PDK/DK 파일들이 있는 폴더 — **확장자가 `.lib`로 시작하는 파일은
   전부 PDK 파일로 인식** (`.lib`, `.lib_css_tn`, 그 외 어떤 접미사가 붙어도 인식됨,
   2026-08 확정. 화이트리스트 방식이 아니므로 새로운 `.lib*` 계열 확장자가 추가돼도 코드
   변경 불필요)
2. **DBS Simulation Folder**: `.mt0` DBS output 파일들이 있는 폴더
3. **Port List (Excel)**: 핀 정보 (`Port` 컬럼이 `PORT`/`PWR`/`GND` 중 하나로 각 행을
   I/O·전원·접지 핀으로 분류)

## 파일명 규칙 (중요 — Step2 PDK/DBS 자동 추천의 기반)

- **PDK/DK**:
  `{공정명}lpv_[{??}_{??}_{??}_{??}_c{??}]_{corner}_{beol}_{min|max}_0p{volt}v_{temp}c_[{??}...].lib*`
  예: `cs17lpv_sc_d7p47t_flk_rvt_c90l14_ffpg_nominal_min_0p7500v_75c_lvf_dth.lib`
  - 대괄호 구간은 파일마다 있을 수도 없을 수도 있어 **토큰 개수가 고정되지 않는다**.
    그래서 위치(index)로 자르지 않고, `min|max` → `0p..v` → `..c` 세 토큰이 연달아
    오는 덩어리를 먼저 찾은 뒤 그 앞쪽에서 corner/beol을 읽는다.
  - beol은 여러 토큰일 수 있으므로 "corner 다음 ~ `min|max` 직전" 전체를 beol로 본다.
- **DBS output**: `{prefix}_0p{volt}v_{temp}c.mt0`
  예: `ffpg_nominal_0p7500v_75c.mt0`
- `0p{XXX}v` → `0.XXX` (`0p920v` → `0.920`, `0p7500v` → `0.7500`). 자릿수(3~4)가 달라도
  같은 값이면 같은 것으로 본다 — 부동소수점 대신 `Decimal`로 정확히 비교.
- temperature: `m{n}` → `-n`, `m` 없으면 그대로 양수 (`m40` → `-40`, `75` → `75`)
- **PDK 파일명의 beol 토큰은 사용자가 고른 beol inform과 다를 확률이 매우 크다**
  (2026-08 2차 재설계에서 확인). 그래서 추천 매칭의 **필수 조건은 corner + voltage +
  temperature 세 가지**뿐이고, beol 일치는 순위 가산점(`MATCH_EXACT`)으로만 쓴다.

## Step 1 — Setup & Validate

**PDK Folder → Port List (Excel) → DBS Simulation Folder** 순으로 3개 경로 입력 및 검증
(2026-08 순서 변경 — 화면 입력 순서와 Validate 단계 순서가 같다). 저장 파일
(`config/user_config.json`)은 key 기준 dict이므로 **순서를 바꿔도 기존 config를 그대로
쓴다**. Port List는 `.xls` / `.xlsx` 둘 다 허용하며, 허용 확장자 목록은
`field_defs.PORT_LIST_FILE_EXTENSIONS` 한 곳에서만 관리한다(파일 대화상자 필터, 화면
확장자 검사, `port_list_reader`의 읽기 분기가 전부 이 목록을 본다). `.xlsx`는 openpyxl,
`.xls`는 xlrd로 읽고, xlrd가 없으면 "무엇을 설치하면 되는지"가 그대로 Details에 뜬다.
설명 문구(구 노란 Note 배너)는 "Input Paths" 제목 옆 hover 정보 아이콘 툴팁으로 이동
(2026-08 레이아웃 개편).

## Step 2 — UDC Settings (2026-08 전면 재설계 → 2026-08 2차 재설계)

1차 재설계에서는 파일명 voltage+temperature로 PDK↔DBS를 자동 페어링해서 "짝이 맞는
파일 개수 = 만들 liberty 개수"로 삼았다. 그러나 실제로는 **PDK 폴더에 훨씬 많은 종류의
PDK 파일이 있고 DBS 파일은 그보다 적어서**, 자동 페어링만으로는 어떤 조합의 liberty를
만들지 결정할 수 없다는 것이 확인됐다 (2026-08 2차 재설계). 그래서 예전 UDC setting처럼
**liberty 파일 하나당 setting 1개를 사용자가 직접 추가**하는 방식으로 되돌아왔다.

**화면 레이아웃 (2026-08 개편)**: Step3처럼 좌우 2단. **왼쪽 = Common Fields + Voltage
Map**(Step3에서 이리로 옮겨옴), **오른쪽 = Liberty Settings**.

1. **공통 필드** (전체 조합에 1번만 입력, 1차 재설계 그대로): `area`, `width`, `height`,
   `static_current`, `cell_name`, `MC/HDA/OUT Timing State`
2. **Liberty Settings**: setting 1개 = liberty 파일 1개. 각 setting의 입력 항목은
   - `corner` — `ffpg`/`fsg`/`sfg`/`sspg`/`tt` 중 선택
   - `beol_inform` — `nominal`/`sigcmin`/`sigrcmin`/`sigrcmax`/`sigcmax` 중 선택
   - `voltage` — 숫자 입력 (화면에 `V` 단위 표시)
   - `temperature` — 숫자 입력 (화면에 `℃` 단위 표시, 파일명 토큰이 정수라 **정수만** 허용)
   - `condition` — **Voltage Map(같은 화면 왼쪽 열)에 정의된 voltage condition 이름**
     중 선택 (코드에 고정된 목록이 아님, 2026-08 사용자 정의 condition 재설계)
   - `pdk_file` — **Step1에서 인식된 모든 PDK 파일** 중 선택
   - `dbs_file` — PDK를 고르면 자동 매핑, 자동으로 못 고르면 직접 선택
3. **자동 추천**: corner/voltage/temperature를 입력하면 그 조건에 맞는 PDK 파일을 찾아
   드롭다운 **맨 위로 올리고 ★ + 초록 배경으로 highlight**한다 (beol까지 맞으면 굵게).
   구분선 아래에는 전체 목록을 그대로 두어, 추천이 틀렸을 때 직접 고를 수 있다.
   PDK를 고르면 같은 corner/voltage/temperature를 가진 `.mt0`를 자동 선택한다 — 후보가
   하나로 좁혀지지 않으면 비워 두고 사용자가 직접 고른다
   (`udc_field_defs.auto_select_dbs_file`).
4. **Validate**: PDK/DBS 폴더를 다시 스캔해서 ① 공통 필드가 전부 채워졌는지,
   ② setting이 1개 이상인지, ③ 각 setting의 7개 항목이 전부 빈 값 없이 채워졌는지
   (voltage/temperature는 숫자로 읽히는지), ④ 고른 PDK/DBS 파일이 **실제로 존재하는지**,
   ⑤ 같은 PDK/DBS 조합이 중복되지 않는지(같은 출력 파일을 두 번 쓰게 되므로) 검사.
5. 저장 형식: `config/udc_settings.json`의 `liberty_settings` 배열
   (`{id, corner, beol_inform, voltage, temperature, condition, pdk_file, dbs_file}`).
   구 `pair_settings` key는 폐기. `condition` 값은 이제 voltage condition **이름**이며,
   예전 config의 `"bst"`는 기본 이름 `"BST"`와 대소문자만 다르므로 그대로 이어서 쓴다
   (드롭다운을 채울 때/생성할 때 모두 대소문자 무시로 매칭).

### Voltage Map (2026-08 Step3 → Step2 이동 + 사용자 정의 condition)
- **사용자가 voltage condition을 원하는 만큼 추가/삭제하고 이름도 직접 정한다.** config에
  아무것도 없을 때만 기본으로 `BST`/`WST`/`TIV` 세 개가 만들어진다(예전에는 이 셋으로
  고정이었다). condition 개수가 많아질 수 있어 카드마다 **접기/펴기**가 있고, 접으면
  헤더 오른쪽에 값 요약(`0.9 / 2.2 / 1.8`)이 보인다. "Collapse all"로 한 번에 접는다.
- condition 하나 = `{"id", "name", "values": {"type1": 값, "type2": ..., "type3": ...}}`.
- **Power Type 정책은 기존 그대로**: 개수는 2~3 조절(기본 3), 대표 전압
  (0.8V/2.2V/1.8V)은 block4에서 Port List Volts를 Power Type에 매칭시키는 고정 임계값,
  Power Type별 voltage name은 condition 구분 없이 Power Type당 하나.
- **저장 위치는 예전 그대로** `config/step3_settings.json`의 `voltage_map` key다(화면만
  옮겨졌다). 구조: `{power_type_count, conditions: [...], names: {power_type1_name, ...}}`.
  예전 config의 `values: {"bst_type1": ...}` 형태는 로드 시 BST/WST/TIV 세 condition으로
  자동 변환된다(`settings_manager._migrate_legacy_conditions`). Step2가 이 부분만
  갈아끼우므로(`save_voltage_map`) Step3에서 입력한 다른 값은 그대로 남는다.
- Step2 Validate가 Voltage Map도 함께 검사한다: condition 1개 이상, 이름이 비어있지
  않고 서로 중복되지 않을 것(대소문자 무시), 현재 Power Type 개수만큼의 값이 전부 숫자,
  그 개수만큼의 voltage name이 전부 채워져 있을 것.

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
- **`Worst case primitive liberty`** (신규): 드롭다운. 후보는 **Step2의 liberty
  setting들이 실제로 고른 PDK 파일들뿐**이다 (2026-08 2차 재설계 — 예전에는 파일명 자동
  페어링이 성립한 PDK 목록이었다). 위 `lu_table_template`은 **liberty마다 각자의 PDK에서
  찾지 않고, 여기서 고른 PDK 하나에서 실행당 딱 한 번만 읽어 생성하는 모든 liberty에
  그대로 재사용**한다 (2026-08 확정).
- **삭제된 필드**: `DKgen_ver`, `portdesc_make`, `mt_make`, `mt_cnt_ref_output`,
  `mt_cnt_ref_input` (liberty 파일 내용에 안 쓰이는 것으로 확인 완료 — 원본 스크립트에서
  주석/로그 전용이거나 별도 문서 생성/검증 임계값 용도였음)
- **Voltage Map은 Step 2로 이동**했다 (2026-08). 화면/데이터 구조 설명은 위 "Step 2 —
  Voltage Map" 절 참고. 저장 위치만 여전히 `config/step3_settings.json`의 `voltage_map`
  key이며, 이 화면은 설정을 저장할 때 그 부분을 **덮어쓰지 않고 파일에서 다시 읽어 그대로
  둔다**(`settings_view._collect_all`).

### Pin Settings (2026-08 연계 입력 추가)
상위 pin 입력 3개는 각각 "그 pin을 입력했기 때문에 같이 입력해야 하는" 하위 필드를
갖는다. 화면에서도 상위 pin 바로 아래에 세로선 + 들여쓰기로 묶어서 보여준다.
**상위 pin 라벨(DBS output pin / Virtual Power / Power down control signal)은 하위
필드보다 크고 굵게**(15px/700) 써서 상위단임이 바로 보이게 하고, 반대로 연계 그룹의
보라색 시스템 안내 문구("These are required because ...")는 `QGraphicsOpacityEffect`로
투명도를 낮춰(0.55) 입력값보다 덜 튀게 한다 (2026-08).

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
  `LUT Table`이 비어있지 않은지, `Worst case primitive liberty`가 선택돼 있고 **Step2의
  liberty setting들이 고른 PDK 목록 안에 있는지**. (Voltage Map 검사는 Step2로 이동 —
  `settings_validator.validate_voltage_map`)
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

**생성된 파일 열기 (2026-08 추가)**: 파일 아이콘을 클릭하면 그 liberty 파일이 **새 창**에
읽기 전용으로 열린다 — 어두운 배경 + 고정폭 글꼴 + 줄번호 + vim 상태줄이고, j/k/h/l,
g/G, Ctrl+D/U로 이동하고 q 또는 Esc로 닫는다 (`ui/file_viewer.py`). 실제 `vi`/`vim`
프로세스를 띄우려면 터미널 에뮬레이터가 필요해 X11 forwarding 환경에서 보장할 수 없어서,
**앱 안에 같은 느낌의 뷰어 창을 직접 구현**했다(편집/저장은 지원하지 않음). 아주 큰
파일은 앞부분 20만 줄까지만 읽고 상태줄에 잘렸다고 표시한다.

**Back 버튼 (2026-08 추가)**: Step4에서 Step3으로 돌아갈 수 있다. 생성이 진행되는 동안
에는 잠기고(예약된 tick이 어중간한 상태에서 계속 파일을 쓰는 것을 막기 위해), 끝나면
다시 열린다. Step3으로 돌아가면 `SettingsView.showEvent`가 DBS output pin Check 결과를
무효화하므로 **Check → Validate → Generate 순서를 처음부터 다시 밟아야 하고**, Generate를
다시 누르면 `GenerateView.start()`가 처음부터 다시 실행되어 몇 번이든 재생성할 수 있다.

### 처리 순서
1. **Block 1 (헤더 주석)**: 기존과 동일한 포맷, `GENERATE OPTION` 블록만 완전히 삭제.
2. **Block 2-(1) (library 선언 + PDK 본문)**: 우리 쪽 `date`/`revision`/`comment`를 먼저
   쓴 뒤, PDK/DK 파일을 줄 단위로 스트리밍하며 `library (...) {` 다음부터 `voltage_map`
   직전까지 그대로 복사. **PDK 자체의 `date`/`revision`/`comment` 줄(줄 첫 토큰 기준)은
   순서/위치에 상관없이 만날 때마다 개별적으로 스킵** (중복 방지, 2026-08 확정).
3. **Block 2-(2) (voltage_map)** (2026-08 Voltage Map 재설계): Step2에서 이 liberty에
   선택된 voltage condition 이름으로 Voltage Map에서 그 condition을 찾아(대소문자 무시)
   Power Type1..N 값을 가져와, **power type 개수만큼의 VDD 줄 + VSS 1줄**을 항상 전부 작성한다.
   VDD 줄은 `voltage_map (VDD_{power type voltage name}, {value}) ;` 형태로, 이름은
   그 Power Type에 입력한 voltage name을 그대로 쓴다(값이 아니라 이름만 -
   block4 pg_pin의 `voltage_name`과 정확히 일치해야 하므로). VSS 줄은 기존과 동일
   (`voltage_map (VSS_0.00000, 0.00000) ;`, 하드코딩).
4. **Block 2-(3) (operating_conditions)**: `nom_temperature`/`nom_voltage`는 **Step2에서
   사용자가 직접 입력한 voltage/temperature 값**을 그대로 쓴다 (2026-08 2차 재설계 확정 —
   예전에는 파일명 파싱 결과를 썼다. 보통 같은 값이 나오지만, 파일명 규칙에서 벗어난
   파일을 고르는 경우까지 고려한 것이다). 괄호 안 library명은 PDK 파일도 우리 출력 파일도 아닌,
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
- Port List 파싱 캐싱/조기 종료/백그라운드 스레드 이관 — Step1 Validate와 Step3
  Output Path 대화상자가 느린 근본 원인(위 "Ctrl+C 강제 종료" 절 참고)의 실제 해결책.
  지금은 Ctrl+C 강제 종료로 안전장치만 마련한 상태.

(해결됨) block5의 `max_capacitance` — 2026-08 확정: **worst case primitive liberty에서
읽은 `lu_table_template`의 `index_2` 마지막 값**을 그대로 쓴다
(`pdk_stream_reader.parse_index_last_value`). index_2를 못 찾은 경우에만 예전처럼
결측 주석 + `#max_capacitance : No Answer;`로 남긴다.

(해결됨) block4 pg_pin의 `switch_function` / `pg_function` 하드코딩 TODO — 2026-08에
Step3 Pin Settings의 연계 입력으로 대체되어 제거됨.

## Ctrl+C 강제 종료 (2026-08 추가)

Step1의 Port List 파싱, Step3의 Output Path 파일 대화상자(네트워크 폴더 탐색) 등에서
화면이 완전히 멈춘 것처럼 보이는 경우를 대비해, **어느 Step 화면에서든 Ctrl+C를 누르면
프로세스를 즉시 하드킬**한다 (`ui/force_quit.py`, `gui_app.MainWindow.__init__`에서
`install_force_quit()` 한 번 호출).

- GUI가 응답 가능한 동안(이벤트 루프가 돌고 있음): QApplication 전체에 건 이벤트
  필터가 모든 KeyPress를 가로채 Ctrl+C를 직접 잡는다. 처음엔 `QShortcut` +
  `Qt.ApplicationShortcut`로 구현했는데, 이 방식은 Qt가 내부적으로 판단하는 "활성
  창" 상태에 의존하다 보니 일부 창관리자/X11 forwarding 조합에서 창을 띄워도 그
  플래그가 안 서서 단축키가 조용히 먹통이 되는 게 실측으로 확인되어(2026-08),
  그 판단 자체를 거치지 않는 이벤트 필터 방식으로 바꿨다.
- 터미널에서 SIGINT(Ctrl+C)가 온 경우도 `signal.signal(SIGINT, ...)`로 받는다. Qt
  이벤트 루프는 idle 대기 중 파이썬 바이트코드를 실행하지 않아 시그널을 처리할
  기회가 없으므로, 짧은 주기(200ms)로 아무 일도 안 하는 `QTimer`를 돌려 계속
  파이썬에 제어권을 돌려준다(PyQt에서 터미널 Ctrl+C가 안 먹는 문제의 표준 우회법).
- 두 경로 모두 `os._exit()`로 그 자리에서 즉시 끝낸다 - 정리/저장 시도 없음.
- Step1/Step3의 파일 대화상자는 `QFileDialog.DontUseNativeDialog`를 켜서 OS 고유
  대화상자가 아니라 이 앱과 같은 이벤트 루프를 쓰는 Qt 대화상자를 띄운다 - 그래야
  대화상자가 열려 있는 동안에도 이벤트 필터가 Ctrl+C를 받을 수 있다.
- **한계**: 위 두 경로 모두 "다음 파이썬 바이트코드가 실행되는 시점"에 들어오므로,
  메인 스레드가 순수 파이썬 루프(예: 큰 Excel 파일을 openpyxl로 파싱하는 도중)를
  실행하는 동안은 GUI에 포커스를 두고 누르는 Ctrl+C(이벤트 필터 경로)가 그 루프가
  끝날 때까지 처리되지 못한다 - Qt 창은 그 순간 키 입력은 물론 닫기 버튼까지 전부
  응답하지 않기 때문. 반면 **터미널 SIGINT는 이 경우에도 즉시 먹힌다**(파이썬
  바이트코드 사이사이에 체크되므로) - 실측으로 12MB급 인위적 대형 xlsx 파싱 도중
  SIGINT를 보내 1.5초 만에 강제 종료되는 것까지 확인함. 앱은 항상 `run_generator.sh`로
  터미널에서 띄워지므로, 진짜 멈춘 것 같으면 그 터미널에서 Ctrl+C를 누르는 게 가장
  확실한 탈출구다.
- Ctrl+C를 앱 전역에서 가로채므로 텍스트 입력칸의 Ctrl+C 복사 단축키는 더 이상 쓸 수
  없다(우클릭 메뉴의 Copy로 대체).

### 근본 원인 (Step1 Port List / Step3 Output Path가 느린 이유)

- **Port List 파싱**: `port_list_reader._load_sheet_rows()`가 openpyxl
  `read_only` 모드로 `[[cell.value for cell in row] for row in sheet.iter_rows()]`를
  실행해 시트 전체를 한 번에 파이썬 리스트로 통째로 올린다. 실제 엔지니어링 Excel은
  서식(테두리/색 등)이 열/행 전체에 걸쳐 적용된 경우가 흔해서, `dimensions`
  (사용 범위)가 실제 데이터보다 훨씬 크게 잡히는 일이 매우 흔하다 - 실측으로 헤더
  2줄만 있고 60만 번째 행 한 칸에만 값이 있는 파일을 만들었더니 `ws.dimensions`가
  `A1:DP600000`(약 7천만 셀)이 되고, 파싱에 수 초가 걸렸다. 게다가 **캐시가 전혀
  없어서** `read_port_list`/`read_port_list_rows`/`list_pins_by_port_type`/
  `list_port_bit_values`/`list_power_ground_pins`/`list_port_pins_detailed`/
  `list_all_pin_names`가 각각 파일을 처음부터 다시 열고 다시 파싱한다 - Step1
  Validate 한 번뿐 아니라 Step2(Virtual Power 콤보)/Step3(Check/Validate/Virtual
  Power 콤보)/Step4(Generate)에서도 매번 똑같은 비용을 반복해서 치른다. 이 모든
  파싱이 GUI 메인 스레드에서 동기로 실행되므로, 그동안 창이 완전히 응답하지 않는다.
- **Output Path 대화상자**: `QFileDialog.getExistingDirectory(self, "Select Output
  Path")`가 시작 폴더 힌트 없이 호출되어, OS 고유(대개 GTK) 대화상자가 마지막 사용
  폴더/즐겨찾기/마운트된 네트워크 공유까지 미리 훑는다. 이 프로젝트가 돌아가는
  "사내 HPC망 VWP" 환경처럼 네트워크 마운트 스토리지가 느리면 이 훑기 자체가 오래
  걸리고, 완전히 별개의 네이티브 툴킷 루프라 우리 앱 코드로는 제어할 수 없었다
  (2026-08부터 `DontUseNativeDialog`로 Qt 자체 대화상자를 쓰도록 바꿔서 최소한 Ctrl+C
  이벤트 필터가 열려 있는 동안에도 도달하게는 했다).
- **완전한 해결책은 아직 미구현**: 무거운 파싱을 캐싱하고(같은 파일이면 재사용),
  진짜 데이터 이후의 완전 공백 구간에서 조기 종료하고, 백그라운드 스레드로 옮겨
  진행률/취소 UI를 붙이는 것 - 코드에 TODO만 남겨두고 아직 하지 않음(아래 "아직 안 한
  것" 참고).

## Step 이동 규칙 (2026-08 확정)

**어느 Step이든 Back으로 돌아오면 그 Step은 반드시 다시 Validate해야 한다.** 각 화면의
`showEvent`가 검사 결과를 무효화한다:
- Step1: 스텝 인디케이터/Details 초기화 + Next 잠금 (`SetupView._invalidate_validation`)
- Step2: Next 잠금 (`UDCView._lock_next`) + PDK/DBS 재스캔
- Step3: DBS output pin Check 결과 무효화 → Validate/Output Path/Generate 잠금
Next(또는 Generate)는 그 Step의 Validate를 통과하기 전까지 항상 disabled이고, 잠긴
버튼에는 "Run Validate first." 툴팁이 붙는다.

## UI 레이아웃 규칙 (2026-08 레이아웃 개편)

- 창 기본 크기는 `ui/theme.py`의 `WINDOW_DEFAULT_WIDTH/HEIGHT`(1560x1000), 최소 크기는
  `WINDOW_MIN_WIDTH/HEIGHT`(1180x760).
- **설명은 화면에 문단으로 깔지 않고 hover 정보 아이콘 툴팁으로 접는다.**
  `ui/ui_common.py`의 `InfoIcon` / `build_section_header(title, info)` /
  `build_label_with_info(label, info)`를 쓴다. 예전에는 각 항목마다 hint 문단과 노란
  배너를 깔아둬서, Step3의 `1) Check DBS Output Pins` 버튼이 한참 스크롤을 내려야
  보였다.
- Step2는 좌우 2단(왼쪽 Common Fields + Voltage Map / 오른쪽 Liberty Settings),
  Step3도 좌우 2단(왼쪽 Constants / 오른쪽 Pin Settings)이고, **열마다 따로 스크롤**을
  준다(전체를 한 스크롤로 감싸면 오른쪽 열의 Check 버튼이 다시 밀려 내려간다). 가로
  스크롤은 끄고(`ScrollBarAlwaysOff`) 폼은 `WrapLongRows` +
  `AllNonFixedFieldsGrow`로 열 폭에 맞춰 줄어들게 한다.
- Step3의 Pin Settings 안에서는 **DBS output pin + Check 블록이 맨 위**다 (Validate보다
  먼저 눌러야 하는 것이 화면에서도 먼저 보이도록).
- 카드(흰 배경) 안에 레이아웃용 빈 `QWidget`을 넣을 때는 `setObjectName("transparentRow")`
  를 붙인다 — 전역 `QWidget` 배경색(회색)이 그대로 칠해져 회색 띠처럼 보이는 것을 막는다.

## 실행 환경
- PyQt5는 Anaconda Python 3.7.6 (`/appl/CAEutil/LINUX/local/Anaconda/Anaconda3.7`)에서만
  동작 확인됨. `run_generator.sh`가 자동으로 이 환경으로 실행.
- `$DISPLAY` 필요 (X11 forwarding).