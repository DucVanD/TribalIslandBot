import subprocess
import time
import os
import cv2
import numpy as np
import threading
import math


class ADBController:
    """
    ADBController quản lý giao tiếp ngầm 100% với BlueStacks:
    - Chụp màn hình trực tiếp từ bộ đệm Android (không dính cửa sổ Windows hay GUI)
    - Tự động tap (chạm) các nút Bắt Đầu, Tấn Công, Kỹ Năng, Hồi Máu, Chọn Perk
    - Vuốt Joystick di chuyển không chiếm chuột hay bàn phím máy tính
    """

    def __init__(self, adb_path=r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe", device_id="emulator-5554"):
        self.adb_path = adb_path
        self.device_id = device_id
        
        # Tọa độ chuẩn 100% chuẩn xác trên màn hình 1920x1080
        self.COORD_ATTACK = (1757, 929)     # Nút Lửa to góc phải dưới
        self.COORD_SKILL = (1761, 643)      # Nút Kỹ năng tím phía trên nút lửa
        self.COORD_HEAL = (1445, 956)       # Nút Đùi gà hồi máu
        self.COORD_START = (980, 950)       # Nút Vàng Bắt Đầu / Tiếp Tục ở sảnh chờ
        self.COORD_END_BATTLE = (1442, 1000) # Nút Vàng 'Kết Thúc' sau khi hết trận
        
        # 3 thẻ chọn kỹ năng khi lên cấp (đo chính xác theo viền tròn trắng)
        self.PERK_COORDS = [
            (755, 701),   # Thẻ 1 (Trái)
            (943, 701),   # Thẻ 2 (Giữa)
            (1132, 701)   # Thẻ 3 (Phải)
        ]

        # Tọa độ Cần gạt di chuyển (Dynamic Joystick) - Chuẩn 100% trên độ phân giải 1920x1080
        # Tâm cần gạt khi đứng yên: (285, 842). Bán kính tối đa: 140px.
        self.JOYSTICK_CENTER = (285, 842)
        self.JOYSTICK_OFFSET = 140

    def run_cmd(self, args, timeout=15):
        """Chạy lệnh ADB với thiết bị chỉ định."""
        cmd = [self.adb_path, "-s", self.device_id] + args
        try:
            return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"[ADB] Lệnh bị timeout sau {timeout}s: {' '.join(args)}")
            return None
        except Exception as e:
            print(f"[ADB] Lỗi chạy lệnh: {e}")
            return None

    def ensure_connection(self):
        """Khởi tạo ADB daemon và kiểm tra kết nối."""
        # Bước 1: Khởi động ADB daemon
        try:
            subprocess.run([self.adb_path, "start-server"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        except Exception:
            pass
        
        # Bước 2: Kiểm tra thiết bị
        res = self.run_cmd(["shell", "echo", "ok"])
        if res and res.returncode == 0 and "ok" in res.stdout:
            return True
        return False

    def tap(self, x, y):
        """Chạm cảm ứng vào tọa độ (x, y) ngầm."""
        self.run_cmd(["shell", "input", "tap", str(int(x)), str(int(y))])

    def swipe(self, x1, y1, x2, y2, duration_ms=1000):
        """Vuốt cảm ứng từ (x1, y1) tới (x2, y2) trong duration_ms."""
        self.run_cmd(["shell", "input", "swipe", str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(duration_ms))])

    def capture_screen(self):
        """
        Chụp ảnh trực tiếp từ Android framebuffer.
        Trả về ảnh numpy BGR (1920x1080) sắc nét, không bị dính bất kỳ cửa sổ nào của Windows.
        """
        temp_remote = "/sdcard/s.png"
        temp_local = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "adb_live_frame.png")
        
        # 1. Chụp trong android
        self.run_cmd(["shell", "screencap", "-p", temp_remote])
        # 2. Kéo về máy tính
        self.run_cmd(["pull", temp_remote, temp_local])
        
        if os.path.exists(temp_local):
            frame = cv2.imread(temp_local)
            return frame
        return None

    def attack(self):
        """Bắn đạn thường (chạm nút lửa)."""
        self.tap(*self.COORD_ATTACK)

    def use_skill(self):
        """Bấm chiêu đặc biệt."""
        self.tap(*self.COORD_SKILL)

    def heal(self):
        """Bơm máu đùi gà."""
        self.tap(*self.COORD_HEAL)

    def click_start(self):
        """Bấm nút Bắt Đầu / Tiếp Tục ở sảnh chờ."""
        self.tap(*self.COORD_START)

    def click_end_battle(self):
        """Bấm nút Kết Thúc màu vàng để nhận thưởng và về sảnh."""
        self.tap(*self.COORD_END_BATTLE)

    def select_perk(self, index=1):
        """Chọn perk lên cấp (index: 1, 2, 3)."""
        if 1 <= index <= 3:
            x, y = self.PERK_COORDS[index - 1]
            self.tap(x, y)

    def move_angle(self, angle_deg, distance_ratio=1.0, duration_ms=1000):
        """
        Điều khiển Joystick theo góc 360 độ tự do (Analog Vector):
        - angle_deg: 0=Phải, 90=Lên, 180=Trái, 270=Xuống (hoặc bất kỳ góc chéo nào: 45, 135, 225, 315,...)
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

    def move_direction(self, direction='w', duration_ms=1500):
        """
        Điều khiển Joystick theo phím hướng hoặc tổ hợp chéo:
        'w': Lên, 'd': Phải, 's': Xuống, 'a': Trái
        'wd': Chéo trên phải, 'wa': Chéo trên trái, 'sd': Chéo dưới phải, 'sa': Chéo dưới trái
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

