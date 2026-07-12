from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from api_client import ApiClient
from license_manager import LicenseManager


ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "logs" / "desktop.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    try:
        logging.basicConfig(
            filename=str(LOG_PATH),
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
            encoding="utf-8",
        )
    except OSError as exc:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
        logging.warning("Desktop file logging is unavailable at %s: %s", LOG_PATH, exc)


configure_logging()


def draw_3d_sphere(painter: QPainter, x: float, y: float, radius: float, base_color_hex: str, highlight_color_hex: str) -> None:
    color_base = QColor(base_color_hex)
    color_hl = QColor(highlight_color_hex)
    
    grad = QRadialGradient(x + radius * 0.7, y + radius * 0.7, radius * 1.2, x + radius * 0.5, y + radius * 0.5)
    grad.setColorAt(0, color_hl)
    grad.setColorAt(0.7, color_base)
    grad.setColorAt(1.0, QColor(color_base.red(), color_base.green(), color_base.blue(), 0))
    
    painter.setBrush(grad)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(int(x), int(y), int(radius * 2), int(radius * 2))


class SignalOrb(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.signal = "WAIT"
        self.setFixedSize(116, 116)
        self.pulse_val = 0
        self.pulse_dir = 1
        
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._update_pulse)
        self.timer.start()

    def _update_pulse(self) -> None:
        if self.signal == "WAIT":
            if self.pulse_val != 0:
                self.pulse_val = max(0, self.pulse_val - 1)
                self.update()
            return
        self.pulse_val += self.pulse_dir * 1.5
        if self.pulse_val >= 16:
            self.pulse_dir = -1
        elif self.pulse_val <= 0:
            self.pulse_dir = 1
        self.update()

    def set_signal(self, signal: str) -> None:
        self.signal = signal
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size = min(self.width(), self.height()) - 14
        x = (self.width() - size) / 2
        y = (self.height() - size) / 2
        rect = QRectF(x, y, size, size)

        is_buy = "BUY" in self.signal or "UP" in self.signal
        is_sell = "SELL" in self.signal or "DOWN" in self.signal
        color = QColor("#00e676") if is_buy else QColor("#ff1744") if is_sell else QColor("#7a8599")

        glow_multiplier = 0.58 + (self.pulse_val / 160.0)
        glow = QRadialGradient(rect.center(), size * glow_multiplier)
        glow.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 230))
        glow.setColorAt(0.48, QColor(color.red(), color.green(), color.blue(), 140))
        glow.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(rect)

        inner = rect.adjusted(size * 0.16, size * 0.16, -size * 0.16, -size * 0.16)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 235))
        painter.drawEllipse(inner)

        painter.setPen(QPen(QColor("#ffffff"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        cx = inner.center().x()
        cy = inner.center().y()
        if is_buy:
            points = [
                (cx - 28, cy + 18),
                (cx - 10, cy + 1),
                (cx + 3, cy + 12),
                (cx + 28, cy - 16),
            ]
        elif is_sell:
            points = [
                (cx - 28, cy - 13),
                (cx - 8, cy + 5),
                (cx + 5, cy - 5),
                (cx + 28, cy + 18),
            ]
        else:
            points = [
                (cx - 26, cy),
                (cx + 26, cy),
            ]
        for start, end in zip(points, points[1:]):
            painter.drawLine(int(start[0]), int(start[1]), int(end[0]), int(end[1]))

        if is_buy or is_sell:
            arrow_x, arrow_y = points[-1]
            if is_buy:
                painter.drawLine(int(arrow_x), int(arrow_y), int(arrow_x - 2), int(arrow_y + 18))
                painter.drawLine(int(arrow_x), int(arrow_y), int(arrow_x - 18), int(arrow_y + 2))
            else:
                painter.drawLine(int(arrow_x), int(arrow_y), int(arrow_x - 2), int(arrow_y - 18))
                painter.drawLine(int(arrow_x), int(arrow_y), int(arrow_x - 18), int(arrow_y - 2))


class SignalWorker(QThread):
    completed = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(
        self,
        client: ApiClient,
        mode: str,
        pair: str,
        duration: str,
        source_url: str | None,
    ) -> None:
        super().__init__()
        self.client = client
        self.mode = mode
        self.pair = pair
        self.duration = duration
        self.source_url = source_url

    def run(self) -> None:
        try:
            self.completed.emit(
                self.client.generate_signal(self.mode, self.pair, self.duration, self.source_url)
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class MarketRefreshWorker(QThread):
    completed = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(
        self,
        client: ApiClient,
        mode: str,
        pair: str,
        duration: str,
        source_url: str | None,
    ) -> None:
        super().__init__()
        self.client = client
        self.mode = mode
        self.pair = pair
        self.duration = duration
        self.source_url = source_url

    def run(self) -> None:
        try:
            self.completed.emit(
                self.client.refresh_market_data(self.mode, self.pair, self.duration, self.source_url)
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class ScanWorker(QThread):
    completed = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, client: ApiClient, mode: str, duration: str, pairs: list[str] | None = None) -> None:
        super().__init__()
        self.client = client
        self.mode = mode
        self.duration = duration
        self.pairs = pairs

    def run(self) -> None:
        try:
            self.completed.emit(self.client.scan_pairs(self.mode, self.duration, self.pairs))
        except Exception as exc:
            self.failed.emit(str(exc))


class LicenseGateWindow(QDialog):
    def __init__(self, license_manager: LicenseManager, client: ApiClient) -> None:
        super().__init__()
        self.license_manager = license_manager
        self.client = client
        self.setWindowTitle("Shahzaib Bot Portal")
        self.setMinimumWidth(520)
        self.setMinimumHeight(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Decorative macOS Titlebar ──
        title_bar = QFrame()
        title_bar.setObjectName("macTitleBar")
        title_bar.setFixedHeight(38)
        title_bar.setStyleSheet("""
            QFrame#macTitleBar {
                background: transparent;
            }
        """)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 16, 0)
        title_layout.setSpacing(8)
        
        for color in ["#ff5f56", "#ffbd2e", "#27c93f"]:
            dot = QFrame()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
            title_layout.addWidget(dot)
            
        title_layout.addSpacing(10)
        title_label = QLabel("Shahzaib Bot Platform Portal")
        title_label.setStyleSheet("color: #a0aec0; font-size: 13px; font-weight: 800; font-family: 'Segoe UI';")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addWidget(title_bar)

        # Main content container
        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 10, 20, 20)
        content_layout.setSpacing(10)

        # Tab Widget for auth modes
        self.tabs = QTabWidget()
        
        # ── Tab 1: Sign In ──
        self.tab_signin = QWidget()
        signin_layout = QVBoxLayout(self.tab_signin)
        signin_layout.setContentsMargins(15, 15, 15, 15)
        signin_layout.setSpacing(12)
        
        signin_form = QFormLayout()
        self.signin_user = QLineEdit()
        self.signin_user.setPlaceholderText("Enter username")
        self.signin_pass = QLineEdit()
        self.signin_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.signin_pass.setPlaceholderText("Enter password")
        signin_form.addRow("Username", self.signin_user)
        signin_form.addRow("Password", self.signin_pass)
        signin_layout.addLayout(signin_form)
        
        self.signin_status = QLabel("")
        self.signin_status.setStyleSheet("color: #ff4d4d; font-weight: bold;")
        signin_layout.addWidget(self.signin_status)
        
        signin_btn = QPushButton("Sign In")
        signin_btn.setObjectName("primaryGenerate")
        signin_btn.clicked.connect(self.login)
        signin_layout.addWidget(signin_btn)
        
        self.tabs.addTab(self.tab_signin, "Sign In")

        # ── Tab 2: Sign Up ──
        self.tab_signup = QWidget()
        signup_layout = QVBoxLayout(self.tab_signup)
        signup_layout.setContentsMargins(15, 15, 15, 15)
        signup_layout.setSpacing(12)
        
        signup_form = QFormLayout()
        self.signup_user = QLineEdit()
        self.signup_user.setPlaceholderText("Choose username")
        self.signup_email = QLineEdit()
        self.signup_email.setPlaceholderText("Enter email address")
        self.signup_pass = QLineEdit()
        self.signup_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.signup_pass.setPlaceholderText("Choose password (min 6 chars)")
        signup_form.addRow("Username", self.signup_user)
        signup_form.addRow("Email", self.signup_email)
        signup_form.addRow("Password", self.signup_pass)
        signup_layout.addLayout(signup_form)
        
        self.signup_status = QLabel("")
        self.signup_status.setStyleSheet("color: #ff4d4d; font-weight: bold;")
        signup_layout.addWidget(self.signup_status)
        
        signup_btn = QPushButton("Register Account")
        signup_btn.setObjectName("primaryGenerate")
        signup_btn.clicked.connect(self.register)
        signup_layout.addWidget(signup_btn)
        
        self.tabs.addTab(self.tab_signup, "Sign Up")

        # ── Tab 3: Admin Portal ──
        self.tab_admin = QWidget()
        admin_layout = QVBoxLayout(self.tab_admin)
        admin_layout.setContentsMargins(15, 15, 15, 15)
        admin_layout.setSpacing(12)
        
        admin_form = QFormLayout()
        self.admin_pass = QLineEdit()
        self.admin_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_pass.setPlaceholderText("Enter admin password")
        admin_form.addRow("Password", self.admin_pass)
        admin_layout.addLayout(admin_form)
        
        self.admin_status = QLabel("")
        self.admin_status.setStyleSheet("color: #ff4d4d; font-weight: bold;")
        admin_layout.addWidget(self.admin_status)
        
        admin_btn = QPushButton("Open Admin Console")
        admin_btn.setObjectName("primaryGenerate")
        admin_btn.clicked.connect(self.open_admin)
        admin_layout.addWidget(admin_btn)
        
        self.tabs.addTab(self.tab_admin, "Admin Access")

        content_layout.addWidget(self.tabs)
        layout.addWidget(content_widget)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Base deep dark background
        painter.fillRect(self.rect(), QColor("#080b11"))
        
        # 1. Big Purple Sphere (Top-Left)
        draw_3d_sphere(painter, -60, -60, 160, "#4a0e4e", "#a020f0")
        # 2. Big Orange Sphere (Bottom-Right)
        draw_3d_sphere(painter, self.width() - 260, self.height() - 260, 180, "#d35400", "#ffaa00")
        # 3. Small Orange Sphere (Left-Middle)
        draw_3d_sphere(painter, 30, 280, 22, "#e67e22", "#ff9f43")
        # 4. Small Purple Sphere (Right-Middle)
        draw_3d_sphere(painter, self.width() - 80, 100, 26, "#8e44ad", "#d289e3")

    def login(self) -> None:
        username = self.signin_user.text().strip()
        password = self.signin_pass.text()
        if not username or not password:
            self.signin_status.setText("All fields are required.")
            return
            
        try:
            # Step 1: Login
            result = self.client.user_login(username, password)
            user_id = result["user_id"]
            token = result["token"]
            
            # Step 2: Get or generate API Key
            keys = self.client.user_get_keys()
            if keys:
                api_key = keys[0]["key"]
            else:
                # Create a key automatically for them on first login
                new_key = self.client.user_create_key(name="Desktop Auto Key")
                api_key = new_key["key"]
                
            # Step 3: Save session cache
            self.license_manager.save_session(
                username=username,
                user_id=user_id,
                session_token=token,
                api_key=api_key
            )
            
            # Inject to client
            self.client.api_key = api_key
            self.client.user_id = str(user_id)
            self.client.user_token = token
            
            self.accept()
        except Exception as exc:
            self.signin_status.setText(f"Login failed: {exc}")

    def register(self) -> None:
        username = self.signup_user.text().strip()
        email = self.signup_email.text().strip()
        password = self.signup_pass.text()
        if not username or not email or not password:
            self.signup_status.setText("All fields are required.")
            return
            
        try:
            # Register user
            self.client.user_register(username, email, password)
            self.signup_status.setStyleSheet("color: #2ed573;")
            self.signup_status.setText("Account created! Logging in...")
            
            # Log in automatically
            result = self.client.user_login(username, password)
            user_id = result["user_id"]
            token = result["token"]
            
            # Generate API Key
            new_key = self.client.user_create_key(name="Desktop Auto Key")
            api_key = new_key["key"]
            
            # Save session
            self.license_manager.save_session(
                username=username,
                user_id=user_id,
                session_token=token,
                api_key=api_key
            )
            
            # Inject
            self.client.api_key = api_key
            self.client.user_id = str(user_id)
            self.client.user_token = token
            
            self.accept()
        except Exception as exc:
            self.signup_status.setStyleSheet("color: #ff6b6b;")
            self.signup_status.setText(f"Registration failed: {exc}")

    def open_admin(self) -> None:
        password = self.admin_pass.text()
        if not password:
            self.admin_status.setText("Password is required.")
            return
            
        try:
            self.client.admin_login(password)
            self.admin_status.setText("")
            self.admin_pass.clear()
            
            dialog = AdminLicenseDialog(self.license_manager, self.client, self)
            dialog.exec()
        except Exception as exc:
            self.admin_status.setText(f"Admin login failed: {exc}")


class AdminLicenseDialog(QDialog):
    def __init__(self, license_manager: LicenseManager, client: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.license_manager = license_manager
        self.client = client
        self.setWindowTitle("Admin Dashboard")
        self.setMinimumWidth(820)
        self.setMinimumHeight(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Decorative macOS Titlebar ──
        title_bar = QFrame()
        title_bar.setObjectName("macTitleBar")
        title_bar.setFixedHeight(38)
        title_bar.setStyleSheet("""
            QFrame#macTitleBar {
                background: transparent;
            }
        """)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 16, 0)
        title_layout.setSpacing(8)
        
        for color in ["#ff5f56", "#ffbd2e", "#27c93f"]:
            dot = QFrame()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
            title_layout.addWidget(dot)
            
        title_layout.addSpacing(10)
        title_label = QLabel("Shahzaib Bot Admin Panel Dashboard")
        title_label.setStyleSheet("color: #a0aec0; font-size: 13px; font-weight: 800; font-family: 'Segoe UI';")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addWidget(title_bar)

        # Main content container
        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 10, 20, 20)
        content_layout.setSpacing(10)

        self.tabs = QTabWidget()

        # ── Tab 1: Users Management ──
        self.tab_users = QWidget()
        users_layout = QVBoxLayout(self.tab_users)
        users_layout.setContentsMargins(15, 15, 15, 15)
        users_layout.setSpacing(10)
        
        self.users_table = QTableWidget(0, 8)
        self.users_table.setHorizontalHeaderLabels([
            "ID", "Username", "Email", "Registered At", "Active", "Role", "Tier", "Subscription Expires"
        ])
        self.users_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.users_table.verticalHeader().setVisible(False)
        users_layout.addWidget(self.users_table)
        
        users_btn_layout = QHBoxLayout()
        refresh_users_btn = QPushButton("Refresh Users List")
        refresh_users_btn.clicked.connect(self.list_users)
        users_btn_layout.addWidget(refresh_users_btn)
        
        self.suspend_btn = QPushButton("Suspend User")
        self.suspend_btn.clicked.connect(self.suspend_user)
        self.activate_btn = QPushButton("Activate User")
        self.activate_btn.clicked.connect(self.activate_user)
        self.extend_sub_btn = QPushButton("Extend Sub")
        self.extend_sub_btn.clicked.connect(self.extend_user_subscription)
        self.toggle_vip_btn = QPushButton("Toggle VIP")
        self.toggle_vip_btn.clicked.connect(self.toggle_user_vip)
        
        users_btn_layout.addWidget(self.suspend_btn)
        users_btn_layout.addWidget(self.activate_btn)
        users_btn_layout.addWidget(self.extend_sub_btn)
        users_btn_layout.addWidget(self.toggle_vip_btn)
        users_layout.addLayout(users_btn_layout)
        
        self.tabs.addTab(self.tab_users, "Manage Users")

        # ── Tab 2: API Keys Management ──
        self.tab_keys = QWidget()
        keys_layout = QVBoxLayout(self.tab_keys)
        keys_layout.setContentsMargins(15, 15, 15, 15)
        keys_layout.setSpacing(10)
        
        self.keys_table = QTableWidget(0, 5)
        self.keys_table.setHorizontalHeaderLabels(["Key", "Owner", "Created At", "Active", "Last Activity"])
        self.keys_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.keys_table.verticalHeader().setVisible(False)
        keys_layout.addWidget(self.keys_table)
        
        keys_btn_layout = QHBoxLayout()
        refresh_keys_btn = QPushButton("Refresh Keys List")
        refresh_keys_btn.clicked.connect(self.list_keys)
        keys_btn_layout.addWidget(refresh_keys_btn)
        
        self.disable_key_btn = QPushButton("Disable Key")
        self.disable_key_btn.clicked.connect(self.disable_key)
        self.enable_key_btn = QPushButton("Enable Key")
        self.enable_key_btn.clicked.connect(self.enable_key)
        keys_btn_layout.addWidget(self.disable_key_btn)
        keys_btn_layout.addWidget(self.enable_key_btn)
        keys_layout.addLayout(keys_btn_layout)
        
        self.tabs.addTab(self.tab_keys, "Manage API Keys")

        # ── Tab 3: Admin Security Settings ──
        self.tab_settings = QWidget()
        settings_layout = QVBoxLayout(self.tab_settings)
        settings_layout.setContentsMargins(15, 15, 15, 15)
        settings_layout.setSpacing(12)
        
        password_form = QFormLayout()
        self.current_password_input = QLineEdit()
        self.current_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.current_password_input.setPlaceholderText("Current admin password")
        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password_input.setPlaceholderText("New password")
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_input.setPlaceholderText("Confirm new password")
        password_form.addRow("Current", self.current_password_input)
        password_form.addRow("New", self.new_password_input)
        password_form.addRow("Confirm", self.confirm_password_input)
        settings_layout.addLayout(password_form)
        
        change_button = QPushButton("Change Admin Password")
        change_button.clicked.connect(self.change_password)
        settings_layout.addWidget(change_button)
        
        self.tabs.addTab(self.tab_settings, "Admin Settings")

        content_layout.addWidget(self.tabs)
        layout.addWidget(content_widget)

        # Initial load
        self.list_users()
        self.list_keys()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Base deep dark background
        painter.fillRect(self.rect(), QColor("#080b11"))
        
        # 1. Big Purple Sphere (Top-Left)
        draw_3d_sphere(painter, -80, -80, 200, "#4a0e4e", "#a020f0")
        # 2. Big Orange Sphere (Bottom-Right)
        draw_3d_sphere(painter, self.width() - 320, self.height() - 320, 220, "#d35400", "#ffaa00")
        # 3. Small Orange Sphere (Left-Middle)
        draw_3d_sphere(painter, 40, 360, 24, "#e67e22", "#ff9f43")
        # 4. Small Purple Sphere (Right-Middle)
        draw_3d_sphere(painter, self.width() - 100, 160, 28, "#8e44ad", "#d289e3")

    def list_users(self) -> None:
        try:
            users = self.client.admin_list_users()
            self.users_table.setRowCount(0)
            for user in users:
                row = self.users_table.rowCount()
                self.users_table.insertRow(row)
                self.users_table.setItem(row, 0, QTableWidgetItem(str(user.get("id", ""))))
                self.users_table.setItem(row, 1, QTableWidgetItem(user.get("username", "")))
                self.users_table.setItem(row, 2, QTableWidgetItem(user.get("email", "")))
                self.users_table.setItem(row, 3, QTableWidgetItem(user.get("created_at", "")))
                self.users_table.setItem(row, 4, QTableWidgetItem("Active" if user.get("is_active") else "Suspended"))
                self.users_table.setItem(row, 5, QTableWidgetItem(user.get("role", "")))
                self.users_table.setItem(row, 6, QTableWidgetItem(user.get("subscription_tier", "")))
                self.users_table.setItem(row, 7, QTableWidgetItem(user.get("subscription_expires_at", "") or "Never/N/A"))
        except Exception as exc:
            QMessageBox.warning(self, "Admin", f"Failed to list users: {exc}")

    def list_keys(self) -> None:
        try:
            keys = self.client.admin_list_keys()
            self.keys_table.setRowCount(0)
            for key in keys:
                row = self.keys_table.rowCount()
                self.keys_table.insertRow(row)
                self.keys_table.setItem(row, 0, QTableWidgetItem(key.get("key", "")))
                self.keys_table.setItem(row, 1, QTableWidgetItem(key.get("username", "")))
                self.keys_table.setItem(row, 2, QTableWidgetItem(key.get("created_at", "")))
                self.keys_table.setItem(row, 3, QTableWidgetItem("Active" if key.get("is_active") else "Disabled"))
                self.keys_table.setItem(row, 4, QTableWidgetItem(key.get("last_activity", "") or "--"))
        except Exception as exc:
            QMessageBox.warning(self, "Admin", f"Failed to list API keys: {exc}")

    def suspend_user(self) -> None:
        selected = self.users_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Admin", "Select a user from the table.")
            return
        user_id = int(self.users_table.item(selected, 0).text())
        try:
            self.client.admin_update_user_status(user_id, is_active=False)
            self.list_users()
            QMessageBox.information(self, "Admin", "User suspended successfully.")
        except Exception as exc:
            QMessageBox.warning(self, "Admin", f"Failed to suspend user: {exc}")

    def activate_user(self) -> None:
        selected = self.users_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Admin", "Select a user from the table.")
            return
        user_id = int(self.users_table.item(selected, 0).text())
        try:
            self.client.admin_update_user_status(user_id, is_active=True)
            self.list_users()
            QMessageBox.information(self, "Admin", "User activated successfully.")
        except Exception as exc:
            QMessageBox.warning(self, "Admin", f"Failed to activate user: {exc}")

    def extend_user_subscription(self) -> None:
        selected = self.users_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Admin", "Select a user from the table.")
            return
        user_id = int(self.users_table.item(selected, 0).text())
        tier = self.users_table.item(selected, 6).text()
        expires_at_str = self.users_table.item(selected, 7).text()
        
        days, ok = QInputDialog.getInt(self, "Extend Subscription", "Enter extension days:", 30, 1, 3650)
        if not ok:
            return
            
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        base_time = now
        if expires_at_str and expires_at_str not in ("Never/N/A", ""):
            try:
                parsed = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if parsed > now:
                    base_time = parsed
            except Exception:
                pass
                
        new_expires = (base_time + timedelta(days=days)).isoformat()
        try:
            self.client.admin_update_user_subscription(user_id, tier, new_expires)
            self.list_users()
            QMessageBox.information(self, "Admin", f"Subscription extended by {days} days.")
        except Exception as exc:
            QMessageBox.warning(self, "Admin", f"Failed to extend subscription: {exc}")

    def toggle_user_vip(self) -> None:
        selected = self.users_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Admin", "Select a user from the table.")
            return
        user_id = int(self.users_table.item(selected, 0).text())
        current_tier = self.users_table.item(selected, 6).text()
        expires_at_str = self.users_table.item(selected, 7).text()
        
        new_tier = "vip" if current_tier.lower() != "vip" else "premium"
        expires_val = None if expires_at_str == "Never/N/A" else expires_at_str
        
        try:
            self.client.admin_update_user_subscription(user_id, new_tier, expires_val)
            self.list_users()
            QMessageBox.information(self, "Admin", f"User tier toggled to {new_tier.upper()}.")
        except Exception as exc:
            QMessageBox.warning(self, "Admin", f"Failed to toggle tier: {exc}")

    def disable_key(self) -> None:
        selected = self.keys_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Admin", "Select an API key from the table.")
            return
        key = self.keys_table.item(selected, 0).text()
        try:
            self.client.admin_update_key_status(key, is_active=False)
            self.list_keys()
            QMessageBox.information(self, "Admin", "API Key disabled successfully.")
        except Exception as exc:
            QMessageBox.warning(self, "Admin", f"Failed to disable key: {exc}")

    def enable_key(self) -> None:
        selected = self.keys_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Admin", "Select an API key from the table.")
            return
        key = self.keys_table.item(selected, 0).text()
        try:
            self.client.admin_update_key_status(key, is_active=True)
            self.list_keys()
            QMessageBox.information(self, "Admin", "API Key enabled successfully.")
        except Exception as exc:
            QMessageBox.warning(self, "Admin", f"Failed to enable key: {exc}")

    def change_password(self) -> None:
        new_password = self.new_password_input.text()
        if new_password != self.confirm_password_input.text():
            QMessageBox.warning(self, "Admin", "New password confirmation does not match.")
            return
        try:
            self.client.admin_change_password(
                self.current_password_input.text(),
                new_password,
            )
            QMessageBox.information(self, "Admin", "Admin password changed.")
            self.current_password_input.clear()
            self.new_password_input.clear()
            self.confirm_password_input.clear()
        except Exception as exc:
            QMessageBox.warning(self, "Admin", f"Password change failed: {exc}")


class UserProfileDialog(QDialog):
    def __init__(self, license_manager: LicenseManager, client: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.license_manager = license_manager
        self.client = client
        self.setWindowTitle("User Profile")
        self.setMinimumSize(420, 520)
        self.setModal(True)
        self.logout_clicked = False
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # ── Decorative macOS Titlebar ──
        title_bar = QFrame()
        title_bar.setObjectName("macTitleBar")
        title_bar.setFixedHeight(38)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 16, 0)
        title_layout.setSpacing(8)
        for color in ["#ff5f56", "#ffbd2e", "#27c93f"]:
            dot = QFrame()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
            title_layout.addWidget(dot)
        title_layout.addSpacing(10)
        title_label = QLabel("User Profile Info")
        title_label.setStyleSheet("color: #a0aec0; font-size: 13px; font-weight: 800; font-family: 'Segoe UI';")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addWidget(title_bar)
        
        # Centered glass card
        card_widget = QWidget()
        card_widget.setStyleSheet("background: transparent;")
        card_layout = QVBoxLayout(card_widget)
        card_layout.setContentsMargins(20, 10, 20, 20)
        card_layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("glassCard")
        card.setStyleSheet("""
            QFrame#glassCard {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 20px;
            }
        """)
        inner_layout = QVBoxLayout(card)
        inner_layout.setContentsMargins(25, 25, 25, 25)
        inner_layout.setSpacing(14)
        
        # User Avatar Icon
        avatar = QLabel("U")
        avatar.setFixedSize(64, 64)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8e2de2, stop:1 #4a0e4e);
            color: #ffffff;
            border-radius: 32px;
            font-size: 24px;
            font-weight: bold;
            border: 2px solid rgba(255, 255, 255, 0.3);
        """)
        inner_layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignCenter)
        
        stored = self.license_manager.validate()
        username = stored.owner if stored.valid else "Unknown User"
        user_id = stored.user_id if stored.valid else "N/A"
        api_key = stored.api_key if stored.valid else "No Key Found"
        
        # Load subscription details live from backend
        sub_tier = "Premium Plan"
        sub_expires = "N/A"
        try:
            profile = self.client.get_user_profile()
            sub_tier = profile.get("subscription_tier", "premium").upper()
            sub_expires_raw = profile.get("subscription_expires_at", "")
            if sub_expires_raw:
                try:
                    dt = datetime.fromisoformat(sub_expires_raw.replace("Z", "+00:00"))
                    sub_expires = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    sub_expires = sub_expires_raw
            else:
                sub_expires = "Never"
        except Exception:
            pass

        # Profile details form
        details_layout = QFormLayout()
        details_layout.setSpacing(10)
        
        def create_label(val, is_header=True):
            l = QLabel(val)
            if is_header:
                l.setStyleSheet("color: #a0aec0; font-weight: bold; font-size: 13px;")
            else:
                l.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 14px;")
            return l
            
        details_layout.addRow(create_label("Username:"), create_label(username, False))
        details_layout.addRow(create_label("User ID:"), create_label(str(user_id), False))
        details_layout.addRow(create_label("SaaS Tier:"), create_label(sub_tier, False))
        details_layout.addRow(create_label("Subscription Expiry:"), create_label(sub_expires, False))
        
        # API Key display field
        self.api_key_field = QLineEdit(api_key)
        self.api_key_field.setReadOnly(True)
        self.api_key_field.setStyleSheet("""
            background: rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.1);
            color: #ffaa00;
            border-radius: 8px;
            padding: 8px;
            font-family: Consolas, monospace;
            font-weight: bold;
        """)
        details_layout.addRow(create_label("API Key:"), self.api_key_field)
        inner_layout.addLayout(details_layout)
        
        # Buttons layout
        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("Copy Key")
        copy_btn.clicked.connect(self.copy_key)
        regen_btn = QPushButton("Re-generate")
        regen_btn.clicked.connect(self.regenerate_key)
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(regen_btn)
        inner_layout.addLayout(btn_layout)
        
        inner_layout.addSpacing(8)
        
        # Logout
        logout_btn = QPushButton("Log Out Account")
        logout_btn.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff1744, stop:1 #b30022);
            color: #ffffff;
            border: none;
            font-weight: bold;
            min-height: 38px;
            border-radius: 10px;
        """)
        logout_btn.clicked.connect(self.logout)
        inner_layout.addWidget(logout_btn)
        
        # Close button
        close_btn = QPushButton("Close Profile")
        close_btn.clicked.connect(self.close)
        inner_layout.addWidget(close_btn)
        
        card_layout.addWidget(card)
        layout.addWidget(card_widget)
        
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#080b11"))
        draw_3d_sphere(painter, -30, -30, 100, "#4a0e4e", "#a020f0")
        draw_3d_sphere(painter, self.width() - 150, self.height() - 150, 120, "#d35400", "#ffaa00")
        
    def copy_key(self) -> None:
        QApplication.clipboard().setText(self.api_key_field.text())
        QMessageBox.information(self, "Profile", "API Key copied to clipboard.")
        
    def regenerate_key(self) -> None:
        try:
            new_key = self.client.user_create_key(name="Desktop Client Key")
            api_key = new_key["key"]
            
            stored = self.license_manager.validate()
            self.license_manager.save_session(
                username=stored.owner,
                user_id=stored.user_id,
                session_token=stored.session_token,
                api_key=api_key
            )
            
            self.client.api_key = api_key
            self.api_key_field.setText(api_key)
            QMessageBox.information(self, "Profile", "New API Key generated successfully.")
        except Exception as exc:
            QMessageBox.warning(self, "Profile", f"Failed to regenerate key: {exc}")
            
    def logout(self) -> None:
        self.license_manager.clear_session()
        self.logout_clicked = True
        self.accept()


class TradingSignalWindow(QMainWindow):
    def __init__(self, license_manager: LicenseManager | None = None, client: ApiClient | None = None) -> None:
        super().__init__()
        self.license_manager = license_manager or LicenseManager()
        self.client = client or ApiClient()
        # Inject stored credentials into the API client
        stored_key, stored_user_id, stored_token = self.license_manager.get_stored_credentials()
        if stored_key:
            self.client.api_key = stored_key
        if stored_user_id:
            self.client.user_id = stored_user_id
        if stored_token:
            self.client.user_token = stored_token
        self.config = {
            "pairs": {
                "Crypto": [
                    "Bitcoin Cash (OTC)",
                    "Binance Coin (OTC)",
                    "Bitcoin (OTC)",
                    "Litecoin (OTC)",
                    "Solana (OTC)",
                    "Axie Infinity (OTC)",
                    "Polkadot (OTC)",
                    "Ripple (OTC)",
                    "Ethereum Classic (OTC)",
                    "Cosmos (OTC)",
                    "Zcash (OTC)",
                    "Chainlink (OTC)",
                    "Avalanche (OTC)",
                    "Trump (OTC)",
                    "Ethereum (OTC)",
                    "Toncoin (OTC)",
                    "Dash (OTC)",
                ],
                "Binance Spot": [
                    "BTC/USDT",
                    "ETH/USDT",
                    "BNB/USDT",
                    "SOL/USDT",
                    "XRP/USDT",
                    "BCH/USDT",
                    "LTC/USDT",
                    "AVAX/USDT",
                    "DOT/USDT",
                    "LINK/USDT",
                ],
                "Quotex": [
                    "EUR/USD OTC",
                    "GBP/USD OTC",
                    "USD/JPY OTC",
                    "AUD/USD OTC",
                    "AUD/JPY OTC",
                    "AUD/CAD OTC",
                    "AUD/CHF OTC",
                    "AUD/NZD OTC",
                    "EUR/GBP OTC",
                    "EUR/AUD OTC",
                    "EUR/CAD OTC",
                    "EUR/CHF OTC",
                    "EUR/NZD OTC",
                    "GBP/AUD OTC",
                    "GBP/CAD OTC",
                    "GBP/CHF OTC",
                    "GBP/JPY OTC",
                    "GBP/NZD OTC",
                    "CAD/CHF OTC",
                    "CAD/JPY OTC",
                    "CHF/JPY OTC",
                    "NZD/CAD OTC",
                    "NZD/CHF OTC",
                    "NZD/JPY OTC",
                    "NZD/USD OTC",
                    "USD/IDR OTC",
                    "USD/INR OTC",
                    "USD/BRL OTC",
                    "USD/BDT OTC",
                    "USD/EGP OTC",
                    "USD/ARS OTC",
                    "USD/COP OTC",
                    "USD/DZD OTC",
                    "USD/MXN OTC",
                    "USD/NGN OTC",
                    "USD/PHP OTC",
                    "USD/ZAR OTC",
                ],
                "Forex": [
                    "EUR/USD",
                    "GBP/USD",
                    "USD/JPY",
                    "AUD/USD",
                    "AUD/JPY",
                    "AUD/CAD",
                    "AUD/CHF",
                    "AUD/NZD",
                    "EUR/JPY",
                    "EUR/AUD",
                    "EUR/CAD",
                    "EUR/CHF",
                    "EUR/NZD",
                    "USD/CAD",
                    "USD/CHF",
                    "EUR/GBP",
                    "GBP/JPY",
                    "GBP/CAD",
                    "GBP/AUD",
                    "GBP/CHF",
                    "GBP/NZD",
                    "CAD/CHF",
                    "CAD/JPY",
                    "CHF/JPY",
                    "NZD/CAD",
                    "NZD/CHF",
                    "NZD/JPY",
                    "NZD/USD",
                ],
            },
            "modes": ["Crypto", "Binance Spot", "Quotex", "Forex"],
            "durations": ["5 Seconds", "10 Seconds", "15 Seconds", "30 Seconds", "1 Minute", "5 Minutes"],
        }
        self.worker: QThread | None = None
        self.market_worker: QThread | None = None
        self.trade_active = False
        self.trade_remaining_seconds = 0
        self.trade_timer = QTimer(self)
        self.trade_timer.setInterval(1000)
        self.trade_timer.timeout.connect(self._tick_trade_timer)
        self.market_timer = QTimer(self)
        self.market_timer.setInterval(1000)
        self.market_timer.timeout.connect(self._tick_market_refresh)
        self.setWindowTitle("AI Trading Signal Application")
        self.setMinimumSize(1080, 700)
        self.setWindowIcon(QIcon(str(ROOT / "assets" / "app_icon.svg")))
        self._load_config()
        self._build_ui()
        self._apply_theme()

        self.refresh_history()
        self.refresh_statistics()
        self.market_timer.start()

    def _load_config(self) -> None:
        try:
            api_config = self.client.get_config()
            self.config = {
                **api_config,
                "modes": ["Crypto", "Binance Spot", "Quotex", "Forex"],
            }
        except Exception:
            logging.warning("Using fallback config because backend is not reachable.", exc_info=True)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(38, 12, 38, 18)
        layout.setSpacing(10)

        # ── Decorative macOS Titlebar ──
        title_bar = QFrame()
        title_bar.setObjectName("macTitleBar")
        title_bar.setFixedHeight(38)
        title_bar.setStyleSheet("""
            QFrame#macTitleBar {
                background: transparent;
            }
        """)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)
        
        for color in ["#ff5f56", "#ffbd2e", "#27c93f"]:
            dot = QFrame()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
            title_layout.addWidget(dot)
            
        title_layout.addSpacing(10)
        title_label = QLabel("Shahzaib Bot Premium Trading Terminal")
        title_label.setStyleSheet("color: #a0aec0; font-size: 13px; font-weight: 800; font-family: 'Segoe UI';")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addWidget(title_bar)

        header = QHBoxLayout()
        self.profile_button = QPushButton("PROFILE")
        self.profile_button.setObjectName("adminButton")
        self.profile_button.clicked.connect(self.open_profile)
        
        self.admin_button = QPushButton("ADMIN")
        self.admin_button.setObjectName("adminButton")
        self.admin_button.clicked.connect(self.open_admin_license)
        
        header.addStretch()
        header.addWidget(self.profile_button)
        header.addSpacing(10)
        header.addWidget(self.admin_button)
        layout.addLayout(header)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 20)
        hero_layout.setSpacing(10)
        hero_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo = QLabel("O")
        logo.setObjectName("logoMark")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(58, 58)
        brand = QLabel("Shahzaib Bot")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        test_pill = QLabel("  TEST   Interface Testing Mode  -  GUI MENU ACTIVE  ")
        test_pill.setObjectName("testPill")
        test_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stats = QLabel("Signals: 508,437    |    Accuracy: 98.8%    Verify Accuracy")
        stats.setObjectName("stats")
        stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(brand)
        hero_layout.addWidget(test_pill, alignment=Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(stats)
        layout.addWidget(hero)

        content = QGridLayout()
        content.setHorizontalSpacing(24)
        content.setVerticalSpacing(18)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(self.config.get("modes", ["Crypto"]))
        self.mode_combo.setCurrentText("Crypto")
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)

        self.pair_combo = QComboBox()
        self.duration_combo = QComboBox()
        self.duration_combo.addItems(self.config["durations"])
        self.duration_combo.setCurrentText("15 Seconds")

        self.link_input = QLineEdit()
        self.link_input.setVisible(False)

        self.generate_button = QPushButton("Generate Signal")
        self.generate_button.clicked.connect(self.generate_signal)
        self.refresh_market_button = QPushButton("Refresh Market Data")
        self.refresh_market_button.clicked.connect(self.refresh_market_data)
        self.scan_button = QPushButton("Multi Pair Scanner")
        self.scan_button.clicked.connect(self.scan_pairs)

        for field in [
            self.mode_combo,
            self.pair_combo,
            self.duration_combo,
            self.generate_button,
            self.refresh_market_button,
            self.scan_button,
        ]:
            field.setMinimumHeight(36)
            field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.generate_button.setVisible(False)
        self.refresh_market_button.setVisible(False)
        self.scan_button.setVisible(False)

        left_panel = QFrame()
        left_panel.setObjectName("leftStack")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(16)

        platform_card = QFrame()
        platform_card.setObjectName("card")
        platform_card.setMinimumHeight(112)
        platform_layout = QVBoxLayout(platform_card)
        platform_layout.setContentsMargins(24, 20, 24, 20)
        platform_layout.setSpacing(12)
        platform_title = QLabel("Trading Platform")
        platform_title.setObjectName("cardTitle")
        platform_layout.addWidget(platform_title)
        platform_layout.addWidget(self.mode_combo)
        left_layout.addWidget(platform_card)

        market_card = QFrame()
        market_card.setObjectName("card")
        market_card.setMinimumHeight(112)
        market_layout = QVBoxLayout(market_card)
        market_layout.setContentsMargins(24, 20, 24, 20)
        market_layout.setSpacing(12)
        market_title = QLabel("Market Type")
        market_title.setObjectName("cardTitle")
        self.provider_hint_label = QLabel("")
        self.provider_hint_label.setObjectName("providerHint")
        self.provider_hint_label.setWordWrap(True)
        market_layout.addWidget(market_title)
        market_layout.addWidget(self.provider_hint_label)
        left_layout.addWidget(market_card)

        pair_card = QFrame()
        pair_card.setObjectName("card")
        pair_card.setMinimumHeight(112)
        pair_layout = QVBoxLayout(pair_card)
        pair_layout.setContentsMargins(24, 20, 24, 20)
        pair_layout.setSpacing(12)
        pair_title = QLabel("Currency Pair")
        pair_title.setObjectName("cardTitle")
        pair_layout.addWidget(pair_title)
        pair_layout.addWidget(self.pair_combo)
        left_layout.addWidget(pair_card)

        bridge_card = QFrame()
        self.bridge_card = bridge_card
        bridge_card.setObjectName("card")
        bridge_card.setMinimumHeight(112)
        bridge_layout = QVBoxLayout(bridge_card)
        bridge_layout.setContentsMargins(24, 20, 24, 20)
        bridge_layout.setSpacing(12)
        bridge_title = QLabel("Bridge API URL")
        bridge_title.setObjectName("cardTitle")
        bridge_layout.addWidget(bridge_title)
        bridge_layout.addWidget(self.link_input)
        left_layout.addWidget(bridge_card)

        time_card = QFrame()
        time_card.setObjectName("card")
        time_card.setMinimumHeight(112)
        time_layout = QVBoxLayout(time_card)
        time_layout.setContentsMargins(24, 20, 24, 20)
        time_layout.setSpacing(12)
        time_title = QLabel("Time Frame")
        time_title.setObjectName("cardTitle")
        time_layout.addWidget(time_title)
        time_layout.addWidget(self.duration_combo)
        left_layout.addWidget(time_card)

        signal_panel = QFrame()
        signal_panel.setObjectName("signalPanel")
        signal_panel.setMinimumHeight(340)
        signal_layout = QVBoxLayout(signal_panel)
        signal_layout.setContentsMargins(28, 30, 28, 28)
        signal_layout.setSpacing(14)

        self.result_pair_label = QLabel("Pair: --")
        self.result_pair_label.setObjectName("summary")
        self.result_signal_label = QLabel("WAIT")
        self.result_signal_label.setObjectName("resultSignal")
        self.result_confidence_label = QLabel("Confidence: --")
        self.result_price_label = QLabel("Price: --")
        self.result_duration_label = QLabel("Trade Time: --")
        self.result_trend_label = QLabel("Trend: --")
        self.result_status_label = QLabel("Status: --")
        self.result_update_label = QLabel("Market Update: --")

        for label in [
            self.result_pair_label,
            self.result_confidence_label,
            self.result_price_label,
            self.result_duration_label,
            self.result_trend_label,
            self.result_status_label,
            self.result_update_label,
        ]:
            label.setObjectName("summary")
            label.setWordWrap(True)
            label.setMinimumHeight(48)
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.result_signal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_signal_label.setMinimumHeight(86)
        self.result_signal_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        ready_label = QLabel("Ready to generate signals")
        ready_label.setObjectName("readyLabel")
        ready_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        signal_layout.addWidget(ready_label)
        signal_layout.addWidget(self.result_signal_label)
        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(10)
        metric_grid.setVerticalSpacing(10)
        metric_grid.addWidget(self.result_confidence_label, 0, 0)
        metric_grid.addWidget(self.result_trend_label, 0, 1)
        metric_grid.addWidget(self.result_price_label, 1, 0)
        metric_grid.addWidget(self.result_status_label, 1, 1)
        metric_grid.addWidget(self.result_pair_label, 2, 0)
        metric_grid.addWidget(self.result_duration_label, 2, 1)
        metric_grid.addWidget(self.result_update_label, 3, 0, 1, 2)
        signal_layout.addLayout(metric_grid)

        self.primary_generate_button = QPushButton("Generate New Signal")
        self.primary_generate_button.setObjectName("primaryGenerate")
        self.primary_generate_button.clicked.connect(self.generate_signal)
        self.primary_generate_button.setMinimumHeight(64)
        signal_layout.addWidget(self.primary_generate_button)

        self.primary_refresh_button = QPushButton("Refresh Market Data")
        self.primary_refresh_button.setObjectName("secondaryGenerate")
        self.primary_refresh_button.clicked.connect(self.refresh_market_data)
        self.primary_refresh_button.setMinimumHeight(58)
        signal_layout.addWidget(self.primary_refresh_button)

        content.addWidget(left_panel, 0, 0)
        content.addWidget(signal_panel, 0, 1)
        content.setColumnStretch(0, 1)
        content.setColumnStretch(1, 1)
        layout.addLayout(content)

        self.analysis_text = QPlainTextEdit()
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setPlainText("Analysis will appear after the first signal.")
        self.analysis_text.setObjectName("analysis")
        self.analysis_text.setFixedHeight(104)
        layout.addWidget(self.analysis_text)

        self.scan_table = self._table(["Pair", "Price", "Signal", "Confidence", "Duration", "Trend", "Status"])
        self.scan_table.setVisible(False)
        scanner_label = QLabel("Scanner")
        scanner_label.setObjectName("sectionTitle")
        scanner_label.setVisible(False)

        self.history_table = self._table(["ID", "Date Time", "Pair", "Signal", "Confidence", "Duration", "Trend", "Outcome"])
        self.history_table.setVisible(False)
        history_label = QLabel("Signal History")
        history_label.setObjectName("sectionTitle")
        history_label.setVisible(False)

        stats_layout = QHBoxLayout()
        self.stats_label = QLabel("Statistics: --")
        self.stats_label.setVisible(False)
        win_button = QPushButton("Mark WIN")
        loss_button = QPushButton("Mark LOSS")
        breakeven_button = QPushButton("Mark BREAKEVEN")
        win_button.setVisible(False)
        loss_button.setVisible(False)
        breakeven_button.setVisible(False)
        win_button.clicked.connect(lambda: self.mark_selected_outcome("WIN"))
        loss_button.clicked.connect(lambda: self.mark_selected_outcome("LOSS"))
        breakeven_button.clicked.connect(lambda: self.mark_selected_outcome("BREAKEVEN"))
        refresh_button = QPushButton("Refresh History")
        refresh_button.setVisible(False)
        refresh_button.clicked.connect(lambda: (self.refresh_history(), self.refresh_statistics()))
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()
        stats_layout.addWidget(win_button)
        stats_layout.addWidget(loss_button)
        stats_layout.addWidget(breakeven_button)
        stats_layout.addWidget(refresh_button)
        layout.addLayout(stats_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(root)
        self.setCentralWidget(scroll)
        self._on_mode_changed(self.mode_combo.currentText())

    def _card(self, title: str, value: str) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 12, 10, 10)
        label = QLabel(value)
        label.setObjectName("metric")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        box.setMinimumHeight(74)
        layout.addWidget(label)
        box.value_label = label
        return box

    def _control_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("controlLabel")
        label.setMinimumHeight(36)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return label

    def _table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        return table

    def open_admin_license(self) -> None:
        status = self.license_manager.validate()
        dialog = AdminLicenseDialog(self.license_manager, self.client, self)
        if status.valid and status.expires_at:
            # We don't have output plain text edit anymore in standard tabs, but we check if attribute exists to avoid crash
            if hasattr(dialog, "output"):
                dialog.output.setPlainText(
                    f"Active license: {status.owner}\nExpires: {status.expires_at.isoformat()}\nDevice ID: {status.machine_id}"
                )
        dialog.exec()

    def open_profile(self) -> None:
        dialog = UserProfileDialog(self.license_manager, self.client, self)
        dialog.exec()
        if dialog.logout_clicked:
            self.hide()
            self.client.user_logout()
            
            # Show login gate
            gate = LicenseGateWindow(self.license_manager, self.client)
            if gate.exec() == QDialog.DialogCode.Accepted:
                stored = self.license_manager.validate()
                self.client.api_key = stored.api_key
                self.client.user_id = str(stored.user_id)
                self.client.user_token = stored.session_token
                
                self._load_config()
                self.refresh_history()
                self.refresh_statistics()
                self.show()
            else:
                sys.exit(0)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Base deep dark background
        painter.fillRect(self.rect(), QColor("#080b11"))
        
        # Draw background 3D spheres
        draw_3d_sphere(painter, 100, 80, 180, "#4a0e4e", "#a020f0")
        draw_3d_sphere(painter, self.width() - 350, 150, 220, "#1f4068", "#16a085")
        draw_3d_sphere(painter, 200, self.height() - 280, 150, "#d35400", "#ffaa00")

    def _update_pairs(self, mode: str) -> None:
        pair_key = mode
        try:
            self.pair_combo.currentTextChanged.disconnect(self._reset_result_for_selection)
        except TypeError:
            pass
        self.pair_combo.clear()
        self.pair_combo.addItems(self.config["pairs"].get(pair_key, []))
        self.pair_combo.currentTextChanged.connect(self._reset_result_for_selection)

    def _on_mode_changed(self, mode: str) -> None:
        self._update_pairs(mode)
        self.link_input.setVisible(False)
        self.bridge_card.setVisible(False)
        if mode == "Binance Spot":
            self.provider_hint_label.setText(
                "Binance Spot mode uses exact Binance symbols such as BTC/USDT and ETH/USDT with live 1-second candles."
            )
        elif mode == "Quotex":
            self.provider_hint_label.setText(
                "Quotex display names use Binance live candles only when a supported crypto mapping exists. No bridge URL is used."
            )
        elif mode == "Forex":
            self.provider_hint_label.setText(
                "Forex symbols are not fetched through XM or any bridge. Select a Binance crypto/USDT market for live candles."
            )
        else:
            self.provider_hint_label.setText(
                "Crypto OTC display names are mapped to Binance live 1-second candles. UP/DOWN requires real indicator agreement; otherwise WAIT."
            )
        self._reset_result_for_selection()

    def _reset_result_for_selection(self) -> None:
        selected_pair = self.pair_combo.currentText() or "--"
        selected_duration = self.duration_combo.currentText() if hasattr(self, "duration_combo") else "--"
        self._set_signal_visual_state("WAIT")
        self.result_pair_label.setText(f"Pair: {selected_pair}")
        self.result_confidence_label.setText("Confidence: --")
        self.result_price_label.setText("Price: --")
        self.result_duration_label.setText(f"Trade Time: {selected_duration}")
        self.result_trend_label.setText("Trend: --")
        self.result_status_label.setText("Status: Ready")
        self.result_update_label.setText("Market Update: --")
        self.analysis_text.setPlainText("Ready. Generate Signal will fetch fresh Binance live candles for the selected pair.")

    def _tick_market_refresh(self) -> None:
        if self.mode_combo.currentText() not in {"Crypto", "Binance Spot"}:
            return
        if self.market_worker and self.market_worker.isRunning():
            return
        self.market_worker = MarketRefreshWorker(
            self.client,
            self.mode_combo.currentText(),
            self.pair_combo.currentText(),
            self.duration_combo.currentText(),
            None,
        )
        self.market_worker.completed.connect(self._show_auto_market_refresh)
        self.market_worker.failed.connect(lambda message: logging.warning("Auto market refresh failed: %s", message))
        self.market_worker.start()

    def generate_signal(self) -> None:
        if not self._ensure_license_for_signals():
            return
        if self.trade_active:
            self.statusBar().showMessage(
                f"Current trade is active. Wait {self.trade_remaining_seconds}s before generating a new signal.",
                3000,
            )
            return
        if self.worker and self.worker.isRunning():
            return
        source_url = None
        self._set_signal_buttons_enabled(False)
        self.result_status_label.setText("Status: Analyzing market...")
        self.statusBar().showMessage("Analyzing fresh market data...", 3000)
        self.worker = SignalWorker(
            self.client,
            self.mode_combo.currentText(),
            self.pair_combo.currentText(),
            self.duration_combo.currentText(),
            source_url,
        )
        self.worker.completed.connect(self._show_signal)
        self.worker.failed.connect(self._show_error)
        self.worker.start()

    def refresh_market_data(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        source_url = None
        self._set_signal_buttons_enabled(False)
        self.result_status_label.setText("Status: Refreshing market data...")
        self.statusBar().showMessage("Fetching latest live market data...", 3000)
        self.worker = MarketRefreshWorker(
            self.client,
            self.mode_combo.currentText(),
            self.pair_combo.currentText(),
            self.duration_combo.currentText(),
            source_url,
        )
        self.worker.completed.connect(self._show_market_refresh)
        self.worker.failed.connect(self._show_error)
        self.worker.start()

    def scan_pairs(self) -> None:
        if not self._ensure_license_for_signals():
            return
        if self.worker and self.worker.isRunning():
            return
        pairs = self.config["pairs"].get(self.mode_combo.currentText(), [])
        self.worker = ScanWorker(self.client, self.mode_combo.currentText(), self.duration_combo.currentText(), pairs)
        self.worker.completed.connect(self._show_scan)
        self.worker.failed.connect(self._show_error)
        self.worker.start()

    def _ensure_license_for_signals(self) -> bool:
        status = self.license_manager.validate()
        if status.valid:
            return True
        self.result_status_label.setText("Status: License required")
        self.analysis_text.setPlainText(
            f"{status.message}\n\nAdmin can activate this device from the ADMIN portal."
        )
        self.statusBar().showMessage("License required. Click ADMIN to activate this device.", 7000)
        return False

    def _show_signal(self, data: dict) -> None:
        self.result_pair_label.setText(f'Pair: {data["pair"]}')
        self.result_confidence_label.setText(f'Confidence: {data["confidence"]}%')
        self.result_price_label.setText(f'Price: {data["current_price"]}')
        self.result_duration_label.setText(f'Trade Time: {data["duration"]}')
        self.result_trend_label.setText(f'Trend: {data["market_trend"]}')
        self.result_status_label.setText(f'Status: {data["status"]}')
        source = data.get("data_source", "--")
        self._set_signal_visual_state(data["signal"])
        analysis = list(data["analysis"])
        if data.get("data_warning") and data["data_warning"] not in analysis:
            analysis.append(data["data_warning"])
        last_update = data.get("last_market_update") or "--"
        self.result_update_label.setText(f"Market Update: {last_update}")
        lines = [f"Source: {source}", f"Last market update: {last_update}", ""]
        lines.extend(f"- {item}" for item in analysis)
        self.analysis_text.setPlainText("\n".join(lines))
        if data["signal"] == "WAIT":
            self._set_signal_buttons_enabled(True)
            self.result_duration_label.setText("WAIT. Fresh market movement required.")
        else:
            self._start_trade_timer(data["duration"])
        if data["signal"] != "WAIT" and data["confidence"] >= 75:
            QApplication.beep()
            self.statusBar().showMessage(f'{data["pair"]}: {data["signal"]} at {data["confidence"]}%', 5000)
        self.refresh_history()
        self.refresh_statistics()

    def _show_market_refresh(self, data: dict) -> None:
        self._set_signal_buttons_enabled(True)
        self.result_pair_label.setText(f'Pair: {data["pair"]}')
        self.result_price_label.setText(f'Price: {data["current_price"]}')
        self.result_status_label.setText(f'Status: {data["status"]}')
        last_update = data.get("last_market_update") or "--"
        self.result_update_label.setText(f"Market Update: {last_update}")
        warning = data.get("data_warning")
        lines = [
            f'Source: {data.get("data_source", "--")}',
            f"Last market update: {last_update}",
            "",
            warning or "Fresh market data fetched. Generate Signal will analyze only after a new live tick or candle arrives.",
        ]
        self.analysis_text.setPlainText("\n".join(lines))
        self.statusBar().showMessage(warning or "Market data refreshed.", 5000)

    def _show_auto_market_refresh(self, data: dict) -> None:
        if data.get("status") != "LIVE":
            return
        self.result_pair_label.setText(f'Pair: {data["pair"]}')
        self.result_price_label.setText(f'Price: {data["current_price"]}')
        self.result_status_label.setText("Status: LIVE")
        last_update = data.get("last_market_update") or "--"
        self.result_update_label.setText(f"Market Update: {last_update}")

    def _show_scan(self, rows: list[dict]) -> None:
        self.scan_table.setRowCount(0)
        for row in rows:
            self._append_row(
                self.scan_table,
                [
                    row["pair"],
                    row["current_price"],
                    row["signal"],
                    f'{row["confidence"]}%',
                    row["duration"],
                    row["market_trend"],
                    row["status"],
                ],
            )

    def refresh_history(self) -> None:
        try:
            rows = self.client.history(100)
        except Exception:
            return
        self.history_table.setRowCount(0)
        for row in rows:
            created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            self._append_row(
                self.history_table,
                [
                    row["id"],
                    created.strftime("%Y-%m-%d %H:%M:%S"),
                    row["pair"],
                    row["signal"],
                    f'{row["confidence"]}%',
                    row["duration"],
                    row["market_trend"],
                    row.get("outcome") or "",
                ],
            )

    def refresh_statistics(self) -> None:
        try:
            stats = self.client.statistics()
        except Exception:
            return
        self.stats_label.setText(
            "Statistics: "
            f'Total {stats["total_signals"]} | '
            f'Wins {stats["wins"]} | Losses {stats["losses"]} | '
            f'Tracked Win Rate {stats["tracked_win_rate"]}% | '
            f'Average Confidence {stats["average_confidence"]}%'
        )

    def mark_selected_outcome(self, outcome: str) -> None:
        row = self.history_table.currentRow()
        if row < 0:
            self.statusBar().showMessage("Select a signal history row first.", 4000)
            return
        signal_id_item = self.history_table.item(row, 0)
        if signal_id_item is None:
            return
        try:
            self.client.update_outcome(int(signal_id_item.text()), outcome)
            self.refresh_history()
            self.refresh_statistics()
            self.statusBar().showMessage(f"Marked signal {signal_id_item.text()} as {outcome}.", 4000)
        except Exception as exc:
            self._show_error(str(exc))

    def _append_row(self, table: QTableWidget, values: list[object]) -> None:
        row_index = table.rowCount()
        table.insertRow(row_index)
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if "BUY" in str(value) or "UP" in str(value):
                item.setForeground(QColor("#3ee27a"))
            elif "SELL" in str(value) or "DOWN" in str(value):
                item.setForeground(QColor("#ff5c77"))
            table.setItem(row_index, column, item)

    def _show_error(self, message: str) -> None:
        logging.error(message)
        self._set_signal_buttons_enabled(True)
        self._set_signal_visual_state("WAIT")
        self.result_pair_label.setText(f"Pair: {self.pair_combo.currentText() or '--'}")
        self.result_confidence_label.setText("Confidence: --")
        self.result_price_label.setText("Price: --")
        self.result_trend_label.setText("Trend: --")
        self.result_update_label.setText("Market Update: --")
        self.result_status_label.setText("Status: Check provider")
        self.analysis_text.setPlainText(message)
        self.statusBar().showMessage(message, 8000)

    def _start_trade_timer(self, duration: str) -> None:
        self.trade_remaining_seconds = self._duration_to_seconds(duration)
        if self.trade_remaining_seconds <= 0:
            self._finish_trade_timer()
            return
        self.trade_active = True
        self._set_signal_buttons_enabled(False)
        self._update_trade_timer_text()
        self.trade_timer.start()

    def _tick_trade_timer(self) -> None:
        self.trade_remaining_seconds -= 1
        if self.trade_remaining_seconds <= 0:
            self._finish_trade_timer()
            return
        self._update_trade_timer_text()

    def _finish_trade_timer(self) -> None:
        self.trade_timer.stop()
        self.trade_active = False
        self.trade_remaining_seconds = 0
        self._set_signal_buttons_enabled(True)
        self.result_duration_label.setText("Trade ended. Ready for next signal.")
        self.statusBar().showMessage("Trade time ended. Click Generate Signal for fresh market analysis.", 6000)

    def _update_trade_timer_text(self) -> None:
        self.result_duration_label.setText(f"Trade Active: {self.trade_remaining_seconds}s left")
        self.primary_generate_button.setText(f"Wait {self.trade_remaining_seconds}s")
        self.generate_button.setText(f"Wait {self.trade_remaining_seconds}s")

    def _set_signal_buttons_enabled(self, enabled: bool) -> None:
        self.generate_button.setEnabled(enabled)
        self.primary_generate_button.setEnabled(enabled)
        self.refresh_market_button.setEnabled(enabled)
        self.primary_refresh_button.setEnabled(enabled)
        self.scan_button.setEnabled(enabled)
        if enabled:
            self.generate_button.setText("Generate Signal")
            self.primary_generate_button.setText("Generate New Signal")
            self.refresh_market_button.setText("Refresh Market Data")
            self.primary_refresh_button.setText("Refresh Market Data")

    @staticmethod
    def _duration_to_seconds(duration: str) -> int:
        parts = duration.split()
        if not parts:
            return 0
        try:
            amount = int(parts[0])
        except ValueError:
            return 0
        unit = parts[1].lower() if len(parts) > 1 else "seconds"
        if unit.startswith("minute"):
            return amount * 60
        return amount

    def _set_signal_visual_state(self, signal: str) -> None:
        if "BUY" in signal or "UP" in signal:
            color = "#21f36d"
            label = "UP"
        elif "SELL" in signal or "DOWN" in signal:
            color = "#ff244d"
            label = "DOWN"
        else:
            color = "#8fa0b7"
            label = "WAIT"

        self.result_signal_label.setText(label)
        self.result_signal_label.setStyleSheet(
            f"""
            QLabel#resultSignal {{
                background: transparent;
                border: none;
                color: {color};
                font-size: 52px;
                font-weight: 900;
                padding: 6px;
            }}
            """
        )

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #080b11;
                color: #f5f8ff;
                font-size: 14px;
                font-family: "Segoe UI", Arial;
            }
            QPushButton#adminButton {
                background: rgba(45, 55, 72, 0.7);
                color: #ff6076;
                border: 1px solid rgba(255, 83, 105, 0.5);
                border-radius: 10px;
                padding: 10px 22px;
                font-size: 12px;
                font-weight: 900;
            }
            QPushButton#adminButton:hover {
                background: rgba(255, 83, 105, 0.15);
                border-color: #ff5369;
            }
            QFrame#hero {
                background: transparent;
                border: none;
            }
            QLabel#logoMark {
                color: #ffffff;
                background: qradialgradient(cx:0.35, cy:0.25, radius:0.9, fx:0.35, fy:0.25, stop:0 #1a8cff, stop:1 #8e2de2);
                border-radius: 29px;
                font-size: 26px;
                font-weight: 900;
            }
            QLabel#brand {
                color: #bcc0ff;
                font-size: 32px;
                font-weight: 900;
            }
            QLabel#testPill {
                color: #ffffff;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#stats {
                color: #a0aec0;
                font-size: 13px;
                font-weight: 800;
            }
            QFrame#leftStack {
                background: transparent;
                border: none;
            }
            QFrame#card, QFrame#signalPanel, QPlainTextEdit#analysis {
                background: rgba(22, 28, 45, 0.55);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
            QLabel#cardTitle {
                color: #00f0ff;
                font-size: 17px;
                font-weight: 900;
            }
            QLabel#providerHint {
                background: transparent;
                border: none;
                color: #a0aec0;
                font-size: 12px;
                font-weight: 800;
                line-height: 1.4;
            }
            QLabel#readyLabel {
                color: #e2e8f0;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#summary {
                background: rgba(15, 20, 35, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 9px;
                color: #ffffff;
                padding: 10px 12px;
                font-size: 13px;
                font-weight: 900;
            }
            QLabel#resultSignal {
                background: transparent;
                border: none;
                font-size: 52px;
                font-weight: 900;
                padding: 6px;
            }
            QLineEdit, QComboBox {
                background: rgba(15, 20, 35, 0.85);
                color: #f5f8ff;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 9px;
                padding: 7px 12px;
                min-height: 28px;
                font-size: 15px;
                font-weight: 900;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #2b76f5;
            }
            QComboBox QAbstractItemView {
                background-color: #121824;
                color: #f5f8ff;
                selection-background-color: #2b76f5;
                selection-color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            QLineEdit::placeholder {
                color: #718096;
            }
            QPushButton {
                background: rgba(45, 55, 72, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
                color: #ffffff;
                padding: 10px 14px;
                font-weight: 900;
            }
            QPushButton:hover {
                background: rgba(55, 68, 92, 0.85);
                border-color: rgba(255, 255, 255, 0.2);
            }
            QPushButton#primaryGenerate {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a8cff, stop:1 #8e2de2);
                color: #ffffff;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: 900;
            }
            QPushButton#primaryGenerate:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #339cff, stop:1 #9f4bf6);
            }
            QPushButton#secondaryGenerate {
                background: rgba(45, 55, 72, 0.5);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                font-size: 15px;
                font-weight: 900;
            }
            QPushButton#secondaryGenerate:hover {
                background: rgba(55, 68, 92, 0.65);
            }
            QPlainTextEdit#analysis {
                padding: 14px;
                color: #e2e8f0;
                font-size: 14px;
            }
            QTableWidget {
                background: rgba(18, 24, 38, 0.5);
                alternate-background-color: rgba(25, 32, 50, 0.4);
                gridline-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
            QHeaderView::section {
                background: rgba(24, 32, 51, 0.85);
                color: #a0aec0;
                padding: 8px;
                border: none;
                font-weight: 900;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.3);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """
        )
        self._set_signal_visual_state("WAIT")


def main() -> None:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(
        """
        QDialog, QWidget {
            background: #080b11;
            color: #f5f8ff;
            font-size: 14px;
            font-family: "Segoe UI", Arial;
        }
        QLabel#cardTitle {
            color: #00f0ff;
            font-size: 18px;
            font-weight: 900;
        }
        QLabel#providerHint {
            color: #a0aec0;
            font-size: 12px;
            font-weight: 800;
        }
        QLineEdit, QPlainTextEdit, QSpinBox {
            background: rgba(15, 20, 35, 0.85);
            color: #f5f8ff;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 9px;
            padding: 8px 12px;
            font-weight: 800;
        }
        QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {
            border: 1px solid #2b76f5;
        }
        QPushButton {
            background: rgba(45, 55, 72, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 10px;
            color: #ffffff;
            padding: 10px 14px;
            font-weight: 900;
        }
        QPushButton:hover {
            background: rgba(55, 68, 92, 0.85);
            border-color: rgba(255, 255, 255, 0.2);
        }
        QPushButton#primaryGenerate {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a8cff, stop:1 #8e2de2);
            border: none;
        }
        QPushButton#primaryGenerate:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #339cff, stop:1 #9f4bf6);
        }
        QTableWidget {
            background: rgba(18, 24, 38, 0.5);
            alternate-background-color: rgba(25, 32, 50, 0.4);
            gridline-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
        }
        QHeaderView::section {
            background: rgba(24, 32, 51, 0.85);
            color: #a0aec0;
            padding: 8px;
            border: none;
            font-weight: 900;
        }
        QTabWidget::pane {
            border: 1px solid rgba(255, 255, 255, 0.08);
            background: rgba(18, 24, 38, 0.45);
            border-radius: 12px;
        }
        QTabBar::tab {
            background: transparent;
            color: #718096;
            padding: 8px 16px;
            font-weight: 700;
            border-bottom: 2px solid transparent;
        }
        QTabBar::tab:hover {
            color: #cbd5e0;
        }
        QTabBar::tab:selected {
            color: #2b76f5;
            border-bottom: 2px solid #2b76f5;
        }
        QScrollBar:vertical {
            border: none;
            background: transparent;
            width: 6px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255, 255, 255, 0.15);
            min-height: 20px;
            border-radius: 3px;
        }
        QScrollBar::handle:vertical:hover {
            background: rgba(255, 255, 255, 0.3);
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        """
    )
    license_manager = LicenseManager()
    client = ApiClient()

    # Check if already licensed locally
    status = license_manager.validate()
    if status.valid:
        client.api_key = status.api_key
        client.user_id = status.user_id
        client.user_token = status.session_token
    else:
        # Show auth gate dialog
        gate = LicenseGateWindow(license_manager, client)
        if gate.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)

    window = TradingSignalWindow(license_manager, client)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

