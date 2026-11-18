# -*- coding: utf-8 -*-
"""
core/demonstration/passive_input_logger.py
Phase P2: Passive Input Logger (Hybrid Passive Recording)
Ghi nhận thụ động 100% thao tác bàn phím của người chơi trong lúc quay video:
- Thuần quan sát thụ động (Zero game intervention, zero input injection)
- Không chặn phím, không làm trễ phím (CallNextHookEx được gọi tức thì)
- Bắt chính xác thời điểm nhấn (KEYDOWN), giữ phím và thả phím (KEYUP)
- Ghi log ra định dạng JSON Lines (.jsonl) kèm epoch timestamp độ chính xác cao
- Tiêu tốn CPU cực thấp (< 0.1%), hoàn toàn không gây tụt FPS game
"""

import os
import sys
import time
import json
import threading
import ctypes
from ctypes import wintypes
from typing import Optional, Callable

# Windows API Constants
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

# 64-bit Windows Hook Types
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

# Thiết lập chữ ký hàm 64-bit an toàn cho User32
user32 = ctypes.windll.user32
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p

user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_longlong

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT

# Bản đồ phím Tribal Island
KEY_MAP = {
    0x57: "w", 0x41: "a", 0x53: "s", 0x44: "d",      # Di chuyển W-A-S-D
    0x4A: "j",                                       # Tấn công thường
    0x4C: "l",                                       # Bơm đùi gà hồi máu
    0x20: "space",                                   # Kỹ năng đặc biệt
    0x31: "1", 0x32: "2", 0x33: "3",                # Chọn Perk thẻ 1, 2, 3
    0x1B: "esc", 0x0D: "enter"
}


class PassiveInputLogger:
    """
    PassiveInputLogger:
    Lắng nghe sự kiện bàn phím qua Low-Level Windows Hook (kèm dự phòng Polling nhẹ).
    Hoạt động độc lập, tách rời hoàn toàn khỏi game và vòng lặp xử lý hình ảnh.
    """

    def __init__(self, output_path: Optional[str] = None, on_event_callback: Optional[Callable] = None):
        if output_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            log_dir = os.path.join(base_dir, "data", "demonstrations", "logs")
            os.makedirs(log_dir, exist_ok=True)
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            self.output_path = os.path.join(log_dir, f"input_log_{timestamp_str}.jsonl")
        else:
            self.output_path = output_path
            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)

        self.on_event_callback = on_event_callback
        self.hook_id = None
        self.hook_proc = None
        self.is_running = False
        self.file_handle = None
        self.event_count = 0
        self.start_epoch = 0.0
        self._mode = "HOOK"  # 'HOOK' hoặc 'ASYNC'
        self._poll_thread = None

    def _hook_callback(self, nCode, wParam, lParam):
        """Callback được Windows gọi mỗi khi có sự kiện phím."""
        if nCode >= 0:
            kb_struct = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk_code = kb_struct.vkCode
            event_time = time.time()

            event_type = None
            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                event_type = "DOWN"
            elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                event_type = "UP"

            if event_type:
                key_name = KEY_MAP.get(vk_code, f"VK_{vk_code:#04x}")
                record = {
                    "t": round(event_time, 4),
                    "rel_t": round(event_time - self.start_epoch, 4) if self.start_epoch else 0.0,
                    "event": event_type,
                    "key": key_name,
                    "vk": vk_code
                }

                if self.file_handle:
                    self.file_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    self.file_handle.flush()

                self.event_count += 1
                if self.on_event_callback:
                    self.on_event_callback(record)

        return user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)

    def _poll_loop(self):
        """Dự phòng: Lắng nghe trạng thái phím qua GetAsyncKeyState (ngủ 10ms, CPU < 0.1%)."""
        tracked_vks = list(KEY_MAP.keys())
        prev_states = {vk: False for vk in tracked_vks}

        while self.is_running:
            now = time.time()
            for vk in tracked_vks:
                # Bit cao nhất = 1 nghĩa là phím đang được nhấn
                is_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                was_down = prev_states[vk]

                if is_down and not was_down:
                    record = {
                        "t": round(now, 4),
                        "rel_t": round(now - self.start_epoch, 4),
                        "event": "DOWN",
                        "key": KEY_MAP[vk],
                        "vk": vk
                    }
                    if self.file_handle:
                        self.file_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                        self.file_handle.flush()
                    self.event_count += 1
                    prev_states[vk] = True

                elif not is_down and was_down:
                    record = {
                        "t": round(now, 4),
                        "rel_t": round(now - self.start_epoch, 4),
                        "event": "UP",
                        "key": KEY_MAP[vk],
                        "vk": vk
                    }
                    if self.file_handle:
                        self.file_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                        self.file_handle.flush()
                    self.event_count += 1
                    prev_states[vk] = False

            time.sleep(0.01)

    def start(self):
        """Bắt đầu lắng nghe sự kiện phím."""
        if self.is_running:
            return

        self.start_epoch = time.time()
        self.event_count = 0
        self.file_handle = open(self.output_path, "w", encoding="utf-8")

        # Ghi header mốc thời gian bắt đầu
        header = {
            "session_start_epoch": self.start_epoch,
            "session_start_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.start_epoch)),
            "platform": "windows_passive_input_logger"
        }
        self.file_handle.write(json.dumps(header, ensure_ascii=False) + "\n")
        self.file_handle.flush()

        # Thử đăng ký Low-Level Hook 64-bit chuẩn
        self.hook_proc = HOOKPROC(self._hook_callback)
        self.hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self.hook_proc,
            None,
            0
        )

        self.is_running = True

        if self.hook_id:
            self._mode = "HOOK"
            print(f"[PassiveInputLogger] 🟢 ĐÃ KHỞI ĐỘNG (Chế độ: Low-Level Hook)!")
        else:
            # Fallback sang GetAsyncKeyState polling nếu hệ thống Windows hạn chế hook
            self._mode = "ASYNC"
            self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._poll_thread.start()
            print(f"[PassiveInputLogger] 🟢 ĐÃ KHỞI ĐỘNG (Chế độ: Async Polling 10ms - CPU < 0.1%)!")

        print(f"[PassiveInputLogger] 📁 File log: {self.output_path}")
        print(f"[PassiveInputLogger] ⏱️ Mốc thời gian T0: {self.start_epoch:.4f}")

    def run_message_loop(self):
        """Chạy vòng lặp thông điệp Windows."""
        msg = wintypes.MSG()
        while self.is_running:
            if self._mode == "HOOK":
                res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if res == 0 or res == -1:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.1)

    def stop(self):
        """Dừng lắng nghe và dọn dẹp tài nguyên."""
        if not self.is_running:
            return

        self.is_running = False
        if self.hook_id:
            user32.UnhookWindowsHookEx(self.hook_id)
            self.hook_id = None

        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None

        print(f"\n[PassiveInputLogger] 🛑 ĐÃ DỪNG! Tổng số sự kiện phím đã ghi: {self.event_count}")


def main():
    print("=" * 65)
    print("      TRIBAL ISLAND BOT – PASSIVE INPUT LOGGER")
    print("    Phương án 3: Ghi nhận phím thụ động (Song song cùng OBS)")
    print("=" * 65)
    print("👉 Hãy mở OBS lên quay màn hình, sau đó chơi game bình thường.")
    print("👉 Nhấn Ctrl + C tại cửa sổ này khi kết thúc ván để lưu file log.")
    print("-" * 65)

    logger = PassiveInputLogger()
    try:
        logger.start()
        logger.run_message_loop()
    except KeyboardInterrupt:
        print("\n[PassiveInputLogger] Nhận tín hiệu dừng từ người dùng...")
    finally:
        logger.stop()


if __name__ == "__main__":
    main()
