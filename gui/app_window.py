import sys
import os

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QSpinBox, QSlider, QCheckBox, QTextEdit,
        QGroupBox, QGridLayout
    )
    from PySide6.QtCore import Qt, QTimer, Signal, QObject
    from PySide6.QtGui import QFont
    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False


class LogBridge(QObject):
    log_signal = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, run_manager=None):
        super().__init__()
        self.run_manager = run_manager
        self.setWindowTitle("Tribal Island Bot - Điều Khiển Tự Động")
        self.resize(650, 700)

        self.bridge = LogBridge()
        self.bridge.log_signal.connect(self._append_log)

        if self.run_manager:
            self.run_manager.log_callback = self.log

        self._init_ui()

        # Timer cập nhật thông tin định kỳ lên GUI
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_status)
        self.timer.start(500)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 1. Header Banner
        header = QLabel("TRIBAL ISLAND AUTO BOT")
        header.setAlignment(Qt.AlignCenter)
        header.setFont(QFont("Arial", 16, QFont.Bold))
        header.setStyleSheet("color: #2b5797; margin: 10px 0;")
        main_layout.addWidget(header)

        # 2. Cấu hình lượt chạy (Settings Box)
        config_group = QGroupBox("Cấu Hình Mục Tiêu")
        config_layout = QGridLayout(config_group)

        config_layout.addWidget(QLabel("Tầng mục tiêu kết thúc (Tự sát nhận rương):"), 0, 0)
        self.spin_target_floor = QSpinBox()
        self.spin_target_floor.setRange(1, 150)
        self.spin_target_floor.setValue(71)
        config_layout.addWidget(self.spin_target_floor, 0, 1)

        config_layout.addWidget(QLabel("Bơm máu khi HP dưới (%):"), 1, 0)
        self.spin_hp_threshold = QSpinBox()
        self.spin_hp_threshold.setRange(10, 90)
        self.spin_hp_threshold.setValue(30)
        config_layout.addWidget(self.spin_hp_threshold, 1, 1)

        self.chk_auto_repeat = QCheckBox("Tự động lặp lại lượt mới sau khi kết thúc")
        self.chk_auto_repeat.setChecked(True)
        config_layout.addWidget(self.chk_auto_repeat, 2, 0, 1, 2)

        main_layout.addWidget(config_group)

        # 3. Trạng thái hiện tại (Status Box)
        status_group = QGroupBox("Trạng Thái Thời Gian Thực")
        status_layout = QGridLayout(status_group)

        self.lbl_status = QLabel("Trạng thái: ĐANG CHỜ")
        self.lbl_status.setFont(QFont("Arial", 11, QFont.Bold))
        status_layout.addWidget(self.lbl_status, 0, 0)

        self.lbl_floor = QLabel("Tầng hiện tại: -")
        self.lbl_floor.setFont(QFont("Arial", 11))
        status_layout.addWidget(self.lbl_floor, 0, 1)

        self.lbl_runs = QLabel("Số lượt đã hoàn thành: 0")
        self.lbl_runs.setFont(QFont("Arial", 11))
        status_layout.addWidget(self.lbl_runs, 1, 0)

        main_layout.addWidget(status_group)

        # 4. Bảng phím tắt BlueStacks (Key mapping reminder)
        key_group = QGroupBox("Bản Đồ Phím Đã Thiết Lập")
        key_layout = QVBoxLayout(key_group)
        keys_info = QLabel("• Di chuyển: W, A, S, D  |  • Đánh thường: J  |  • Kỹ năng: SPACE\n• Bơm máu đùi gà: L  |  • Chọn kỹ năng lên cấp: 1, 2, 3")
        keys_info.setStyleSheet("color: #555; font-style: italic;")
        key_layout.addWidget(keys_info)
        main_layout.addWidget(key_group)

        # 5. Nút điều khiển (Start / Pause / Stop)
        btn_layout = QHBoxLayout()

        self.btn_start = QPushButton("BẮT ĐẦU (START)")
        self.btn_start.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px; font-size: 13px;")
        self.btn_start.clicked.connect(self._on_start)
        btn_layout.addWidget(self.btn_start)

        self.btn_pause = QPushButton("TẠM DỪNG (PAUSE)")
        self.btn_pause.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; padding: 10px; font-size: 13px;")
        self.btn_pause.clicked.connect(self._on_pause)
        btn_layout.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("DỪNG HẲN (STOP)")
        self.btn_stop.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 10px; font-size: 13px;")
        self.btn_stop.clicked.connect(self._on_stop)
        btn_layout.addWidget(self.btn_stop)

        main_layout.addLayout(btn_layout)

        # 6. Nhật ký hoạt động (Log Box)
        main_layout.addWidget(QLabel("Nhật Ký Hoạt Động (Logs):"))
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background-color: #1e1e1e; color: #00ff66; font-family: Consolas, monospace; font-size: 11px;")
        main_layout.addWidget(self.txt_log)

    def log(self, text):
        self.bridge.log_signal.emit(text)

    def _append_log(self, text):
        self.txt_log.append(text)
        self.txt_log.verticalScrollBar().setValue(self.txt_log.verticalScrollBar().maximum())

    def _on_start(self):
        if self.run_manager:
            self.run_manager.target_floor = self.spin_target_floor.value()
            self.run_manager.hp_heal_threshold = self.spin_hp_threshold.value()
            self.run_manager.auto_repeat = self.chk_auto_repeat.isChecked()
            self.run_manager.start()
        self.lbl_status.setText("Trạng thái: ĐANG CHẠY")
        self.log("[GIAO DIỆN] Đã bấm nút BẮT ĐẦU!")

    def _on_pause(self):
        if self.run_manager:
            if self.run_manager.combat.is_paused:
                self.run_manager.resume()
                self.btn_pause.setText("TẠM DỪNG (PAUSE)")
                self.lbl_status.setText("Trạng thái: ĐANG CHẠY")
            else:
                self.run_manager.pause()
                self.btn_pause.setText("TIẾP TỤC (RESUME)")
                self.lbl_status.setText("Trạng thái: TẠM DỪNG")

    def _on_stop(self):
        if self.run_manager:
            self.run_manager.stop()
        self.lbl_status.setText("Trạng thái: ĐÃ DỪNG")
        self.log("[GIAO DIỆN] Đã bấm nút DỪNG HẲN!")

    def _update_status(self):
        if self.run_manager:
            if getattr(self.run_manager, "use_hybrid", False) and hasattr(self.run_manager, "hybrid"):
                floor = self.run_manager.hybrid.current_floor
            else:
                floor = self.run_manager.current_floor
            self.lbl_floor.setText(f"Tầng hiện tại: {floor}")
            self.lbl_runs.setText(f"Số lượt đã hoàn thành: {self.run_manager.total_runs_completed}")
            state = self.run_manager.state
            self.lbl_status.setText(f"Trạng thái: {state}")


def launch_gui(run_manager=None):
    if not PYSIDE_AVAILABLE:
        print("[LỖI] PySide6 chưa được cài đặt. Vui lòng chạy: pip install pyside6")
        return
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(run_manager)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()

