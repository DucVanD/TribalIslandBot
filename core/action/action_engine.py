# -*- coding: utf-8 -*-
"""
core/action/action_engine.py
ActionEngine thống nhất điều khiển 100% ngầm qua ADB.
Thay thế hoàn toàn pydirectinput, không chiếm chuột/bàn phím máy tính.
Hỗ trợ fast capture qua exec-out và thực thi SteeringCommand.
"""

import subprocess
import time
import os
import cv2
import numpy as np
import threading
import math
from typing import Optional, Tuple

from core.common_types import SteeringCommand


class ActionEngine:
    """
    ActionEngine quản lý toàn bộ thao tác vật lý gửi vào BlueStacks qua ADB:
    - Fast screen capture (exec-out raw buffer < 100ms)
    - Joystick di chuyển 360 độ (Analog Angle Swipe)
    - Tấn công, dùng kỹ năng, đùi gà hồi máu, chọn perk, nút sảnh
    - Thực thi SteeringCommand từ Decision Engine
    """

    def __init__(self, adb_path: str = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
                 device_id: str = "emulator-5554"):
        self.adb_path = adb_path
        self.device_id = device_id
        self._lock = threading.Lock()

        # Tọa độ chuẩn 100% chuẩn xác trên màn hình 1920x1080
        self.COORD_ATTACK = (1757, 929)        # Nút Lửa to góc phải dưới
        self.COORD_SKILL = (1761, 643)         # Nút Kỹ năng tím phía trên nút lửa
        self.COORD_HEAL = (1445, 956)          # Nút Đùi gà hồi máu
        self.COORD_START = (980, 950)          # Nút Vàng Bắt Đầu / Tiếp Tục ở sảnh chờ
        self.COORD_END_BATTLE = (1390, 1000)   # Nút Vàng 'Kết Thúc' sau khi hết trận (tâm chuẩn)

        # 3 thẻ chọn kỹ năng khi lên cấp
        self.PERK_COORDS = [
            (755, 701),   # Thẻ 1 (Trái)
            (943, 701),   # Thẻ 2 (Giữa)
            (1132, 701)   # Thẻ 3 (Phải)
        ]

        # Tọa độ Cần gạt di chuyển (Dynamic Joystick) - Chuẩn 100% trên độ phân giải 1920x1080
        # Tâm cần gạt khi đứng yên: (285, 842). Bán kính tối đa: 140px.
        self.JOYSTICK_CENTER = (285, 842)
        self.JOYSTICK_OFFSET = 140

        # Trạng thái kết nối
        self.is_connected = False

    def run_cmd(self, args, timeout: int = 15, binary_stdout: bool = False):
        """Chạy lệnh ADB với thiết bị chỉ định."""
        cmd = [self.adb_path, "-s", self.device_id] + args
        try:
            return subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=not binary_stdout,
                timeout=timeout
            )
        except subprocess.TimeoutExpired:
            print(f"[ActionEngine] Lệnh bị timeout sau {timeout}s: {' '.join(str(a) for a in args)}")
            return None
        except Exception as e:
            print(f"[ActionEngine] Lỗi chạy lệnh ADB: {e}")
            return None

    def ensure_connection(self) -> bool:
        """Khởi tạo ADB daemon và kiểm tra kết nối thiết bị."""
        try:
            subprocess.run([self.adb_path, "start-server"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        except Exception:
            pass

        res = self.run_cmd(["shell", "echo", "ok"], timeout=5)
        if res and res.returncode == 0 and "ok" in res.stdout:
            self.is_connected = True
            return True

        # Thử connect port mặc định 127.0.0.1:5555 nếu chưa nhận
        try:
            subprocess.run([self.adb_path, "connect", "127.0.0.1:5555"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            res2 = self.run_cmd(["shell", "echo", "ok"], timeout=5)
            if res2 and res2.returncode == 0 and "ok" in res2.stdout:
                self.is_connected = True
                return True
        except Exception:
            pass

        self.is_connected = False
        return False

    def fast_capture_screen(self) -> Optional[np.ndarray]:
        """
        Chụp ảnh màn hình tốc độ cao qua adb exec-out screencap -p.
        Không ghi file vào sdcard, nhận raw PNG bytes trực tiếp qua stdout.
        Độ trễ: < 100ms.
        """
        with self._lock:
            try:
                # exec-out truyền raw binary stream không bị ngắt CRLF
                res = subprocess.run(
                    [self.adb_path, "-s", self.device_id, "exec-out", "screencap", "-p"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=5
                )
                if res and res.returncode == 0 and len(res.stdout) > 1000:
                    raw_bytes = res.stdout
                    # Fix Windows CRLF (\r\n -> \n) nếu ADB cũ tự chèn \r
                    if raw_bytes.startswith(b'\x89PNG\r\r\n'):
                        raw_bytes = raw_bytes.replace(b'\r\r\n', b'\n')
                    elif b'\r\n' in raw_bytes[:16]:
                        raw_bytes = raw_bytes.replace(b'\r\n', b'\n')
                    
                    frame = cv2.imdecode(np.frombuffer(raw_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None and frame.shape[0] > 0:
                        return frame
            except Exception as e:
                # Fallback to file pull
                pass

            # Fallback nếu exec-out lỗi
            return self._capture_screen_fallback()

    def _capture_screen_fallback(self) -> Optional[np.ndarray]:
        """Phương pháp dự phòng: Chụp vào /sdcard/ rồi pull về máy tính."""
        temp_remote = "/sdcard/s.png"
        temp_local = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "adb_live_frame.png")
        self.run_cmd(["shell", "screencap", "-p", temp_remote], timeout=5)
        self.run_cmd(["pull", temp_remote, temp_local], timeout=5)
        if os.path.exists(temp_local):
            return cv2.imread(temp_local)
        return None

    def tap(self, x: int, y: int):
        """Chạm cảm ứng vào tọa độ (x, y) ngầm."""
        self.run_cmd(["shell", "input", "tap", str(int(x)), str(int(y))])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 800):
        """Vuốt cảm ứng từ (x1, y1) tới (x2, y2) trong duration_ms."""
        self.run_cmd(["shell", "input", "swipe", str(int(x1)), str(int(y1)),
                      str(int(x2)), str(int(y2)), str(int(duration_ms))])

    def attack(self):
        """Bắn đạn thường (chạm nút lửa)."""
        self.tap(*self.COORD_ATTACK)

    def use_skill(self):
        """Bấm chiêu đặc biệt màu tím."""
        self.tap(*self.COORD_SKILL)

    def heal(self):
        """Bơm máu đùi gà."""
        self.tap(*self.COORD_HEAL)

    def click_start(self):
        """Bấm nút Bắt Đầu / Tiếp Tục ở sảnh chờ."""
        self.tap(*self.COORD_START)

    def click_end_battle(self, coords: Optional[Tuple[int, int]] = None):
        """Tap once; the caller confirms the screen transition before retrying."""
        target = coords or self.COORD_END_BATTLE
        self.tap(*target)

    def select_perk(self, index: int = 1):
        """Chọn perk lên cấp (index: 1, 2, 3)."""
        if 1 <= index <= 3:
            x, y = self.PERK_COORDS[index - 1]
            self.tap(x, y)

    def move_angle(self, angle_deg: float, distance_ratio: float = 1.0, duration_ms: int = 800):
        """
        Điều khiển Joystick theo góc 360 độ tự do (Analog Vector):
        - angle_deg: 0=Phải, 90=Lên, 180=Trái, 270=Xuống (hệ tọa độ toán học tiêu chuẩn)
        - distance_ratio: Độ lệch cần gạt (0.2 -> 1.0)
        - duration_ms: Thời gian giữ cần gạt di chuyển (milliseconds)
        """
        rad = math.radians(angle_deg)
        cx, cy = self.JOYSTICK_CENTER
        max_offset = self.JOYSTICK_OFFSET * min(1.0, max(0.2, distance_ratio))

        # Hệ tọa độ màn hình Android: Y hướng xuống dưới nên -sin(rad)
        tx = int(cx + max_offset * math.cos(rad))
        ty = int(cy - max_offset * math.sin(rad))
        self.swipe(cx, cy, tx, ty, duration_ms=duration_ms)

    def move_angle_sustained(self, angle_deg: float, distance_ratio: float = 1.0,
                             duration_ms: int = 1400):
        """Use a long, known-working ADB swipe for one uninterrupted heading."""
        self.move_angle(
            angle_deg,
            distance_ratio,
            duration_ms=max(1000, int(duration_ms)),
        )

    def move_direction(self, direction: str = 'w', duration_ms: int = 800):
        """
        Điều khiển Joystick theo phím hướng hoặc tổ hợp chéo:
        'w': Lên (90°), 'd': Phải (0°), 's': Xuống (270°), 'a': Trái (180°)
        """
        angle_map = {
            'w': 90.0,
            'd': 0.0,
            's': 270.0,
            'a': 180.0,
            'wd': 45.0,
            'dw': 45.0,
            'wa': 135.0,
            'aw': 135.0,
            'sd': 315.0,
            'ds': 315.0,
            'sa': 225.0,
            'as': 225.0
        }
        angle = angle_map.get(direction.lower(), 90.0)
        self.move_angle(angle, distance_ratio=1.0, duration_ms=duration_ms)

    def stop_all(self):
        """Nhả cần gạt và dừng mọi thao tác (chạm nhẹ tâm joystick)."""
        cx, cy = self.JOYSTICK_CENTER
        self.tap(cx, cy)

    def execute_command(self, cmd: SteeringCommand):
        """Thực thi một SteeringCommand từ Decision Engine."""
        if cmd.action_type == "MOVE":
            self.move_angle(cmd.angle_degrees, cmd.distance_ratio, cmd.duration_ms)
        elif cmd.action_type == "ATTACK":
            self.attack()
        elif cmd.action_type == "SKILL":
            self.use_skill()
        elif cmd.action_type == "HEAL":
            self.heal()
        elif cmd.action_type == "SELECT_PERK":
            self.select_perk(cmd.perk_index)
        elif cmd.action_type == "HOLD":
            self.stop_all()

