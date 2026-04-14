from __future__ import annotations

from datetime import datetime, time
import re
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QComboBox,
    QDialogButtonBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_logging import get_logger
from central_api import ApiError, CentralApiClient
from lottery_storage import PredictionRecord
from number_prediction_logic import (
    ai_base_numbers,
    build_recommendation,
    generate_history_prediction,
    numbers_to_text,
)
from remote_storage import RemoteLotteryStorage
from session_store import SessionStore, build_device_profile, new_request_id

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
DAILY_UPDATE_TIME = time(21, 16)
HISTORY_CUTOFF_CODE = "2026078"
PRODUCT_CODE = "GAME_OF_NUMBER"
CLIENT_TYPE = "DESKTOP"
AUTH_DIALOG_STYLE = """
QDialog {
    background-color: #1f2739;
}
QFrame#card {
    background-color: #232d43;
    border: 2px solid #b7c0d4;
    border-radius: 24px;
}
QLabel#title {
    color: #f3f7ff;
    font-size: 24px;
    font-weight: 700;
}
QLabel#fieldLabel {
    color: #e8eefb;
    font-size: 15px;
    font-weight: 700;
}
QLabel#subtleText {
    color: #8e9ab3;
    font-size: 13px;
}
QPushButton#segmented {
    background-color: #1a2235;
    color: #9aa8c2;
    border: none;
    border-radius: 14px;
    padding: 14px 18px;
    font-size: 15px;
    font-weight: 700;
}
QPushButton#segmented:checked {
    background-color: #4a7cf0;
    color: white;
}
QPushButton#textAction {
    background: transparent;
    color: #5d95ff;
    border: none;
    font-size: 14px;
    font-weight: 700;
    padding: 0;
}
QPushButton#primaryButton {
    background-color: #4a7cf0;
    color: white;
    border: none;
    border-radius: 14px;
    min-height: 54px;
    font-size: 16px;
    font-weight: 700;
}
QPushButton#primaryButton:disabled {
    background-color: #3f5fa6;
    color: #a8b4cd;
}
QPushButton#ghostButton {
    background: transparent;
    color: #5d95ff;
    border: none;
    font-size: 15px;
    font-weight: 700;
}
QLineEdit {
    background-color: #1a2235;
    color: #edf3ff;
    border: 2px solid #a7b2ca;
    border-radius: 14px;
    min-height: 54px;
    padding: 0 16px;
    font-size: 15px;
}
QLineEdit::placeholder {
    color: #6c7a98;
}
QCheckBox {
    color: #8e9ab3;
    font-size: 14px;
    font-weight: 600;
}
"""


def _build_segment_button(text: str, checked: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("segmented")
    button.setCheckable(True)
    button.setChecked(checked)
    return button


def _build_text_action(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("textAction")
    return button


def _build_input(placeholder: str, password: bool = False) -> QLineEdit:
    widget = QLineEdit()
    widget.setPlaceholderText(placeholder)
    if password:
        widget.setEchoMode(QLineEdit.EchoMode.Password)
    return widget


class AuthDialog(QDialog):
    def __init__(self, api_client: CentralApiClient, session_store: SessionStore) -> None:
        super().__init__()
        self.api_client = api_client
        self.session_store = session_store
        self.account: Optional[Dict[str, Any]] = None
        self.device_profile = build_device_profile()
        self.api_client.set_device_profile(
            {
                **self.device_profile,
                "productCode": PRODUCT_CODE,
                "clientType": CLIENT_TYPE,
            }
        )
        self.setWindowTitle("账号登录")
        self.resize(760, 720)
        self.login_scene = "phone"
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(AUTH_DIALOG_STYLE)
        root = QVBoxLayout()
        root.setContentsMargins(42, 24, 42, 24)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(52, 46, 52, 38)
        card_layout.setSpacing(20)

        title = QLabel("登录")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        scene_row = QHBoxLayout()
        scene_row.setSpacing(14)
        self.phone_login_button = _build_segment_button("手机号登录", checked=True)
        self.email_login_button = _build_segment_button("邮箱登录")
        self.phone_login_button.clicked.connect(lambda: self._switch_login_scene("phone"))
        self.email_login_button.clicked.connect(lambda: self._switch_login_scene("email"))
        scene_row.addWidget(self.phone_login_button)
        scene_row.addWidget(self.email_login_button)
        card_layout.addLayout(scene_row)

        self.account_label = QLabel("手机号码")
        self.account_label.setObjectName("fieldLabel")
        card_layout.addWidget(self.account_label)
        self.login_account_input = _build_input("请输入手机号")
        card_layout.addWidget(self.login_account_input)

        self.secret_label = QLabel("密码")
        self.secret_label.setObjectName("fieldLabel")
        card_layout.addWidget(self.secret_label)
        self.password_input = _build_input("请输入密码", password=True)
        card_layout.addWidget(self.password_input)

        option_row = QHBoxLayout()
        self.remember_checkbox = QCheckBox("记住我")
        option_row.addWidget(self.remember_checkbox)
        option_row.addStretch()
        self.forgot_button = _build_text_action("忘记密码？")
        self.forgot_button.clicked.connect(self._show_reset_tip)
        option_row.addWidget(self.forgot_button)
        card_layout.addLayout(option_row)

        self.login_button = QPushButton("登录")
        self.login_button.setObjectName("primaryButton")
        self.login_button.clicked.connect(self._login)
        card_layout.addWidget(self.login_button)

        foot_row = QHBoxLayout()
        foot_row.addStretch()
        foot_row.addWidget(QLabel("还没有账户？"))
        self.register_button = _build_text_action("立即注册")
        self.register_button.clicked.connect(self._open_register)
        foot_row.addWidget(self.register_button)
        foot_row.addStretch()
        card_layout.addLayout(foot_row)

        self.status_label = QLabel("首次使用请先注册账号，再登录并选择产品计划。")
        self.status_label.setObjectName("subtleText")
        self.status_label.setWordWrap(True)
        card_layout.addWidget(self.status_label)

        root.addStretch()
        root.addWidget(card)
        root.addStretch()
        self.setLayout(root)

    def _switch_login_scene(self, scene: str) -> None:
        self.login_scene = scene
        self.phone_login_button.setChecked(scene == "phone")
        self.email_login_button.setChecked(scene == "email")
        if scene == "phone":
            self.account_label.setText("手机号码")
            self.login_account_input.setPlaceholderText("请输入手机号")
        else:
            self.account_label.setText("邮箱地址")
            self.login_account_input.setPlaceholderText("请输入邮箱地址")

    def _show_reset_tip(self) -> None:
        QMessageBox.information(self, "提示", "忘记密码流程需要订阅中心提供重置密码接口。")

    def _login(self) -> None:
        login_account = self.login_account_input.text().strip()
        password = self.password_input.text().strip()
        if not login_account or not password:
            QMessageBox.information(self, "提示", "请先完整输入登录信息")
            return
        if self.login_scene == "phone" and not re.fullmatch(r"1\d{10}", login_account):
            QMessageBox.information(self, "提示", "请输入正确的手机号")
            return
        if self.login_scene == "email" and not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+", login_account
        ):
            QMessageBox.information(self, "提示", "请输入正确的邮箱地址")
            return
        try:
            self.api_client.login(
                login_account=login_account,
                password=password,
                client_type=CLIENT_TYPE,
                product_code=PRODUCT_CODE,
                login_ip=self.device_profile["loginIp"],
            )
            self.account = self.api_client.get_current_account().get("data", {})
            self._establish_product_session()
            self._save_session()
            self.accept()
        except ApiError as exc:
            QMessageBox.information(self, "登录失败", str(exc))

    def _open_register(self) -> None:
        dialog = RegisterDialog(self.api_client, self)
        dialog.exec()

    def _establish_product_session(self) -> None:
        device_payload = dict(self.device_profile)
        device_payload["productCode"] = PRODUCT_CODE
        self.api_client.set_device_profile(device_payload)
        self.api_client.upsert_device(device_payload)
        self._ensure_subscription()
        self.api_client.enter_product(
            {
                "productCode": PRODUCT_CODE,
                "clientType": CLIENT_TYPE,
                "deviceFingerprint": self.device_profile["deviceFingerprint"],
                "installId": self.device_profile["installId"],
                "loginIp": self.device_profile["loginIp"],
                "userAgent": "PyQt6 Desktop Client",
                "concurrencyStrategy": "KICK_OLD",
                "requestId": new_request_id("enter-product"),
            }
        )
        session_no = str(self.api_client.product_session_no or "")
        access_payload = self.api_client.check_access(
            product_code=PRODUCT_CODE,
            session_no=session_no,
            device_fingerprint=self.device_profile["deviceFingerprint"],
        )
        access_data = access_payload.get("data", access_payload)
        access_granted = bool(
            access_data.get("access")
            or access_data.get("granted")
            or access_data.get("hasAccess")
        )
        if access_granted:
            return
        dialog = PlanDialog(self.api_client, self.device_profile, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            raise ApiError("未完成产品计划开通")
        self.api_client.enter_product(
            {
                "productCode": PRODUCT_CODE,
                "clientType": CLIENT_TYPE,
                "deviceFingerprint": self.device_profile["deviceFingerprint"],
                "installId": self.device_profile["installId"],
                "loginIp": self.device_profile["loginIp"],
                "userAgent": "PyQt6 Desktop Client",
                "concurrencyStrategy": "KICK_OLD",
                "requestId": new_request_id("enter-product"),
            }
        )

    def _ensure_subscription(self) -> None:
        payload = self.api_client.get_current_subscription(PRODUCT_CODE)
        data = payload.get("data", payload)
        has_access = False
        if isinstance(data, dict):
            has_access = bool(
                data.get("access")
                or data.get("granted")
                or data.get("hasAccess")
                or data.get("active")
                or data.get("currentStatus") in {"ACTIVE", "TRIAL", "VALID"}
                or data.get("status") in {"ACTIVE", "TRIAL", "VALID"}
            )
        if has_access:
            return
        try:
            self.api_client.open_trial(
                product_code=PRODUCT_CODE,
                device_fingerprint=self.device_profile["deviceFingerprint"],
                client_type=CLIENT_TYPE,
                request_id=new_request_id("trial"),
            )
        except ApiError:
            pass

    def _save_session(self) -> None:
        if not self.remember_checkbox.isChecked():
            self.session_store.clear()
            return
        self.session_store.save(
            {
                "auth": {
                    "accessToken": self.api_client.auth_access_token,
                    "refreshToken": self.api_client.auth_refresh_token,
                },
                "product": {
                    "accessToken": self.api_client.product_access_token,
                    "refreshToken": self.api_client.product_refresh_token,
                    "sessionNo": self.api_client.product_session_no,
                },
                "account": self.account,
                "deviceProfile": self.device_profile,
            }
        )


class RegisterDialog(QDialog):
    def __init__(self, api_client: CentralApiClient, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api_client = api_client
        self.setWindowTitle("注册账号")
        self.resize(540, 820)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(AUTH_DIALOG_STYLE)
        root = QVBoxLayout()
        root.setContentsMargins(28, 10, 28, 10)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(36, 34, 36, 30)
        card_layout.setSpacing(16)

        title = QLabel("创建账户")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        self.username_label = QLabel("* 用户名")
        self.username_label.setObjectName("fieldLabel")
        card_layout.addWidget(self.username_label)
        self.username_input = _build_input("请输入用户名")
        card_layout.addWidget(self.username_input)

        self.email_label = QLabel("邮箱地址")
        self.email_label.setObjectName("fieldLabel")
        card_layout.addWidget(self.email_label)
        self.email_input = _build_input("请输入邮箱地址")
        card_layout.addWidget(self.email_input)

        self.phone_label = QLabel("* 手机号码")
        self.phone_label.setObjectName("fieldLabel")
        card_layout.addWidget(self.phone_label)
        self.phone_input = _build_input("请输入手机号码")
        card_layout.addWidget(self.phone_input)

        self.password_label = QLabel("* 密码")
        self.password_label.setObjectName("fieldLabel")
        card_layout.addWidget(self.password_label)
        self.password_input = _build_input("请输入密码（至少6位）", password=True)
        card_layout.addWidget(self.password_input)

        self.confirm_password_label = QLabel("* 确认密码")
        self.confirm_password_label.setObjectName("fieldLabel")
        card_layout.addWidget(self.confirm_password_label)
        self.confirm_password_input = _build_input("请再次输入密码", password=True)
        card_layout.addWidget(self.confirm_password_input)

        self.agree_checkbox = QCheckBox("我已阅读并同意 服务条款 和 隐私政策")
        card_layout.addWidget(self.agree_checkbox)

        self.create_account_button = QPushButton("创建账户")
        self.create_account_button.setObjectName("primaryButton")
        self.create_account_button.clicked.connect(self._register)
        card_layout.addWidget(self.create_account_button)

        foot_row = QHBoxLayout()
        foot_row.addStretch()
        foot_row.addWidget(QLabel("已有账户？"))
        login_button = _build_text_action("立即登录")
        login_button.clicked.connect(self.accept)
        foot_row.addWidget(login_button)
        foot_row.addStretch()
        card_layout.addLayout(foot_row)

        self.status_label = QLabel("* 为必填项，邮箱为选填。")
        self.status_label.setObjectName("subtleText")
        self.status_label.setWordWrap(True)
        card_layout.addWidget(self.status_label)

        root.addWidget(card)
        self.setLayout(root)

    def _register(self) -> None:
        username = self.username_input.text().strip()
        email = self.email_input.text().strip()
        phone = self.phone_input.text().strip()
        password = self.password_input.text().strip()
        confirm_password = self.confirm_password_input.text().strip()
        if not username or not phone or not password:
            QMessageBox.information(self, "提示", "请完整填写所有必填项")
            return
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            QMessageBox.information(self, "提示", "请输入正确的邮箱地址")
            return
        if not re.fullmatch(r"1\d{10}", phone):
            QMessageBox.information(self, "提示", "请输入正确的手机号")
            return
        if len(password) < 6:
            QMessageBox.information(self, "提示", "密码长度不能少于 6 位")
            return
        if password != confirm_password:
            QMessageBox.information(self, "提示", "两次输入的密码不一致")
            return
        if not self.agree_checkbox.isChecked():
            QMessageBox.information(self, "提示", "请先阅读并同意服务条款和隐私政策")
            return
        try:
            self.api_client.register(
                username=username,
                email=email,
                phone=phone,
                password=password,
                nickname=username,
                register_source=CLIENT_TYPE,
            )
        except ApiError as exc:
            QMessageBox.information(self, "注册失败", str(exc))
            return
        QMessageBox.information(self, "提示", "注册成功，请返回登录")
        self.accept()


class PlanDialog(QDialog):
    def __init__(
        self,
        api_client: CentralApiClient,
        device_profile: Dict[str, str],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.api_client = api_client
        self.device_profile = device_profile
        self.setWindowTitle("选择产品计划")
        self.resize(460, 260)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        title = QLabel("当前账号尚未开通 数字游戏 使用权限")
        title.setWordWrap(True)
        layout.addWidget(title)

        self.plan_combo = QComboBox()
        plans = self._extract_plans()
        for plan in plans:
            label = f"{plan.get('planCode', '')} / {plan.get('planName', '')}".strip(" /")
            self.plan_combo.addItem(label or "默认计划", plan)
        layout.addWidget(self.plan_combo)

        trial_button = QPushButton("开通试用")
        trial_button.clicked.connect(self._open_trial)
        order_button = QPushButton("创建支付订单")
        order_button.clicked.connect(self._create_order)
        buttons = QHBoxLayout()
        buttons.addWidget(trial_button)
        buttons.addWidget(order_button)
        layout.addLayout(buttons)
        self.tip_label = QLabel("如产品支持试用，可先开通试用；否则直接生成支付订单。")
        self.tip_label.setWordWrap(True)
        self.tip_label.setStyleSheet("font-size: 12px; color: #666666;")
        layout.addWidget(self.tip_label)
        self.setLayout(layout)

    def _extract_plans(self) -> List[Dict[str, Any]]:
        return [{"planCode": "MONTH", "planName": "月付"}]

    def _open_trial(self) -> None:
        try:
            self.api_client.open_trial(
                product_code=PRODUCT_CODE,
                device_fingerprint=self.device_profile["deviceFingerprint"],
                client_type=CLIENT_TYPE,
                request_id=new_request_id("trial"),
            )
        except ApiError as exc:
            QMessageBox.information(self, "开通试用失败", str(exc))
            return
        QMessageBox.information(self, "提示", "试用已开通")
        self.accept()

    def _create_order(self) -> None:
        plan = self.plan_combo.currentData() or {}
        plan_code = str(plan.get("planCode", "MONTH"))
        try:
            payload = self.api_client.create_payment_order(
                product_code=PRODUCT_CODE,
                plan_code=plan_code,
                order_type=2,
            )
        except ApiError as exc:
            QMessageBox.information(self, "创建订单失败", str(exc))
            return
        order = payload.get("data", payload)
        QMessageBox.information(
            self,
            "订单已创建",
            f"订单号：{order.get('orderNo', '') or order.get('bizRequestNo', '')}",
        )
        self.accept()


class NumberPredictionWindow(QWidget):
    def __init__(
        self,
        storage: RemoteLotteryStorage,
        account: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("数字游戏")
        self.storage = storage
        self.account = account or {}
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
        self._safe_sync_data(force=True)
        self._safe_load_history()
        self._start_sync_timer()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout()

        title = QLabel("数字游戏")
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
        nickname = self.account.get("nickname") or self.account.get("username") or "当前用户"
        self.trial_status = QLabel(f"已登录：{nickname}")
        self.trial_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.trial_status.setStyleSheet("font-size: 12px; color: #666666;")
        main_layout.addWidget(self.trial_status)

        self.calc_button = QPushButton("计算")
        self.calc_button.clicked.connect(self._on_calculate)
        self.calc_button.setEnabled(True)
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
            if self.storage.get_latest_code() is None:
                self._sync_data(force=True)
            if self.storage.get_latest_code() is None:
                QMessageBox.information(self, "提示", "暂无数据，请先同步开奖数据")
                return
            stats = self.storage.get_stats_for_recent_days(days=21)
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

    def _safe_load_history(self) -> None:
        try:
            self._load_history()
        except Exception as exc:
            self.logger.exception("加载历史记录失败", exc_info=exc)
            self.history_table.setRowCount(0)
            self.sync_status.setText(self._format_backend_error("历史记录加载失败", exc))

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
            self._safe_load_history()
            if self.validation_window:
                self.validation_window.load_records()
        except Exception as exc:
            self.logger.exception("数据同步失败", exc_info=exc)
            self.sync_status.setText(self._format_backend_error("数据同步失败", exc))
            return

    def _safe_sync_data(self, force: bool = False) -> None:
        try:
            self._sync_data(force=force)
        except Exception as exc:
            self.logger.exception("初始化同步失败", exc_info=exc)
            self.sync_status.setText(self._format_backend_error("初始化失败", exc))

    def _format_backend_error(self, prefix: str, exc: Exception) -> str:
        message = str(exc)
        if "Central auth request failed" in message:
            return (
                f"{prefix}：数字游戏后端鉴权依赖的中心服务地址配置异常，"
                "请检查后端是否仍指向 localhost:8081"
            )
        return f"{prefix}：{message}"

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
        self.error_filter_button = QPushButton("未中记录")
        self.error_filter_button.clicked.connect(self._toggle_error_filter)
        self.show_only_errors = False
        self.accuracy_label = QLabel("准确率：--")
        self._build_ui()
        self.load_records()
        self.resize(1100, 720)

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        title = QLabel("数据验证")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        self.accuracy_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.accuracy_label.setStyleSheet("font-size: 14px; color: #444444;")
        filter_row = QHBoxLayout()
        filter_row.addStretch()
        filter_row.addWidget(self.accuracy_label)
        filter_row.addSpacing(12)
        filter_row.addWidget(self.error_filter_button)
        layout.addLayout(filter_row)
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
        display_records = records
        if self.show_only_errors:
            display_records = [
                record
                for record in records
                if self._is_record_incorrect(record)
            ]
        display_records = display_records[:50]
        self.table.setRowCount(len(display_records))
        for row_index, record in enumerate(display_records):
            self._render_record(row_index, record)
        self.table.resizeColumnsToContents()

    def load_records(self) -> None:
        try:
            self._load_records()
        except Exception as exc:
            QMessageBox.information(self, "提示", f"加载验证数据失败：{exc}")
            self.table.setRowCount(0)

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
            if self._is_record_correct(record):
                correct += 1
        accuracy = (correct / len(verified)) * 100
        self.accuracy_label.setText(f"准确率：{accuracy:.2f}%")

    def _digit_in_numbers(self, digit: int, numbers_text: str) -> bool:
        numbers = [num.strip() for num in numbers_text.split(",") if num.strip()]
        return str(digit) in numbers

    def _is_record_correct(self, record: PredictionRecord) -> bool:
        digits = self._parse_red_digits(record.red)
        if not digits:
            return False
        return (
            self._digit_in_numbers(digits[0], record.hundreds_dan)
            and self._digit_in_numbers(digits[1], record.tens_dan)
            and self._digit_in_numbers(digits[2], record.units_dan)
        )

    def _is_record_incorrect(self, record: PredictionRecord) -> bool:
        if record.status != "已开奖" or not record.hundreds_dan:
            return False
        return not self._is_record_correct(record)

    def _toggle_error_filter(self) -> None:
        self.show_only_errors = not self.show_only_errors
        self.error_filter_button.setText(
            "显示全部" if self.show_only_errors else "未中记录"
        )
        self._load_records()


def main() -> None:
    app = QApplication([])
    session_store = SessionStore()
    api_client = CentralApiClient()
    session = session_store.load()
    auth_session = session.get("auth", {})
    product_session = session.get("product", {})
    api_client.set_auth_tokens(
        auth_session.get("accessToken"),
        auth_session.get("refreshToken"),
    )
    api_client.set_product_session(
        product_session.get("accessToken"),
        product_session.get("refreshToken"),
        product_session.get("sessionNo"),
        (session.get("deviceProfile") or {}).get("deviceFingerprint"),
    )

    account = None
    if api_client.auth_access_token:
        try:
            account = api_client.get_current_account().get("data", {})
        except ApiError:
            try:
                api_client.refresh_auth_token()
                account = api_client.get_current_account().get("data", {})
            except ApiError:
                session_store.clear()
                api_client.set_auth_tokens(None, None)
                api_client.clear_product_session()
    if not account:
        dialog = AuthDialog(api_client, session_store)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        account = dialog.account
    else:
        device_profile = session.get("deviceProfile") or build_device_profile()
        api_client.set_device_profile(
            {
                **device_profile,
                "productCode": PRODUCT_CODE,
                "clientType": CLIENT_TYPE,
            }
        )
        try:
            api_client.upsert_device(
                {
                    **device_profile,
                    "productCode": PRODUCT_CODE,
                }
            )
            api_client.enter_product(
                {
                    "productCode": PRODUCT_CODE,
                    "clientType": CLIENT_TYPE,
                    "deviceFingerprint": device_profile["deviceFingerprint"],
                    "installId": device_profile["installId"],
                    "loginIp": device_profile["loginIp"],
                    "userAgent": "PyQt6 Desktop Client",
                    "concurrencyStrategy": "KICK_OLD",
                    "requestId": new_request_id("enter-product"),
                }
            )
            api_client.check_access(
                product_code=PRODUCT_CODE,
                session_no=str(api_client.product_session_no or ""),
                device_fingerprint=device_profile["deviceFingerprint"],
            )
            session_store.save(
                {
                    "auth": {
                        "accessToken": api_client.auth_access_token,
                        "refreshToken": api_client.auth_refresh_token,
                    },
                    "product": {
                        "accessToken": api_client.product_access_token,
                        "refreshToken": api_client.product_refresh_token,
                        "sessionNo": api_client.product_session_no,
                    },
                    "account": account,
                    "deviceProfile": device_profile,
                }
            )
        except ApiError:
            session_store.clear()
            dialog = AuthDialog(api_client, session_store)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            account = dialog.account

    window = NumberPredictionWindow(
        storage=RemoteLotteryStorage(api_client),
        account=account,
    )
    window.resize(820, 600)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
