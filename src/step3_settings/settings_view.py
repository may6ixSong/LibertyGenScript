"""
settings_view.py

'Constants & Pin Settings' 화면 (Step 3, 2026-08 재설계 -> 2026-08 레이아웃 개편):
상수 값(class/process_prefix/output_prefix/DFF Cell Name/LUT Table/Worst case primitive
liberty)과 Pin 설정을 입력받는다.

2026-08 Voltage Map 이동: Voltage Map은 **Step 2 왼쪽 열**로 옮겨졌다(사용자가 voltage
condition을 직접 추가/삭제하고 이름도 정하는 형태로 바뀜, step2_udc/voltage_map_view.py).
저장 위치는 예전 그대로 step3_settings.json의 voltage_map key이므로, 이 화면이 설정을
저장할 때는 그 부분을 화면 값으로 덮어쓰지 않고 파일에서 다시 읽어 그대로 둔다.

2026-08 레이아웃 개편 - "Check가 안 보인다" 문제 해결:
  이전에는 Constants 카드와 Pin Settings 카드를 세로로 이어 붙이고 각 항목마다 설명
  문단(hint)을 그대로 깔아둬서, 정작 Validate보다 먼저 눌러야 하는
  "1) Check DBS Output Pins" 버튼이 한참 스크롤을 내려야 보였다. 그래서:
    - 화면을 좌우 2단(왼쪽 Constants / 오른쪽 Pin Settings)으로 나눴고,
    - Pin Settings 안에서도 DBS output pin + Check 블록을 **맨 위**로 올렸으며,
    - 모든 설명 문단은 제목/라벨 옆 hover 정보 아이콘(InfoIcon)의 툴팁으로 옮겼다.
  창 기본 너비도 함께 넓혔다 (ui/theme.py의 WINDOW_DEFAULT_WIDTH).

2026-08 추가 - 연계 입력(linked group):
  Virtual Power / Power down control signal / DBS output pin 세 개는 각각 "그 pin을
  입력했기 때문에 추가로 같이 입력해야 하는" 하위 필드들을 갖는다. 화면에서도 상위 pin
  바로 아래에 세로선 + 들여쓰기로 묶어서(_build_linked_group) 연계 관계가 한눈에
  보이도록 한다.

2026-08 추가 - DBS output pin은 Validate 전에 반드시 Check 먼저:
  Port List 파일이 바뀌면 같은 와일드카드라도 인식되는 pin 집합이 달라지므로,
  "1) Check DBS Output Pins" 버튼을 눌러 현재 Port List 기준으로 pin을 다시 펼친 뒤에야
  Data Transfer Type을 고르고(Parallel이면 pin마다 Number of Col도 입력, Serial이면
  Serial Cluster를 고르고 "More than 1"이면 공유 Number of Col/Related Pin 와일드카드도
  입력)할 수 있고, 그 다음에야 "2) Validate" 버튼이 열린다.
  DBS output pin 입력을 고치거나 화면을 다시 열면 Check 결과는 무효가 되고 Validate가
  다시 잠긴다. Step4에서 Back으로 돌아온 경우도 마찬가지다(showEvent).

2026-08 추가 - DBS output pin bit 분할 → 2026-08 재설계(Number of Col):
  Related Pin은 더 이상 표에서 수정할 수 없다 - Check 시점에 Port List의 'Related Pin'
  컬럼 값으로 고정된다(단, Serial Cluster "More than 1"에서는 아래 절 참고 - Related
  Pin 자체가 pin마다가 아니라 공유 와일드카드로 바뀐다). Parallel에서는 표에 DBS
  Bits / Related Bits(둘 다 Port List의 'Bits' 컬럼에서 읽음, pin명의 '[N:0]' 파싱보다
  정확함)를 함께 보여주고, 사용자는 "Number of Col (#)"(옛 "Bit Depth"/"Split into
  (bits)")만 입력한다 - **Related Pin의 총 Bits**를 그 값으로 나눈 몫이 cluster
  개수다(2026-08 재설계 - 예전에는 DBS output pin 쪽을 나눴다). 그 DBS output pin
  자신의 Bits가 그 몫으로 나누어떨어진 값(cluster당 DBS output pin 자신의 Bit Depth)은
  사용자가 입력하지 않고 자동 계산되며, 어느 한쪽이든 나누어떨어지지 않으면 Validate가
  막는다(settings_validator._validate_dbs_related_pins, block5_writer._dbs_bit_split_groups).

2026-08 변경 - DBS output pin 표시: 표(QTableWidget) -> 카드 -> 일반 폼:
  컬럼이 6개(DBS Output Pin/Bits/Related Pin/Related Bits/Number of Col/Result)로
  늘어나면서 표 칸이 너무 좁아 값이 잘려 보인다는 피드백을 받아, 1차로 pin마다
  entryCard 스타일 박스 목록으로 바꿨다. 그런데 박스+스크롤 구성도 여전히 "표 같다"는
  피드백을 다시 받았고, 실제로 인식되는 DBS output pin은 보통 1~2개뿐이라 스크롤이나
  박스로 감쌀 이유가 없었다. 그래서 2차로 **박스/스크롤을 걷어내고, 화면의 다른
  입력들과 똑같은 `QFormLayout` 흐름**으로 더 단순화했다(`_build_dbs_pin_section`):
  pin마다 굵은 제목 줄(이름 + Bits) 하나, 그 아래 `QFormLayout` 두 행("Related Pin"은
  읽기 전용 텍스트, "Number of Col (#)"는 입력칸 + 그 바로 아래 계산 결과 문구) -
  Number of Col을 뺀 나머지는 전부 시스템이 채워주는 값이므로 굳이 표/카드처럼
  별도 시각 단위로 감싸지 않고, 이 화면의 timing_sense/timing_type 같은 다른 입력
  행과 같은 방식으로 보여준다. pin이 둘 이상이면 사이에 얇은 구분선만 넣는다.

2026-08 추가 - Data Transfer Type (Parallel/Serial):
  Check 성공 후, 인식된 pin 전체에 공통으로 적용되는 라디오 버튼 선택
  (`dbs_transfer_type_row`, pin마다가 아니라 한 번만 고른다) - Parallel (DTBUS) /
  Serial (ADBUS).
    - **Parallel**: 위 "DBS output pin bit 분할" 절 그대로 - 각 pin에 "Number of Col
      (#)" 입력칸이 보이고, Related Pin의 총 Bits를 그 값으로 나눈 몫이 "cluster
      개수"다(화면에 "N cluster(s) · DBS output pin Bit Depth: M bit(s)."로 표시).
      DBS output pin 자신의 Bit Depth는 여전히 자동 계산이지 사용자가 입력하지 않는다.
    - **Serial(기본값)**: 아래 "Serial Cluster" 절 참고 - Cluster 1이면 이 DBS output
      pin bit 분할 기능이 생기기 전과 완전히 동일(몫 항상 1), More than 1이면
      Parallel처럼 나누되 반대 방향(DBS output pin 쪽을 나눔) + Related Pin이 공유
      와일드카드로 바뀐다.
  라디오는 Check 때마다 다시 만들지 않는 영구 위젯이라, 전환해도 Port List를 다시
  읽지 않고 이미 읽어 둔 `_dbs_row_info`를 그 자리에서 다시 그리기만 한다
  (`_render_dbs_pin_sections`, `_on_dbs_transfer_type_changed`). 선택값은
  `pins[DBS_TRANSFER_TYPE_KEY]`로 저장되고, block5가 Parallel일 때만 그 방식으로
  분할하도록 참조한다(block5_writer._dbs_bit_split_groups, liberty_assembler.build_job).

2026-08 추가 - Serial Cluster ("Split Serial"):
  Serial을 고른 뒤 추가로 한 번 더 고르는 전역 라디오(`dbs_serial_cluster_row`,
  `pins[DBS_SERIAL_CLUSTER_MODE_KEY]`, 기본값 Cluster 1) - Data Transfer Type
  라디오와 같은 패턴으로 영구 위젯이고 Check 이후에만 보인다.
    - **Cluster: 1(기본값)**: 이 기능이 생기기 전과 완전히 동일 - 몫 항상 1, pin마다
      섹션에 이름 + Related Pin(Port List 값)만 보여준다.
    - **Cluster: More than 1**: 전체 공통(인식된 pin 전체, pin마다가 아님) 입력 두
      개를 `dbs_serial_split_row`에서 받는다 - "Number of Col (#)"과 "Related Pin
      (wildcard)"(예: "RD_EN_*[12:0]", '*'는 숫자만 매칭 - `pin_field_defs.
      match_digit_wildcard`). 각 DBS output pin의 Bits를 그 Number of Col로 나눈
      몫이 그 pin의 cluster 개수이고(Parallel과 반대 방향), 와일드카드로 매치된
      Related Pin이 그 개수만큼 있어야 한다. 인식된 DBS output pin이 Top/Bottom
      2개면(`pin_field_defs.classify_wildcard_side` - DBS output pin 와일드카드의
      '*'가 그 pin에서 실제로 매치한 조각이 'T'/'B'인지로 판별) 매치된 Related Pin을
      '*' 숫자값의 홀/짝으로 나눠 Top은 홀수만, Bottom은 짝수만 쓴다. pin마다 섹션은
      이름 + Bits만 보여주고("Related Pin은 아래 공유 입력이 담당" 안내 문구),
      결과 미리보기는 `dbs_serial_split_result`에 즉시 표시된다
      (`_update_dbs_serial_split_result`, settings_validator._validate_serial_split과
      같은 규칙).

2026-08 변경 - Output Path는 더 이상 Validate에 종속되지 않음:
  예전에는 Check(1) + Validate(2)를 통과해야만 Output Path 입력칸/Browse가 열렸다.
  이제 Output Path는 그 순서와 무관하게 언제든 입력·수정할 수 있고, Validate를 누르면
  (값이 채워져 있는 경우) 그 경로가 실제로 존재하는 폴더인지도 함께 검사한다
  (settings_validator.validate_output_path). Generate 버튼은 여전히 "Validate 통과"와
  "Output Path가 실제로 존재"를 모두 요구한다(_update_generate_button_state).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QButtonGroup, QFileDialog, QFormLayout, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QScrollArea, QVBoxLayout, QWidget,
)

from step1_setup.port_list_reader import (
    list_all_pin_bit_info, list_pins_by_port_type, list_port_pins_detailed,
    strip_bit_range_suffix,
)
from step2_udc import udc_manager
from step2_udc.udc_validator import selected_pdk_files
from step3_settings import settings_manager
from step3_settings.constants_field_defs import SCALAR_CONSTANT_DEFS
from step3_settings.pin_field_defs import (
    DBS_BIT_SPLIT_KEY, DBS_OUTPUT_KEY, DBS_POWER_DOWN_FUNCTION_KEY, DBS_RELATED_PINS_KEY,
    DBS_SERIAL_CLUSTER_MODE_DEFAULT, DBS_SERIAL_CLUSTER_MODE_KEY, DBS_SERIAL_CLUSTER_MULTI,
    DBS_SERIAL_CLUSTER_SINGLE, DBS_SERIAL_NUM_COL_KEY, DBS_SERIAL_RELATED_PATTERN_KEY,
    DBS_TIMING_SENSE_KEY,
    DBS_TIMING_TYPE_KEY, DBS_TRANSFER_TYPE_DEFAULT, DBS_TRANSFER_TYPE_KEY,
    DBS_TRANSFER_TYPE_PARALLEL, DBS_TRANSFER_TYPE_SERIAL, ENABLE_SIGNAL_KEY,
    POWER_DOWN_FALL_POWER_KEY, POWER_DOWN_KEY, POWER_DOWN_RISE_POWER_KEY, POWER_DOWN_WHEN_KEY,
    VIRTUAL_POWER_KEY, VIRTUAL_POWER_PG_FUNCTION_KEY, VIRTUAL_POWER_PORT_TYPE,
    VIRTUAL_POWER_SWITCH_FUNCTION_KEY, classify_wildcard_side, expand_dbs_output_pins,
    match_digit_wildcard_pins, split_pattern_and_range,
)
from step3_settings.settings_validator import (
    validate_constants, validate_output_path, validate_pin_settings,
)
from ui.theme import (
    BORDER_COLOR, ERROR_COLOR, MUTED_TEXT_COLOR, PRIMARY_COLOR, SUCCESS_COLOR, TEXT_COLOR,
    WARNING_BG, WARNING_BORDER, WARNING_TEXT,
)
from ui.ui_common import (
    NoWheelComboBox, add_shadow, build_back_button, build_bottom_button_row,
    build_label_with_info, build_section_header, run_export_config_dialog,
)

_HINT_STYLE = f"color: {MUTED_TEXT_COLOR}; font-size: 11px;"
# 2026-08 2차 변경 - 카드(entryCard 박스) 목록도 "표처럼 보인다"는 피드백을 받아,
# 인식된 pin이 보통 1~2개뿐이라는 점을 반영해 박스/스크롤 없이 나머지 입력들과 같은
# QFormLayout 흐름으로 더 단순화했다(아래 "DBS output pin 표시" 절 참고).
_DBS_PIN_NAME_STYLE = f"color: {TEXT_COLOR}; font-size: 13px; font-weight: 700;"
_DBS_RELATED_VALUE_STYLE = f"color: {TEXT_COLOR}; font-size: 12px;"

# 2026-08: Pin Settings의 상위 pin 3개(DBS output pin / Virtual Power / Power down
# control signal)는 "여기가 상위단"이라는 게 한눈에 보이도록 아래 연계 필드보다 크고
# 굵게 쓴다. 반대로 연계 그룹의 보라색 안내 문구("These are required because ...")는
# 입력값보다 덜 튀도록 투명도를 낮춘다.
_TOP_PIN_LABEL_STYLE = f"color: {TEXT_COLOR}; font-size: 15px; font-weight: 700;"
_LINKED_CAPTION_OPACITY = 0.55


def _build_top_pin_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(_TOP_PIN_LABEL_STYLE)
    return label


# ---------------------------------------------------------------------------
# 설명 문구 - 화면에 문단으로 깔지 않고 hover 정보 아이콘 툴팁으로만 보여준다
# (2026-08 레이아웃 개편).
# ---------------------------------------------------------------------------
_CONSTANTS_INFO = (
    "class, process_prefix, output_prefix, DFF Cell Name, LUT Table and Worst case "
    "primitive liberty are all required.\n\n"
    "process_prefix / class are used in block4's cell attributes "
    "(e.g. {process_prefix}_class).\n"
    "output_prefix is used in the output filename: "
    "{output_prefix}lpv_{cell_name}_{dbs stem}.lib"
)

_SCALAR_FIELD_INFO = {
    "dff_cell_name": (
        "Used with LUT Table to locate the lu_table_template index_1/index_2 lines in the "
        "PDK/DK file: the first 'cell (DFF Cell Name)' declaration is found, then the first "
        "line after it containing the LUT Table name (its cell_rise/cell_fall block) "
        "supplies the index_1/index_2 values."
    ),
    "primitive_cell_name": (
        "The cell_rise/cell_fall block name searched for after the DFF Cell Name "
        "declaration; its index_1/index_2 lines become block3's lu_table_template."
    ),
    "worst_case_pdk": (
        "The lu_table_template is read from THIS PDK file only, once per run, and the same "
        "table is reused for every generated liberty - the other PDK files are never "
        "searched for it.\n\n"
        "Candidates are the PDK files selected by the Step 2 liberty settings."
    ),
}

_DBS_CHECK_INFO = (
    "Run this check BEFORE Validate. The pins recognized by the wildcard change whenever "
    "the Port List file changes, so this list must be rebuilt from the current Port List "
    "first. Validate stays locked until then.\n\n"
    "Related Pin is read from the Port List and cannot be edited - it is always the "
    "current Port List's 'Related Pin' column value for that DBS output pin.\n\n"
    "Choose a Data Transfer Type below to control how each pin is shown and written."
)

_DBS_TRANSFER_TYPE_INFO = (
    "Parallel (DTBUS): set 'Number of Col (#)' per pin - Related Pin's total Bits must "
    "divide evenly by it (that quotient is the cluster count). block5 writes that many "
    "pin() ranges in the bus(), each with its own related_bus_pins range. This DBS "
    "output pin's own per-cluster Bit Depth is derived automatically (this pin's Bits / "
    "cluster count) - if either division does not divide evenly, Validate will reject it.\n\n"
    "Serial (ADBUS, default): choose a Serial Cluster below - '1' behaves exactly like "
    "before this feature existed; 'More than 1' (Split Serial) lets you split it too, "
    "using a shared Number of Col and a wildcard Related Pin instead of the Port List "
    "column."
)

_DBS_SERIAL_CLUSTER_INFO = (
    "Cluster: 1 (default) - the same single-block behavior as before this feature "
    "existed. Related Pin is read from the Port List and shown as-is.\n\n"
    "Cluster: More than 1 (Split Serial) - set a shared 'Number of Col (#)' and a "
    "wildcard 'Related Pin' pattern below (applies to every recognized DBS output pin, "
    "not per-pin). Each DBS output pin's Bits divided by Number of Col gives its cluster "
    "count; that many Related Pins (matched by the wildcard) are required. If two DBS "
    "output pins are recognized (Top/Bottom - determined by whether the DBS output pin "
    "wildcard's '*' matches 'T' or 'B'), the Top pin uses odd-numbered matches and the "
    "Bottom pin uses even-numbered matches."
)

_DBS_SERIAL_RELATED_INFO = (
    "Wildcard matched against Port==PORT pin names (e.g. 'RD_EN_*[12:0]') - '*' matches "
    "digits only (a name where '*' would match letters is ignored). The trailing "
    "'[12:0]' is display-only, like the DBS output pin's own range suffix - it is not "
    "used for matching."
)

_DBS_POWER_DOWN_FUNCTION_INFO = (
    "Optional - shared by every recognized DBS output pin, regardless of Data Transfer "
    "Type or Serial Cluster. When filled in, block5 writes "
    "power_down_function : \"<this text>\" ; right after "
    "{process_prefix}_input_signal_level in every DBS output pin() body. Leave empty to "
    "omit the line entirely - Validate does not require this field."
)

_DBS_TIMING_INFO = (
    "timing_sense / timing_type are shared by every recognized DBS output pin and are "
    "written into block5's timing() block. The values shown are the previous hard-coded "
    "defaults (non_unate / combinational)."
)

_VIRTUAL_POWER_INFO = (
    "Switch Function / PG Function do not allow wildcards (*). They are written as-is into "
    "block4's pg_pin switch_function / pg_function for the Virtual Power pin.\n\n"
    "Enable Signal keeps its wildcard behaviour."
)

_POWER_DOWN_INFO = (
    "Written into block5's {process_prefix}_acore_internal_power block of every pin "
    "matching the Power down control signal (_acore_rise_power / _acore_fall_power / "
    "_acore_when). The values shown are the previous hard-coded defaults."
)


class SettingsView(QWidget):
    def __init__(
        self,
        get_pdk_folder: Callable[[], str],
        get_dbs_folder: Callable[[], str],
        get_port_list_file: Callable[[], str],
        on_generate: Callable[[str], None] | None = None,
        show_loading: Callable[[str], None] | None = None,
        hide_loading: Callable[[], None] | None = None,
        on_back: Callable[[], None] | None = None,
        parent=None,
    ):
        """
        Args:
            get_pdk_folder / get_dbs_folder: 최신 폴더 경로를 즉시 조회하는 콜백
                (Step 1 값 재사용). 'Worst case primitive liberty' 후보 자체는 Step2에서
                고른 PDK 파일 목록에서 오지만, 앞으로의 확장을 위해 그대로 받아둔다.
            get_port_list_file: 최신 Port List 파일 경로를 즉시 조회하는 콜백
            on_generate: Generate 버튼을 눌렀을 때 호출되는 콜백(output_path: str)
            show_loading / hide_loading: Validate처럼 시간이 걸릴 수 있는 작업 전후에
                                          전역 로딩 오버레이를 보여주고 숨기는 콜백
            on_back: Back 버튼을 눌렀을 때 호출되는 콜백 (이전 Step으로 이동)
        """
        super().__init__(parent)
        self.get_pdk_folder = get_pdk_folder
        self.get_dbs_folder = get_dbs_folder
        self.get_port_list_file = get_port_list_file
        self.on_generate = on_generate
        self.show_loading = show_loading
        self.hide_loading = hide_loading
        self.on_back = on_back
        self.settings: dict = settings_manager.load_settings()

        self.scalar_widgets: dict[str, QWidget] = {}
        # "Check DBS Output Pins"를 눌러 현재 Port List로 pin을 펼친 상태인지 여부.
        # False인 동안에는 Validate 버튼이 잠겨 있다.
        self._dbs_check_done = False
        # 2026-08 추가: Check로 채운 pin마다의 원본 데이터(pin_name/dbs_bits/
        # related_pin/related_bits/default_split) + 현재 그려진 위젯 참조
        # (split_edit/result_label, Serial이면 둘 다 None). Related Pin/Bits는
        # 편집할 수 없으므로 이 값이 그 원본(source of truth)이고, Parallel일 때만
        # split_edit(Bit Depth) 칸을 사용자가 고친다.
        self._dbs_row_info: list[dict] = []
        # 2) Validate를 통과했는지 여부. Generate 버튼은 이 값과 Output Path가 실제로
        # 존재하는 폴더인지에 따라 열린다(_update_generate_button_state). Output Path
        # 자체는 더 이상 이 값에 의해 잠기지 않는다 - Validate 전에도 자유롭게 미리
        # 입력/변경할 수 있다(2026-08 변경, 아래 _on_browse_output 참고).
        self._settings_validated = False

        self._build_layout()

    # ------------------------------------------------------------------
    # 레이아웃 (좌: Constants / 우: Pin Settings)
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)

        title = QLabel("Constants & Pin Settings")
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "Configure constants and pin settings. Check the DBS output pins first, then "
            "validate before generating."
        )
        subtitle.setObjectName("subtitleLabel")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(self._wrap_in_scroll(self._build_constants_card()), stretch=1)
        columns.addWidget(self._wrap_in_scroll(self._build_pins_card()), stretch=1)
        outer.addLayout(columns, stretch=1)

        outer.addLayout(self._build_bottom_bar())

    def _wrap_in_scroll(self, widget: QWidget) -> QScrollArea:
        """
        2단 중 한쪽이 길어져도 다른 쪽은 그대로 보이도록, 열마다 따로 스크롤을 준다.
        (전체를 하나의 스크롤로 감싸면 오른쪽 열의 Check 버튼이 다시 밀려 내려간다)
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        # 가로 스크롤은 끈다 - 열 폭에 맞춰 내용이 줄어들어야지, 가로로 넘쳐서
        # 입력칸 오른쪽이 잘리면 안 된다.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        container.setObjectName("transparentRow")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)
        layout.addWidget(widget)
        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ------------------------------------------------------------------
    # Constants
    # ------------------------------------------------------------------
    def _build_constants_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(build_section_header("Constants", _CONSTANTS_INFO))

        scalar_form = QFormLayout()
        scalar_form.setSpacing(8)
        # 라벨이 길어도(예: "Worst case primitive liberty") 입력칸이 오른쪽으로 밀려
        # 열 밖으로 넘치지 않도록, 폭이 모자라면 라벨 아래로 접히게 한다.
        scalar_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        scalar_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for key, label, kind, default in SCALAR_CONSTANT_DEFS:
            saved = self.settings["scalars"].get(key, default)
            if kind == "pdk_dropdown":
                widget: QWidget = NoWheelComboBox()
            else:
                widget = QLineEdit(str(saved))
            widget.setMinimumWidth(120)
            self.scalar_widgets[key] = widget

            info = _SCALAR_FIELD_INFO.get(key)
            scalar_form.addRow(build_label_with_info(label, info) if info else label, widget)
        layout.addLayout(scalar_form)
        self._populate_worst_case_pdk_combo()

        return card

    def _populate_worst_case_pdk_combo(self) -> None:
        """
        'Worst case primitive liberty' 드롭다운을 다시 채운다. 후보는 Step2의 liberty
        setting들이 실제로 고른 PDK 파일들뿐이다 (2026-08 2차 재설계 - 예전에는 파일명
        자동 페어링이 성립한 PDK 목록이었다).
        """
        combo = self.scalar_widgets.get("worst_case_pdk")
        if combo is None:
            return

        combo.blockSignals(True)
        combo.clear()
        combo.addItem("(None)", "")
        for pdk_file in self.paired_pdk_files():
            combo.addItem(pdk_file, pdk_file)

        current = self.settings["scalars"].get("worst_case_pdk", "")
        idx = combo.findData(current) if current else 0
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def paired_pdk_files(self) -> list[str]:
        """Step2의 liberty setting들이 고른 PDK 파일명 목록 (항상 새로 읽음)."""
        return selected_pdk_files(udc_manager.load_state())

    # ------------------------------------------------------------------
    # Pin Settings
    #   2026-08 레이아웃 개편: DBS output pin + Check 블록을 맨 위로 올려서, 화면에
    #   들어오자마자 "1) Check DBS Output Pins" 버튼이 스크롤 없이 보이도록 한다.
    # ------------------------------------------------------------------
    def _build_pins_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)

        layout.addWidget(build_section_header("Pin Settings"))

        self._build_dbs_output_section(layout)
        self._build_virtual_power_section(layout)
        self._build_power_down_section(layout)

        return card

    def _build_dbs_output_section(self, layout: QVBoxLayout) -> None:
        pins = self.settings["pins"]

        dbs_form = QFormLayout()
        dbs_form.setSpacing(10)
        dbs_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        dbs_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.dbs_output_edit, self.dbs_output_badge = self._build_wildcard_field(
            dbs_form, _build_top_pin_label("DBS output pin"), pins.get(DBS_OUTPUT_KEY, ""),
        )
        self.dbs_output_edit.textChanged.connect(lambda _text: self._invalidate_dbs_check())
        layout.addLayout(dbs_form)

        group = self._build_linked_group(
            layout, "These are required because a DBS output pin is used."
        )

        check_row = QHBoxLayout()
        self.dbs_check_btn = QPushButton("1) Check DBS Output Pins")
        self.dbs_check_btn.setObjectName("primaryButton")
        self.dbs_check_btn.clicked.connect(self._on_check_dbs_pins)
        check_row.addWidget(self.dbs_check_btn)
        check_row.addWidget(self._build_dbs_check_badge())
        self.dbs_check_status = QLabel("")
        self.dbs_check_status.setWordWrap(True)
        check_row.addWidget(self.dbs_check_status, stretch=1)
        group.addLayout(check_row)

        # 2026-08 추가: Data Transfer Type(Parallel/Serial) - 인식된 pin 전체 공통
        # 선택 하나. Check 때마다 다시 만들지 않는 영구 위젯이라(선택값이 유지됨),
        # 전환되면 _on_dbs_transfer_type_changed가 Port List를 다시 읽지 않고
        # _dbs_row_info를 그 자리에서 다시 그린다(모듈 docstring 참고).
        self.dbs_transfer_type_row = QWidget()
        self.dbs_transfer_type_row.setObjectName("transparentRow")
        self.dbs_transfer_type_row.setVisible(False)
        transfer_type_layout = QHBoxLayout(self.dbs_transfer_type_row)
        transfer_type_layout.setContentsMargins(0, 0, 0, 0)
        transfer_type_layout.setSpacing(10)
        transfer_type_layout.addWidget(
            build_label_with_info("Data Transfer Type", _DBS_TRANSFER_TYPE_INFO)
        )
        self.dbs_transfer_type_group = QButtonGroup(self)
        self.dbs_transfer_type_parallel_radio = QRadioButton("Parallel (DTBUS)")
        self.dbs_transfer_type_serial_radio = QRadioButton("Serial (ADBUS)")
        self.dbs_transfer_type_group.addButton(self.dbs_transfer_type_parallel_radio)
        self.dbs_transfer_type_group.addButton(self.dbs_transfer_type_serial_radio)
        saved_transfer_type = pins.get(DBS_TRANSFER_TYPE_KEY, DBS_TRANSFER_TYPE_DEFAULT)
        if saved_transfer_type == DBS_TRANSFER_TYPE_PARALLEL:
            self.dbs_transfer_type_parallel_radio.setChecked(True)
        else:
            self.dbs_transfer_type_serial_radio.setChecked(True)
        self.dbs_transfer_type_parallel_radio.toggled.connect(self._on_dbs_transfer_type_changed)
        transfer_type_layout.addWidget(self.dbs_transfer_type_parallel_radio)
        transfer_type_layout.addWidget(self.dbs_transfer_type_serial_radio)
        transfer_type_layout.addStretch()
        group.addWidget(self.dbs_transfer_type_row)

        # 2026-08 추가: Serial Cluster ("Split Serial") - Serial일 때만 의미 있는
        # 두 번째 전역 선택. 영구 위젯이라(전환해도 다시 만들지 않음) Data Transfer
        # Type 라디오와 같은 패턴을 따른다.
        self.dbs_serial_cluster_row = QWidget()
        self.dbs_serial_cluster_row.setObjectName("transparentRow")
        self.dbs_serial_cluster_row.setVisible(False)
        cluster_row_layout = QHBoxLayout(self.dbs_serial_cluster_row)
        cluster_row_layout.setContentsMargins(0, 0, 0, 0)
        cluster_row_layout.setSpacing(10)
        cluster_row_layout.addWidget(
            build_label_with_info("Serial Cluster", _DBS_SERIAL_CLUSTER_INFO)
        )
        self.dbs_serial_cluster_group = QButtonGroup(self)
        self.dbs_serial_cluster_single_radio = QRadioButton("Cluster: 1")
        self.dbs_serial_cluster_multi_radio = QRadioButton("Cluster: More than 1 (Split Serial)")
        self.dbs_serial_cluster_group.addButton(self.dbs_serial_cluster_single_radio)
        self.dbs_serial_cluster_group.addButton(self.dbs_serial_cluster_multi_radio)
        saved_cluster_mode = pins.get(DBS_SERIAL_CLUSTER_MODE_KEY, DBS_SERIAL_CLUSTER_MODE_DEFAULT)
        if saved_cluster_mode == DBS_SERIAL_CLUSTER_MULTI:
            self.dbs_serial_cluster_multi_radio.setChecked(True)
        else:
            self.dbs_serial_cluster_single_radio.setChecked(True)
        self.dbs_serial_cluster_single_radio.toggled.connect(self._on_dbs_serial_cluster_mode_changed)
        cluster_row_layout.addWidget(self.dbs_serial_cluster_single_radio)
        cluster_row_layout.addWidget(self.dbs_serial_cluster_multi_radio)
        cluster_row_layout.addStretch()
        group.addWidget(self.dbs_serial_cluster_row)

        # Serial Cluster "More than 1"일 때만 보이는 공유(전체 pin 공통) 입력 두 개 +
        # 즉시 피드백용 결과 문구.
        self.dbs_serial_split_row = QWidget()
        self.dbs_serial_split_row.setObjectName("transparentRow")
        self.dbs_serial_split_row.setVisible(False)
        serial_split_form = QFormLayout(self.dbs_serial_split_row)
        serial_split_form.setSpacing(6)
        serial_split_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        serial_split_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.dbs_serial_num_col_edit = QLineEdit(str(pins.get(DBS_SERIAL_NUM_COL_KEY, "")))
        self.dbs_serial_related_edit = QLineEdit(str(pins.get(DBS_SERIAL_RELATED_PATTERN_KEY, "")))
        self.dbs_serial_num_col_edit.textChanged.connect(lambda _t: self._update_dbs_serial_split_result())
        self.dbs_serial_related_edit.textChanged.connect(lambda _t: self._update_dbs_serial_split_result())
        serial_split_form.addRow("Number of Col (#)", self.dbs_serial_num_col_edit)
        serial_split_form.addRow(
            build_label_with_info("Related Pin (wildcard)", _DBS_SERIAL_RELATED_INFO),
            self.dbs_serial_related_edit,
        )
        self.dbs_serial_split_result = QLabel("")
        self.dbs_serial_split_result.setWordWrap(True)
        self.dbs_serial_split_result.setStyleSheet("font-size: 11px;")
        serial_split_form.addRow("", self.dbs_serial_split_result)
        group.addWidget(self.dbs_serial_split_row)

        # 2026-08 2차 변경: 인식되는 DBS output pin은 보통 1~2개뿐이라 표/카드/스크롤로
        # 감쌀 이유가 없다 - 화면의 다른 입력들과 같은 QFormLayout 흐름으로 그냥
        # 이어서 보여준다(모듈 docstring "DBS output pin 표시" 절 참고).
        self.dbs_pins_container = QWidget()
        self.dbs_pins_container.setObjectName("transparentRow")
        self.dbs_pins_container.setVisible(False)
        self.dbs_pins_layout = QVBoxLayout(self.dbs_pins_container)
        self.dbs_pins_layout.setContentsMargins(0, 0, 0, 0)
        self.dbs_pins_layout.setSpacing(8)
        self.dbs_pins_layout.addStretch()
        group.addWidget(self.dbs_pins_container)

        inner_form = self._add_form(group)
        self.dbs_power_down_function_edit = QLineEdit(str(pins.get(DBS_POWER_DOWN_FUNCTION_KEY, "")))
        inner_form.addRow(
            build_label_with_info("power_down_function", _DBS_POWER_DOWN_FUNCTION_INFO),
            self.dbs_power_down_function_edit,
        )
        self.dbs_timing_sense_edit = QLineEdit(str(pins.get(DBS_TIMING_SENSE_KEY, "")))
        self.dbs_timing_type_edit = QLineEdit(str(pins.get(DBS_TIMING_TYPE_KEY, "")))
        inner_form.addRow(build_label_with_info("timing_sense", _DBS_TIMING_INFO), self.dbs_timing_sense_edit)
        inner_form.addRow(build_label_with_info("timing_type", _DBS_TIMING_INFO), self.dbs_timing_type_edit)

    def _build_virtual_power_section(self, layout: QVBoxLayout) -> None:
        pins = self.settings["pins"]

        top_form = QFormLayout()
        top_form.setSpacing(10)
        top_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        top_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.virtual_power_combo = NoWheelComboBox()
        self._populate_virtual_power_combo()
        top_form.addRow(_build_top_pin_label("Virtual Power (power gate)"), self.virtual_power_combo)
        layout.addLayout(top_form)

        group = self._build_linked_group(
            layout, "These are required because a Virtual Power (power gate) pin is used."
        )
        form = self._add_form(group)
        self.enable_signal_edit, self.enable_signal_badge = self._build_wildcard_field(
            form, "Enable Signal for power gate", pins.get(ENABLE_SIGNAL_KEY, ""),
        )
        self.switch_function_edit, self.switch_function_badge = self._build_plain_pin_field(
            form, "Virtual Power Switch Function",
            pins.get(VIRTUAL_POWER_SWITCH_FUNCTION_KEY, ""), _VIRTUAL_POWER_INFO,
        )
        self.pg_function_edit, self.pg_function_badge = self._build_plain_pin_field(
            form, "Virtual Power PG Function",
            pins.get(VIRTUAL_POWER_PG_FUNCTION_KEY, ""), _VIRTUAL_POWER_INFO,
        )

    def _build_power_down_section(self, layout: QVBoxLayout) -> None:
        pins = self.settings["pins"]

        pd_form = QFormLayout()
        pd_form.setSpacing(10)
        pd_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        pd_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.power_down_edit, self.power_down_badge = self._build_wildcard_field(
            pd_form, _build_top_pin_label("Power down control signal"),
            pins.get(POWER_DOWN_KEY, ""),
        )
        layout.addLayout(pd_form)

        group = self._build_linked_group(
            layout, "These are required because a Power down control signal is used."
        )
        form = self._add_form(group)
        self.power_down_rise_edit = QLineEdit(str(pins.get(POWER_DOWN_RISE_POWER_KEY, "")))
        self.power_down_fall_edit = QLineEdit(str(pins.get(POWER_DOWN_FALL_POWER_KEY, "")))
        self.power_down_when_edit = QLineEdit(str(pins.get(POWER_DOWN_WHEN_KEY, "")))
        form.addRow(build_label_with_info("rise power", _POWER_DOWN_INFO), self.power_down_rise_edit)
        form.addRow(build_label_with_info("fall power", _POWER_DOWN_INFO), self.power_down_fall_edit)
        form.addRow(build_label_with_info("when", _POWER_DOWN_INFO), self.power_down_when_edit)

    def _build_dbs_check_badge(self) -> QLabel:
        """
        "Validate보다 먼저"라는 경고를 문단 대신 한 칸짜리 배지 + 툴팁으로 보여준다
        (2026-08 레이아웃 개편 - 예전엔 세 줄짜리 배너였다).
        """
        badge = QLabel("⚠ required first")
        badge.setToolTip(_DBS_CHECK_INFO)
        badge.setStyleSheet(
            f"background-color: {WARNING_BG}; border: 1px solid {WARNING_BORDER}; "
            f"color: {WARNING_TEXT}; border-radius: 6px; padding: 4px 8px; font-size: 11px;"
        )
        return badge

    def _build_linked_group(self, parent_layout: QVBoxLayout, caption: str) -> QVBoxLayout:
        """
        바로 위 pin 입력에 연계된 하위 필드들을 담는 프레임. 왼쪽 세로선 + 들여쓰기로
        "위 pin을 입력했기 때문에 이어서 입력해야 하는 값들"임을 시각적으로 표현한다.

        Returns: 하위 위젯/폼을 순서대로 넣을 프레임 내부 QVBoxLayout
                 (폼이 필요하면 _add_form()으로 그 자리에 하나 만들어 쓴다)
        """
        frame = QFrame()
        frame.setObjectName("linkedGroup")
        frame.setStyleSheet(
            f"QFrame#linkedGroup {{ border: none; border-left: 2px solid {PRIMARY_COLOR}; "
            f"background: transparent; }}"
        )
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(14, 6, 0, 10)
        frame_layout.setSpacing(6)

        caption_label = QLabel(f"↳  {caption}")
        caption_label.setWordWrap(True)
        caption_label.setStyleSheet(f"color: {PRIMARY_COLOR}; font-size: 11px; font-weight: 600;")
        # 시스템 안내 문구는 입력값보다 덜 튀어야 하므로 투명도를 낮춘다 (2026-08).
        caption_opacity = QGraphicsOpacityEffect(caption_label)
        caption_opacity.setOpacity(_LINKED_CAPTION_OPACITY)
        caption_label.setGraphicsEffect(caption_opacity)
        frame_layout.addWidget(caption_label)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addSpacing(18)
        row.addWidget(frame, stretch=1)
        parent_layout.addLayout(row)
        return frame_layout

    def _add_form(self, layout: QVBoxLayout) -> QFormLayout:
        """지금 위치에 QFormLayout을 하나 만들어 붙이고 돌려준다(배치 순서 제어용)."""
        form = QFormLayout()
        form.setSpacing(8)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.addLayout(form)
        return form

    def _build_wildcard_field(
        self, form: QFormLayout, label, initial: str, info: str = "",
    ) -> tuple[QLineEdit, QLabel]:
        edit, badge = self._build_field_with_badge(form, label, initial, info)
        edit.textChanged.connect(lambda: self._update_wildcard_badge(edit, badge))
        self._update_wildcard_badge(edit, badge)
        return edit, badge

    def _build_plain_pin_field(
        self, form: QFormLayout, label, initial: str, info: str = "",
    ) -> tuple[QLineEdit, QLabel]:
        """와일드카드를 허용하지 않는 pin 입력 (입력에 '*'가 있으면 즉시 빨간 안내)."""
        edit, badge = self._build_field_with_badge(form, label, initial, info)
        edit.textChanged.connect(lambda: self._update_no_wildcard_badge(edit, badge))
        self._update_no_wildcard_badge(edit, badge)
        return edit, badge

    def _build_field_with_badge(
        self, form: QFormLayout, label, initial: str, info: str = "",
    ) -> tuple[QLineEdit, QLabel]:
        """label은 문자열 또는 위젯(예: 상위 pin용 굵은 라벨) 둘 다 가능하다."""
        container = QWidget()
        container.setObjectName("transparentRow")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)

        edit = QLineEdit(initial)
        badge = QLabel("")
        badge.setStyleSheet("font-size: 11px;")
        container_layout.addWidget(edit)
        container_layout.addWidget(badge)

        form.addRow(build_label_with_info(label, info) if info else label, container)
        return edit, badge

    def _update_wildcard_badge(self, edit: QLineEdit, badge: QLabel) -> None:
        pattern, range_part = split_pattern_and_range(edit.text())
        if "*" in pattern:
            text = "✓ Wildcard pattern detected"
            if range_part:
                text += f" · Range {range_part}"
            badge.setStyleSheet(f"color: {SUCCESS_COLOR}; font-size: 11px;")
            badge.setText(text)
        else:
            badge.setText("")

    def _update_no_wildcard_badge(self, edit: QLineEdit, badge: QLabel) -> None:
        if "*" in edit.text():
            badge.setStyleSheet(f"color: {ERROR_COLOR}; font-size: 11px;")
            badge.setText("✗ Wildcard (*) is not allowed here - enter one exact pin.")
        else:
            badge.setText("")

    def _build_bottom_bar(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(8)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output Path"))
        # 2026-08 변경: 예전에는 Check(1) + Validate(2)를 통과해야만 이 입력칸이
        # 열렸다. 이제 Output Path는 Validate와 순서 무관하게 언제든 입력/변경할 수
        # 있고, 실제로 존재하는 폴더인지는 Validate가 검사한다
        # (settings_validator.validate_output_path). Generate 버튼만 여전히 "Validate
        # 통과 + 존재하는 경로"를 함께 요구한다(_update_generate_button_state).
        self.output_path_edit = QLineEdit(self.settings.get("output_path", ""))
        self.output_path_edit.textChanged.connect(self._update_generate_button_state)
        output_row.addWidget(self.output_path_edit, stretch=1)
        self.output_browse_btn = QPushButton("Browse...")
        self.output_browse_btn.clicked.connect(self._on_browse_output)
        output_row.addWidget(self.output_browse_btn)
        layout.addLayout(output_row)

        self.output_path_status = QLabel("")
        self.output_path_status.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        layout.addWidget(self.output_path_status)

        self.export_btn = QPushButton("Export Config")
        self.export_btn.clicked.connect(self._on_export_config)

        self.validate_btn = QPushButton("2) Validate")
        self.validate_btn.setObjectName("primaryButton")
        self.validate_btn.clicked.connect(self._on_validate)

        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._on_generate_clicked)

        self.back_btn = build_back_button(self.on_back)
        layout.addLayout(build_bottom_button_row(
            self.back_btn, self.validate_btn, self.generate_btn,
            extra_left_buttons=(self.export_btn,),
        ))

        self._invalidate_dbs_check()
        return layout

    # ------------------------------------------------------------------
    # Virtual Power 콤보 (Port List의 PWR pin들로 채움)
    # ------------------------------------------------------------------
    def _populate_virtual_power_combo(self) -> None:
        self.virtual_power_combo.blockSignals(True)
        self.virtual_power_combo.clear()

        pwr_pins = list_pins_by_port_type(self.get_port_list_file(), VIRTUAL_POWER_PORT_TYPE)
        self.virtual_power_combo.addItem("(None)", "")
        for pin in pwr_pins:
            self.virtual_power_combo.addItem(pin, pin)

        current = self.settings["pins"].get(VIRTUAL_POWER_KEY, "")
        idx = self.virtual_power_combo.findData(current) if current else 0
        self.virtual_power_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.virtual_power_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # DBS output pin Check (Validate보다 항상 먼저)
    # ------------------------------------------------------------------
    def _invalidate_dbs_check(self) -> None:
        """
        Check 결과를 무효화하고 Validate를 다시 잠근다. DBS output pin 입력이 바뀌거나
        화면을 다시 열었을 때(= Port List가 바뀌었을 수 있을 때, Step4에서 Back으로
        돌아온 경우 포함) 호출된다.
        """
        self._dbs_check_done = False
        self._settings_validated = False
        self._dbs_row_info = []
        if hasattr(self, "dbs_pins_container"):
            self._clear_dbs_pin_sections()
            self.dbs_pins_container.setVisible(False)
        if hasattr(self, "dbs_transfer_type_row"):
            self.dbs_transfer_type_row.setVisible(False)
        if hasattr(self, "dbs_serial_cluster_row"):
            self.dbs_serial_cluster_row.setVisible(False)
        if hasattr(self, "dbs_serial_split_row"):
            self.dbs_serial_split_row.setVisible(False)
        if hasattr(self, "dbs_check_status"):
            self.dbs_check_status.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
            self.dbs_check_status.setText("Not checked yet - Validate is locked.")
        if hasattr(self, "validate_btn"):
            self.validate_btn.setEnabled(False)
            self.validate_btn.setToolTip("Run '1) Check DBS Output Pins' first.")
        if hasattr(self, "generate_btn"):
            self.generate_btn.setEnabled(False)

    def _on_check_dbs_pins(self) -> None:
        # Check 도중 다시 눌려 중복 실행되지 않도록 잠근다 (2026-08 추가).
        self.dbs_check_btn.setEnabled(False)
        if self.show_loading:
            self.show_loading("Checking DBS output pins against the Port List...")

        try:
            dbs_text = self.dbs_output_edit.text().strip()
            recognized = (
                expand_dbs_output_pins(self.get_port_list_file(), dbs_text) if dbs_text else []
            )
        finally:
            self.dbs_check_btn.setEnabled(True)
            if self.hide_loading:
                self.hide_loading()

        if not dbs_text:
            self._invalidate_dbs_check()
            self.dbs_check_status.setStyleSheet(f"color: {ERROR_COLOR}; font-size: 11px;")
            self.dbs_check_status.setText("DBS output pin is empty - nothing to check.")
            return

        if not recognized:
            self._invalidate_dbs_check()
            self.dbs_check_status.setStyleSheet(f"color: {ERROR_COLOR}; font-size: 11px;")
            self.dbs_check_status.setText(
                f"'{dbs_text}' matched no PORT pins in the current Port List."
            )
            return

        self._rebuild_dbs_pin_sections(recognized)
        self._dbs_check_done = True
        self.dbs_check_status.setStyleSheet(f"color: {SUCCESS_COLOR}; font-size: 11px;")
        self.dbs_check_status.setText(
            f"✓ {len(recognized)} DBS output pin(s) recognized. Related Pin is fixed from "
            "the Port List. Choose a Data Transfer Type below, then Validate."
        )
        self.validate_btn.setEnabled(True)
        self.validate_btn.setToolTip("")

    def _clear_dbs_pin_sections(self) -> None:
        while self.dbs_pins_layout.count():
            item = self.dbs_pins_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.dbs_pins_layout.addStretch()

    @staticmethod
    def _build_separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {BORDER_COLOR};")
        return line

    def _current_transfer_type(self) -> str:
        if self.dbs_transfer_type_parallel_radio.isChecked():
            return DBS_TRANSFER_TYPE_PARALLEL
        return DBS_TRANSFER_TYPE_SERIAL

    def _on_dbs_transfer_type_changed(self, _checked: bool = False) -> None:
        """
        라디오가 바뀌면(Check가 이미 끝난 상태에서만 의미 있음) Port List를 다시
        읽지 않고, 이미 읽어 둔 _dbs_row_info로 화면만 다시 그린다.
        """
        if self._dbs_check_done:
            self._render_dbs_pin_sections()

    def _rebuild_dbs_pin_sections(self, recognized: list[str]) -> None:
        """
        Port List에서 인식된 pin마다 값(Bits/Related Pin/Related Bits)을 다시 읽어
        _dbs_row_info를 채우고 화면을 그린다. Bit Depth의 저장된 기본값도 여기서
        함께 채워 둔다(Data Transfer Type을 바꿔도 다시 읽을 필요 없도록).
        """
        port_list_file = self.get_port_list_file()
        detailed_by_name = {
            pin["pin_name"]: pin for pin in list_port_pins_detailed(port_list_file)
        }
        pin_bit_info = list_all_pin_bit_info(port_list_file)
        saved_split = self.settings["pins"].get(DBS_BIT_SPLIT_KEY) or {}

        self._dbs_row_info = []
        for pin_name in recognized:
            detail = detailed_by_name.get(pin_name)
            dbs_bits = detail["bits"] if detail else None
            related_pin = (detail.get("related_pin") or "").strip() if detail else ""
            related_base = strip_bit_range_suffix(related_pin) if related_pin else ""
            related_info = pin_bit_info.get(related_base) if related_base else None
            related_bits = related_info["bits"] if related_info else None

            default_split = str(saved_split.get(pin_name, "")).strip()
            if not default_split:
                # 기본값 = Related Pin의 전체 bit 수 그대로(=1 cluster, 2026-08 재설계 -
                # Number of Col은 이제 Related Pin 쪽을 나누므로) - 건드리지 않으면
                # 예전과 동일하게 pin() 하나만 쓰는 동작이 유지된다.
                default_split = str(related_bits) if related_bits else "1"

            self._dbs_row_info.append({
                "pin_name": pin_name, "dbs_bits": dbs_bits,
                "related_pin": related_pin, "related_bits": related_bits,
                "default_split": default_split,
                "split_edit": None, "result_label": None,
            })

        self._render_dbs_pin_sections()
        self.dbs_pins_container.setVisible(True)
        self.dbs_transfer_type_row.setVisible(True)

    def _current_serial_cluster_mode(self) -> str:
        if self.dbs_serial_cluster_multi_radio.isChecked():
            return DBS_SERIAL_CLUSTER_MULTI
        return DBS_SERIAL_CLUSTER_SINGLE

    def _on_dbs_serial_cluster_mode_changed(self, _checked: bool = False) -> None:
        """Data Transfer Type 라디오와 같은 패턴 - Check가 끝난 상태에서만 다시 그린다."""
        if self._dbs_check_done:
            self._render_dbs_pin_sections()

    def _render_dbs_pin_sections(self) -> None:
        """
        현재 Data Transfer Type(Parallel/Serial) + Serial Cluster 선택에 맞춰
        _dbs_row_info를 화면에 (다시) 그린다 - Port List는 다시 읽지 않는다. 인식된
        pin이 보통 1~2개뿐이라 pin이 많을 때를 위한 스크롤/높이 제한은 두지 않는다 -
        pin 사이에는 구분선만 넣는다(모듈 docstring "DBS output pin 표시" / "Data
        Transfer Type" 절 참고).
        """
        self._clear_dbs_pin_sections()
        transfer_type = self._current_transfer_type()
        is_serial = transfer_type == DBS_TRANSFER_TYPE_SERIAL
        cluster_mode = self._current_serial_cluster_mode()
        self.dbs_serial_cluster_row.setVisible(is_serial)
        self.dbs_serial_split_row.setVisible(is_serial and cluster_mode == DBS_SERIAL_CLUSTER_MULTI)

        for index, info in enumerate(self._dbs_row_info):
            if index > 0:
                self.dbs_pins_layout.insertWidget(self.dbs_pins_layout.count() - 1, self._build_separator())

            section, split_edit, result_label = self._build_dbs_pin_section(info, transfer_type, cluster_mode)
            self.dbs_pins_layout.insertWidget(self.dbs_pins_layout.count() - 1, section)
            info["split_edit"] = split_edit
            info["result_label"] = result_label
            if split_edit is not None:
                row = index
                split_edit.textChanged.connect(lambda _t, r=row: self._update_dbs_row_result(r))

        for row in range(len(self._dbs_row_info)):
            self._update_dbs_row_result(row)
        self._update_dbs_serial_split_result()

    def _build_dbs_pin_section(
        self, info: dict, transfer_type: str, serial_cluster_mode: str = DBS_SERIAL_CLUSTER_SINGLE,
    ) -> tuple[QWidget, QLineEdit | None, QLabel | None]:
        """
        인식된 DBS output pin 하나.
          - Serial + Cluster 1: 굵은 이름 줄 + "Related Pin" 한 줄뿐(이 기능이 생기기
            전과 동일 - Bits도 보여주지 않는다).
          - Serial + Cluster "More than 1"(Split Serial): 이름 + Bits만 보여준다 -
            Related Pin은 pin마다가 아니라 화면 아래 공유 와일드카드 입력이 담당한다.
          - Parallel: 이름+Bits, Related Pin+Bits, 그리고 "Number of Col (#)" 입력칸
            (그 바로 아래 cluster 개수/DBS output pin Bit Depth 계산 결과 문구)까지 -
            Number of Col을 뺀 나머지는 전부 시스템이 채워주는 값이므로 표/카드처럼
            별도 박스로 감싸지 않는다.
        """
        pin_name = info["pin_name"]
        dbs_bits = info["dbs_bits"]
        related_pin = info["related_pin"]
        related_bits = info["related_bits"]

        section = QWidget()
        section.setObjectName("transparentRow")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(4)

        form = QFormLayout()
        form.setSpacing(6)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        if transfer_type == DBS_TRANSFER_TYPE_SERIAL and serial_cluster_mode == DBS_SERIAL_CLUSTER_MULTI:
            bits_text = f"{dbs_bits} bit" if dbs_bits is not None else "? bit"
            name_label = QLabel(f"{pin_name}   ·   {bits_text}")
            name_label.setStyleSheet(_DBS_PIN_NAME_STYLE)
            name_label.setWordWrap(True)
            section_layout.addWidget(name_label)

            note = QLabel(
                "Related Pin is set below (shared 'Number of Col' / 'Related Pin "
                "(wildcard)') - not per pin."
            )
            note.setStyleSheet(_HINT_STYLE)
            note.setWordWrap(True)
            section_layout.addWidget(note)
            return section, None, None

        if transfer_type == DBS_TRANSFER_TYPE_SERIAL:
            name_label = QLabel(pin_name)
            name_label.setStyleSheet(_DBS_PIN_NAME_STYLE)
            name_label.setWordWrap(True)
            section_layout.addWidget(name_label)

            related_label = QLabel(related_pin or "(none - Port List Related Pin is empty)")
            related_label.setStyleSheet(_DBS_RELATED_VALUE_STYLE)
            related_label.setWordWrap(True)
            form.addRow("Related Pin", related_label)

            section_layout.addLayout(form)
            return section, None, None

        bits_text = f"{dbs_bits} bit" if dbs_bits is not None else "? bit"
        name_label = QLabel(f"{pin_name}   ·   {bits_text}")
        name_label.setStyleSheet(_DBS_PIN_NAME_STYLE)
        name_label.setWordWrap(True)
        section_layout.addWidget(name_label)

        related_bits_text = f"{related_bits} bit" if related_bits is not None else "? bit"
        related_label = QLabel(
            f"{related_pin}   ·   {related_bits_text}" if related_pin
            else "(none - Port List Related Pin is empty)"
        )
        related_label.setStyleSheet(_DBS_RELATED_VALUE_STYLE)
        related_label.setWordWrap(True)
        form.addRow("Related Pin", related_label)

        split_container = QWidget()
        split_container.setObjectName("transparentRow")
        split_layout = QVBoxLayout(split_container)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(2)
        can_split = (
            dbs_bits is not None and dbs_bits > 1 and related_bits is not None and related_bits > 1
        )
        split_edit = QLineEdit(info["default_split"])
        split_edit.setMaximumWidth(120)
        split_edit.setEnabled(can_split)
        if dbs_bits is None or dbs_bits <= 1:
            split_edit.setToolTip("1 bit - cannot be split.")
        elif related_bits is None or related_bits <= 1:
            split_edit.setToolTip("Related Pin has 1 bit or is unknown - cannot be split.")
        result_label = QLabel("")
        result_label.setWordWrap(True)
        result_label.setStyleSheet("font-size: 11px;")
        split_layout.addWidget(split_edit)
        split_layout.addWidget(result_label)
        form.addRow("Number of Col (#)", split_container)

        section_layout.addLayout(form)
        return section, split_edit, result_label

    def _update_dbs_row_result(self, row: int) -> None:
        """
        'Number of Col (#)' 바로 아래 문구를 이 행의 현재 값으로 다시 계산해 보여준다
        (settings_validator._validate_dbs_related_pins와 같은 규칙 - 여기서는 즉시
        피드백용이고, 최종 확정 검사는 여전히 Validate가 한다). Serial이면 split_edit
        자체가 없으므로 아무것도 하지 않는다.
        """
        if row >= len(self._dbs_row_info):
            return
        info = self._dbs_row_info[row]
        split_edit = info["split_edit"]
        result_label = info["result_label"]
        if split_edit is None or result_label is None:
            return

        def _set(text: str, color: str) -> None:
            result_label.setStyleSheet(f"color: {color}; font-size: 11px;")
            result_label.setText(text)

        dbs_bits = info["dbs_bits"]
        related_bits = info["related_bits"]
        if dbs_bits is None:
            _set("DBS output pin Bits is unknown.", ERROR_COLOR)
            return
        if dbs_bits == 1:
            _set("1 bit - written as a single pin().", MUTED_TEXT_COLOR)
            return
        if not info["related_pin"]:
            _set("Related Pin is empty in the Port List.", ERROR_COLOR)
            return
        if related_bits is None:
            _set("Related Pin Bits is unknown.", ERROR_COLOR)
            return
        if related_bits <= 1:
            _set("Related Pin has only 1 bit - cannot be split into columns.", ERROR_COLOR)
            return

        col_text = split_edit.text().strip()
        try:
            col_count = int(col_text)
        except ValueError:
            _set("Enter a whole number of columns.", ERROR_COLOR)
            return

        if col_count <= 0 or col_count > related_bits:
            _set(f"Must be between 1 and {related_bits} (Related Pin's Bits).", ERROR_COLOR)
            return
        if related_bits % col_count != 0:
            _set(f"Related Pin's {related_bits} bits do not divide evenly by {col_count}.", ERROR_COLOR)
            return
        cluster_count = related_bits // col_count
        if dbs_bits % cluster_count != 0:
            _set(
                f"DBS output pin's {dbs_bits} bits do not divide evenly across "
                f"{cluster_count} cluster(s).",
                ERROR_COLOR,
            )
            return
        dbs_bit_depth = dbs_bits // cluster_count
        _set(
            f"✓ {cluster_count} cluster(s) · DBS output pin Bit Depth: {dbs_bit_depth} bit(s).",
            SUCCESS_COLOR,
        )

    def _update_dbs_serial_split_result(self) -> None:
        """
        Serial Cluster "More than 1"(Split Serial)의 공유 결과 문구를 현재 입력값으로
        다시 계산해 보여준다(settings_validator._validate_serial_split과 같은 규칙 -
        즉시 피드백용이고, 최종 확정 검사는 여전히 Validate가 한다).
        """
        if not hasattr(self, "dbs_serial_split_result"):
            return
        label = self.dbs_serial_split_result

        def _set(text: str, color: str) -> None:
            label.setStyleSheet(f"color: {color}; font-size: 11px;")
            label.setText(text)

        if (self._current_transfer_type() != DBS_TRANSFER_TYPE_SERIAL
                or self._current_serial_cluster_mode() != DBS_SERIAL_CLUSTER_MULTI):
            label.setText("")
            return
        if not self._dbs_row_info:
            return

        col_text = self.dbs_serial_num_col_edit.text().strip()
        try:
            col_count = int(col_text)
            if col_count <= 0:
                raise ValueError
        except ValueError:
            _set("Enter a positive whole number of columns.", ERROR_COLOR)
            return

        recognized = [info["pin_name"] for info in self._dbs_row_info]
        if len(recognized) > 2:
            _set(
                f"Split Serial supports at most 2 DBS output pins (Top/Bottom); "
                f"{len(recognized)} were recognized.",
                ERROR_COLOR,
            )
            return

        cluster_counts: dict[str, int] = {}
        for info in self._dbs_row_info:
            dbs_bits = info["dbs_bits"]
            pin_name = info["pin_name"]
            if dbs_bits is None:
                _set(f"DBS output pin '{pin_name}': Bits is unknown.", ERROR_COLOR)
                return
            if dbs_bits <= 1 or col_count > dbs_bits or dbs_bits % col_count != 0:
                _set(
                    f"DBS output pin '{pin_name}': {dbs_bits} bits do not divide evenly "
                    f"by {col_count}.",
                    ERROR_COLOR,
                )
                return
            cluster_counts[pin_name] = dbs_bits // col_count

        related_pattern = self.dbs_serial_related_edit.text().strip()
        if not related_pattern:
            _set("Enter a Related Pin wildcard (e.g. RD_EN_*[12:0]).", ERROR_COLOR)
            return
        matched = match_digit_wildcard_pins(self.get_port_list_file(), related_pattern)
        if not matched:
            _set(f"'{related_pattern}' matched no PORT pins.", ERROR_COLOR)
            return

        if len(recognized) == 1:
            pin_name = recognized[0]
            needed = cluster_counts[pin_name]
            if len(matched) != needed:
                _set(f"Matched {len(matched)} Related Pin(s), need exactly {needed}.", ERROR_COLOR)
            else:
                _set(f"✓ {needed} cluster(s) matched.", SUCCESS_COLOR)
            return

        dbs_pattern, _range_part = split_pattern_and_range(self.dbs_output_edit.text().strip())
        sides: dict[str, str] = {}
        for pin_name in recognized:
            side = classify_wildcard_side(dbs_pattern, pin_name)
            if side is None:
                _set(f"Could not determine Top/Bottom for '{pin_name}' from the wildcard.", ERROR_COLOR)
                return
            sides[pin_name] = side
        if set(sides.values()) != {"top", "bottom"}:
            _set("Need exactly one Top (T) and one Bottom (B) DBS output pin.", ERROR_COLOR)
            return

        odd_count = sum(1 for value, _name in matched if value % 2 == 1)
        even_count = len(matched) - odd_count
        parts = []
        ok = True
        for pin_name, side in sides.items():
            needed = cluster_counts[pin_name]
            actual = odd_count if side == "top" else even_count
            parity = "odd" if side == "top" else "even"
            parts.append(f"{pin_name} ({side}): {actual}/{needed} {parity}-numbered")
            if actual != needed:
                ok = False
        _set(("✓ " if ok else "✗ ") + " · ".join(parts), SUCCESS_COLOR if ok else ERROR_COLOR)

    def _collect_dbs_related_pins(self) -> dict:
        """
        Check가 끝난 상태면 이번 Check로 고정된 Port List 값을 그대로 쓰고, 아직
        Check 전이면 저장돼 있던 값을 유지한다(화면을 다시 열었다는 이유만으로 이미
        저장된 값이 날아가지 않도록). Related Pin은 더 이상 편집할 수 없으므로 카드가
        아니라 _dbs_row_info(원본)에서 읽는다.
        """
        if not self._dbs_check_done:
            saved = self.settings["pins"].get(DBS_RELATED_PINS_KEY) or {}
            return dict(saved)
        return {info["pin_name"]: info["related_pin"] for info in self._dbs_row_info}

    def _collect_dbs_bit_split(self) -> dict:
        """
        Check가 끝난 상태면 저장값에 각 pin의 현재 Bit Depth 칸 값을 덮어써서
        돌려준다. Serial일 때는 Bit Depth 입력칸 자체가 없으므로(split_edit이 None)
        그 pin은 건드리지 않고 저장값을 그대로 둔다 - Parallel로 다시 돌아왔을 때
        예전에 입력했던 값이 날아가지 않도록.
        """
        saved = self.settings["pins"].get(DBS_BIT_SPLIT_KEY) or {}
        if not self._dbs_check_done:
            return dict(saved)
        result = dict(saved)
        for info in self._dbs_row_info:
            if info["split_edit"] is not None:
                result[info["pin_name"]] = info["split_edit"].text().strip()
        return result

    def _collect_dbs_transfer_type(self) -> str:
        return self._current_transfer_type()

    # ------------------------------------------------------------------
    # 값 수집 / 저장
    # ------------------------------------------------------------------
    def _collect_constants(self) -> dict:
        scalars = {}
        for key, _label, kind, _default in SCALAR_CONSTANT_DEFS:
            widget = self.scalar_widgets[key]
            if kind == "pdk_dropdown":
                scalars[key] = widget.currentData() or ""
            else:
                scalars[key] = widget.text().strip()

        return {"scalars": scalars}

    def _collect_pins(self) -> dict:
        return {
            VIRTUAL_POWER_KEY: self.virtual_power_combo.currentData() or "",
            ENABLE_SIGNAL_KEY: self.enable_signal_edit.text().strip(),
            VIRTUAL_POWER_SWITCH_FUNCTION_KEY: self.switch_function_edit.text().strip(),
            VIRTUAL_POWER_PG_FUNCTION_KEY: self.pg_function_edit.text().strip(),
            POWER_DOWN_KEY: self.power_down_edit.text().strip(),
            POWER_DOWN_RISE_POWER_KEY: self.power_down_rise_edit.text().strip(),
            POWER_DOWN_FALL_POWER_KEY: self.power_down_fall_edit.text().strip(),
            POWER_DOWN_WHEN_KEY: self.power_down_when_edit.text().strip(),
            DBS_OUTPUT_KEY: self.dbs_output_edit.text().strip(),
            DBS_POWER_DOWN_FUNCTION_KEY: self.dbs_power_down_function_edit.text().strip(),
            DBS_TIMING_SENSE_KEY: self.dbs_timing_sense_edit.text().strip(),
            DBS_TIMING_TYPE_KEY: self.dbs_timing_type_edit.text().strip(),
            DBS_RELATED_PINS_KEY: self._collect_dbs_related_pins(),
            DBS_BIT_SPLIT_KEY: self._collect_dbs_bit_split(),
            DBS_TRANSFER_TYPE_KEY: self._collect_dbs_transfer_type(),
            DBS_SERIAL_CLUSTER_MODE_KEY: self._current_serial_cluster_mode(),
            DBS_SERIAL_NUM_COL_KEY: self.dbs_serial_num_col_edit.text().strip(),
            DBS_SERIAL_RELATED_PATTERN_KEY: self.dbs_serial_related_edit.text().strip(),
        }

    def _collect_all(self) -> dict:
        constants = self._collect_constants()
        return {
            "scalars": constants["scalars"],
            # Voltage Map은 Step 2에서 편집한다(화면만 옮겨졌고 저장 위치는 여기 그대로).
            # 이 화면이 들고 있던 옛 값으로 덮어쓰지 않도록 항상 파일에서 다시 읽는다.
            "voltage_map": settings_manager.load_voltage_map(),
            "pins": self._collect_pins(),
            "output_path": self.output_path_edit.text().strip(),
        }

    def _persist(self) -> None:
        self.settings = self._collect_all()
        settings_manager.save_settings(self.settings)

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------
    def _on_validate(self) -> None:
        if not self._dbs_check_done:
            # 버튼이 잠겨 있으므로 보통은 여기 오지 않지만, 방어적으로 한 번 더 막는다.
            self.result_label.setStyleSheet(f"color: {ERROR_COLOR};")
            self.result_label.setText("• Run '1) Check DBS Output Pins' before validating.")
            return

        # Validate 도중 다시 눌려 중복 실행되지 않도록 잠근다 (2026-08 추가).
        self.validate_btn.setEnabled(False)
        if self.show_loading:
            self.show_loading("Validating settings...")

        try:
            self._persist()
            errors = validate_constants(self.settings["scalars"], self.paired_pdk_files())
            errors += validate_pin_settings(self.settings["pins"], self.get_port_list_file())
            # 2026-08 추가: Output Path는 이제 Validate 전에도 자유롭게 입력할 수
            # 있으므로, 채워져 있다면 실제로 존재하는 폴더인지 여기서 확인한다.
            errors += validate_output_path(self.settings.get("output_path", ""))
        finally:
            self.validate_btn.setEnabled(True)
            if self.hide_loading:
                self.hide_loading()

        if errors:
            self._settings_validated = False
            self.result_label.setStyleSheet(f"color: {ERROR_COLOR};")
            self.result_label.setText("\n".join(f"• {e}" for e in errors))
        else:
            self._settings_validated = True
            self.result_label.setStyleSheet(f"color: {SUCCESS_COLOR};")
            output_path = self.output_path_edit.text().strip()
            if output_path and Path(output_path).is_dir():
                self.result_label.setText("Settings passed validation. Ready to generate.")
            else:
                self.result_label.setText(
                    "Settings passed validation. Choose an output path to continue."
                )
        self._update_generate_button_state()

    def _update_generate_button_state(self) -> None:
        # 2026-08 변경: Output Path는 더 이상 Validate로 잠기지 않으므로, Generate는
        # "Validate 통과" + "Output Path가 실제로 존재하는 폴더"를 함께 요구한다.
        output_path = self.output_path_edit.text().strip()
        path_exists = bool(output_path) and Path(output_path).is_dir()
        self.generate_btn.setEnabled(self._settings_validated and path_exists)

        if hasattr(self, "output_path_status"):
            if not output_path:
                self.output_path_status.setText("")
            elif path_exists:
                self.output_path_status.setStyleSheet(f"color: {SUCCESS_COLOR}; font-size: 11px;")
                self.output_path_status.setText("✓ Path exists.")
            else:
                self.output_path_status.setStyleSheet(f"color: {ERROR_COLOR}; font-size: 11px;")
                self.output_path_status.setText("✗ This path does not exist yet.")

    def _on_browse_output(self) -> None:
        # 2026-08 변경: 예전에는 Validate를 통과해야만 대화상자가 열렸지만, 이제
        # Output Path는 Validate와 순서 무관하게 언제든 고를 수 있다.
        #
        # DontUseNativeDialog(2026-08 추가): OS 고유 대화상자는 네트워크 폴더를 훑느라
        # 느릴 수 있고, 이 앱의 Ctrl+C 강제 종료 단축키(ui/force_quit.py)가 닿지 않는
        # 별도 창이라 열려 있는 동안은 먹히지 않는다. Qt 자체 대화상자를 쓰면 같은
        # 이벤트 루프 안에서 열리므로 열려 있는 동안에도 Ctrl+C가 그대로 동작한다.
        #
        # 시작 폴더(2026-08 추가): 힌트 없이 열면 OS/Qt가 홈 디렉터리(사내 HPC망에서는
        # 대개 네트워크 마운트)부터 훑어야 해서 대화상자를 여는 것 자체가 느려질 수
        # 있다. 이미 골라 둔 Output Path, 없으면 Step1의 PDK Folder(이미 접근 가능하다고
        # 확인된 위치)를 힌트로 준다.
        start_dir = self.output_path_edit.text().strip() or self.get_pdk_folder()
        path = QFileDialog.getExistingDirectory(
            self, "Select Output Path", start_dir, QFileDialog.DontUseNativeDialog,
        )
        if path:
            self.output_path_edit.setText(path)

    def _on_generate_clicked(self) -> None:
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            return
        self._persist()
        if self.on_generate:
            self.on_generate(output_path)

    # ------------------------------------------------------------------
    # Config export (2026-08 추가)
    # ------------------------------------------------------------------
    def _on_export_config(self) -> None:
        self._persist()
        run_export_config_dialog(self, self.get_pdk_folder())

    # ------------------------------------------------------------------
    # 화면이 다시 보일 때마다 (Step 2에서 왔을 때 / Step4에서 Back으로 돌아왔을 때)
    # 최신 pin/PDK 정보 반영 + Check 결과 무효화
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        super().showEvent(event)
        self._populate_virtual_power_combo()
        self._populate_worst_case_pdk_combo()
        # Step1에서 Port List 파일이 바뀌었을 수 있고, Step4에서 Back으로 돌아온 경우도
        # 처음부터 다시 밟아야 하므로, 화면에 들어올 때마다 Check 결과는 무효로 본다.
        self._invalidate_dbs_check()
