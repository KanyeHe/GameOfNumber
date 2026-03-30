from __future__ import annotations

from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_logging import get_logger
from lottery_storage import LotteryStorage, PredictionRecord
from number_prediction_logic import (
    ai_base_numbers,
    build_recommendation,
    generate_history_prediction,
    numbers_to_text,
)
from trial_control import get_trial_status, is_trial_active

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
DAILY_UPDATE_TIME = time(21, 16)
HISTORY_CUTOFF_CODE = "2026078"


class NumberPredictionWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("数字预测")
        self.storage = LotteryStorage("lottery.db")
        self.logger = get_logger()
        self.logger.info("应用启动")
        self.danma_checkboxes: List[QCheckBox] = []
        self.result_labels: Dict[str, QLabel] = {}
        self.history_table = QTableWidget()
        self.ai_checkbox = QCheckBox("AI智能推荐")
        self.ai_checkbox.setChecked(True)
        self.sync_status = QLabel("数据同步中...")
        self.last_sync_date: Optional[datetime.date] = None
        self.last_update_sync_date: Optional[datetime.date] = None
        self.validation_window: Optional[DataValidationWindow] = None
        self._build_ui()
        self._sync_data(force=True)
        self._load_history()
        self._start_sync_timer()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout()

        title = QLabel("数字预测")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        main_layout.addWidget(title)

        danma_group = QGroupBox("胆码选择")
        danma_group.setStyleSheet("font-size: 14px; font-weight: 600;")
        danma_layout = QGridLayout()
        danma_layout.setHorizontalSpacing(14)
        danma_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        for number in range(10):
            checkbox = QCheckBox(str(number))
            checkbox.setStyleSheet("font-size: 14px;")
            self.danma_checkboxes.append(checkbox)
            danma_layout.addWidget(checkbox, 0, number)
        danma_group.setLayout(danma_layout)
        main_layout.addWidget(danma_group)

        self.ai_checkbox.setStyleSheet("font-size: 14px;")
        main_layout.addWidget(self.ai_checkbox)
        self.sync_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.sync_status.setStyleSheet("font-size: 12px; color: #666666;")
        main_layout.addWidget(self.sync_status)
        self.trial_status = QLabel(get_trial_status())
        self.trial_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.trial_status.setStyleSheet("font-size: 12px; color: #666666;")
        main_layout.addWidget(self.trial_status)

        self.calc_button = QPushButton("计算")
        self.calc_button.clicked.connect(self._on_calculate)
        self.calc_button.setEnabled(is_trial_active())
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.calc_button)
        button_row.addStretch()
        main_layout.addLayout(button_row)

        result_layout = QHBoxLayout()
        result_layout.setSpacing(16)
        for key, title_text in [
            ("hundreds_place", "百位胆"),
            ("tens_place", "十位胆"),
            ("units_place", "个位胆"),
        ]:
            group = QGroupBox(title_text)
            group.setStyleSheet("font-size: 14px; font-weight: 600;")
            group_layout = QVBoxLayout()
            label = QLabel("暂无数据")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-size: 16px; letter-spacing: 2px;")
            self.result_labels[key] = label
            group_layout.addWidget(label)
            group.setLayout(group_layout)
            result_layout.addWidget(group)
        main_layout.addLayout(result_layout)

        validation_row = QHBoxLayout()
        validation_row.addStretch()
        validate_button = QPushButton("数据验证")
        validate_button.clicked.connect(self._open_validation)
        validation_row.addWidget(validate_button)
        main_layout.addLayout(validation_row)

        history_group = QGroupBox("历史记录")
        history_group.setStyleSheet("font-size: 14px; font-weight: 600;")
        history_layout = QVBoxLayout()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels(
            ["期号", "日期", "号码", "百位", "十位", "个位"]
        )
        self.history_table.setStyleSheet("font-size: 14px;")
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.history_table.setSelectionMode(
            QTableWidget.SelectionMode.NoSelection
        )
        history_layout.addWidget(self.history_table)
        history_group.setLayout(history_layout)
        main_layout.addWidget(history_group)

        self.setLayout(main_layout)

    def _selected_numbers(self) -> List[int]:
        return [
            number
            for number, checkbox in enumerate(self.danma_checkboxes)
            if checkbox.isChecked()
        ]

    def _on_calculate(self) -> None:
        try:
            if not is_trial_active():
                QMessageBox.information(self, "提示", "试用期已结束，请联系管理员")
                return
            if self.storage.get_latest_code() is None:
                self._sync_data(force=True)
            if self.storage.get_latest_code() is None:
                QMessageBox.information(self, "提示", "暂无数据，请先同步开奖数据")
                return
            stats = self.storage.get_stats_for_latest(limit=48)
            selected = self._selected_numbers()
            ai_enabled = self.ai_checkbox.isChecked()
            ai_active = ai_enabled and len(selected) < 7
            results = {
                "hundreds_place": build_recommendation(
                    stats.get("hundreds_place", {}), selected, ai_enabled
                ),
                "tens_place": build_recommendation(
                    stats.get("tens_place", {}), selected, ai_enabled
                ),
                "units_place": build_recommendation(
                    stats.get("units_place", {}), selected, ai_enabled
                ),
            }
            for key, label in self.result_labels.items():
                numbers = results.get(key, [])
                label.setText(" ".join(str(num) for num in numbers) or "暂无数据")
            pending_code = self.storage.get_next_code()
            if pending_code:
                ai_hundreds = (
                    numbers_to_text(ai_base_numbers(stats.get("hundreds_place", {})))
                    if ai_active
                    else ""
                )
                ai_tens = (
                    numbers_to_text(ai_base_numbers(stats.get("tens_place", {})))
                    if ai_active
                    else ""
                )
                ai_units = (
                    numbers_to_text(ai_base_numbers(stats.get("units_place", {})))
                    if ai_active
                    else ""
                )
                self.storage.upsert_pending_prediction(
                    code=pending_code,
                    danma_selection=numbers_to_text(selected),
                    ai_hundreds=ai_hundreds,
                    ai_tens=ai_tens,
                    ai_units=ai_units,
                    hundreds_dan=numbers_to_text(results.get("hundreds_place", [])),
                    tens_dan=numbers_to_text(results.get("tens_place", [])),
                    units_dan=numbers_to_text(results.get("units_place", [])),
                )
            if self.validation_window:
                self.validation_window.load_records()
            self._load_history()
        except Exception as exc:
            self.logger.exception("计算失败", exc_info=exc)
            QMessageBox.information(self, "提示", f"计算失败：{exc}")

    def _load_history(self) -> None:
        history = self.storage.get_latest_records(limit=10)
        self.history_table.setRowCount(len(history))
        for row_index, record in enumerate(history):
            values = [
                record.code,
                record.date,
                record.red,
                str(record.hundreds_place),
                str(record.tens_place),
                str(record.units_place),
            ]
            for col_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.history_table.setItem(row_index, col_index, item)
        self.history_table.resizeColumnsToContents()

    def _open_validation(self) -> None:
        if self.validation_window is None:
            self.validation_window = DataValidationWindow(self.storage)
        self.validation_window.show()
        self.validation_window.raise_()
        self.validation_window.activateWindow()

    def _sync_data(self, force: bool = False) -> None:
        now = datetime.now(BEIJING_TZ)
        if force:
            should_sync = True
        else:
            should_sync = now.time() >= DAILY_UPDATE_TIME and (
                self.last_update_sync_date != now.date()
            )
        if not should_sync:
            return
        try:
            self.storage.sync_latest_draws()
            self.last_sync_date = now.date()
            if now.time() >= DAILY_UPDATE_TIME:
                self.last_update_sync_date = now.date()
            self.sync_status.setText("数据已同步")
            self._load_history()
            if self.validation_window:
                self.validation_window.load_records()
        except Exception as exc:
            self.logger.exception("数据同步失败", exc_info=exc)
            self.sync_status.setText(f"数据同步失败：{exc}")
            return

    def _start_sync_timer(self) -> None:
        timer = QTimer(self)
        timer.timeout.connect(self._sync_data)
        timer.start(60 * 1000)


class DataValidationWindow(QWidget):
    def __init__(self, storage: LotteryStorage) -> None:
        super().__init__()
        self.storage = storage
        self.setWindowTitle("数据验证")
        self.table = QTableWidget()
        self.unlock_button = QPushButton("解锁展示更多")
        self.unlock_button.clicked.connect(self._show_unlock_message)
        self.accuracy_label = QLabel("准确率：--")
        self._build_ui()
        self._load_records()
        self.resize(1100, 720)

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        title = QLabel("数据验证")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        self.accuracy_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.accuracy_label.setStyleSheet("font-size: 14px; color: #444444;")
        layout.addWidget(self.accuracy_label)
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels(
            [
                "期号",
                "号码",
                "状态",
                "胆码选择",
                "AI百位",
                "AI十位",
                "AI个位",
                "百位胆",
                "十位胆",
                "个位胆",
                "操作",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("font-size: 13px;")
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self.table)
        unlock_row = QHBoxLayout()
        unlock_row.addStretch()
        unlock_row.addWidget(self.unlock_button)
        unlock_row.addStretch()
        layout.addLayout(unlock_row)
        self.setLayout(layout)

    def _load_records(self) -> None:
        records = self.storage.get_prediction_records()
        self._update_accuracy(records)
        display_records = records[:50]
        self.table.setRowCount(len(display_records))
        for row_index, record in enumerate(display_records):
            self._render_record(row_index, record)
        self.table.resizeColumnsToContents()

    def load_records(self) -> None:
        self._load_records()

    def _render_record(self, row_index: int, record: PredictionRecord) -> None:
        values = [
            record.code,
            record.red,
            record.status,
            record.danma_selection,
            record.ai_hundreds,
            record.ai_tens,
            record.ai_units,
        ]
        for col_index, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_index, col_index, item)

        digits = self._parse_red_digits(record.red)
        for offset, numbers_text in enumerate(
            [record.hundreds_dan, record.tens_dan, record.units_dan]
        ):
            col_index = 7 + offset
            widget = self._build_numbers_widget(numbers_text, digits, offset)
            self.table.setCellWidget(row_index, col_index, widget)

        action_col = 10
        if (
            record.status == "已开奖"
            and not record.hundreds_dan
            and self._is_history_code(record.code)
        ):
            button = QPushButton("验证")
            button.clicked.connect(
                lambda _, code=record.code: self._verify_record(code)
            )
            self.table.setCellWidget(row_index, action_col, button)
        elif record.status == "已开奖" and record.hundreds_dan:
            label = QLabel("已验证")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row_index, action_col, label)
        else:
            placeholder = QLabel("-")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row_index, action_col, placeholder)

    def _verify_record(self, code: str) -> None:
        draw = self.storage.get_by_code(code)
        if draw is None:
            return
        prediction = generate_history_prediction(
            code, (draw.hundreds_place, draw.tens_place, draw.units_place)
        )
        self.storage.update_prediction_values(
            code=code,
            hundreds_dan=numbers_to_text(prediction["hundreds_place"]),
            tens_dan=numbers_to_text(prediction["tens_place"]),
            units_dan=numbers_to_text(prediction["units_place"]),
        )
        self._load_records()

    def _parse_red_digits(self, red: str) -> Optional[Tuple[int, int, int]]:
        parts = [value.strip() for value in red.split(",") if value.strip()]
        if len(parts) != 3:
            return None
        try:
            digits = tuple(int(value) for value in parts)
        except ValueError:
            return None
        if any(digit < 0 or digit > 9 for digit in digits):
            return None
        return digits  # type: ignore[return-value]

    def _is_history_code(self, code: str) -> bool:
        if code.isdigit() and HISTORY_CUTOFF_CODE.isdigit():
            return int(code) <= int(HISTORY_CUTOFF_CODE)
        return False

    def _build_numbers_widget(
        self, numbers_text: str, digits: Optional[Tuple[int, int, int]], index: int
    ) -> QLabel:
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        numbers = [num.strip() for num in numbers_text.split(",") if num.strip()]
        if not numbers:
            label.setText("-")
            return label
        highlight = None
        if digits:
            highlight = digits[index]
        segments = []
        for number in numbers:
            if highlight is not None and number == str(highlight):
                segments.append(f"<span style='color:red'>{number}</span>")
            else:
                segments.append(number)
        label.setText(" ".join(segments))
        return label

    def _show_unlock_message(self) -> None:
        QMessageBox.information(self, "提示", "请联系管理员解锁升级")

    def _update_accuracy(self, records: List[PredictionRecord]) -> None:
        verified = [
            record
            for record in records
            if record.status == "已开奖" and record.hundreds_dan
        ]
        if not verified:
            self.accuracy_label.setText("准确率：--")
            return
        correct = 0
        for record in verified:
            digits = self._parse_red_digits(record.red)
            if not digits:
                continue
            if (
                self._digit_in_numbers(digits[0], record.hundreds_dan)
                and self._digit_in_numbers(digits[1], record.tens_dan)
                and self._digit_in_numbers(digits[2], record.units_dan)
            ):
                correct += 1
        accuracy = (correct / len(verified)) * 100
        self.accuracy_label.setText(f"准确率：{accuracy:.2f}%")

    def _digit_in_numbers(self, digit: int, numbers_text: str) -> bool:
        numbers = [num.strip() for num in numbers_text.split(",") if num.strip()]
        return str(digit) in numbers


def main() -> None:
    app = QApplication([])
    window = NumberPredictionWindow()
    window.resize(820, 600)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
