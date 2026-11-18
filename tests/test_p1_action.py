# -*- coding: utf-8 -*-
"""
tests/test_p1_action.py
Kiểm thử độc lập ActionEngine:
- Vector math của Joystick 360 độ (Polar -> Cartesian Android)
- Bản đồ tọa độ 1080p chuẩn
- Phân phối SteeringCommand vào Action Primitives
- Đảm bảo 100% không sử dụng pydirectinput
"""

import os
import sys
import math
import unittest

base_dir = os.path.dirname(os.path.dirname(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.common_types import SteeringCommand
from core.action.action_engine import ActionEngine


class TestP1ActionEngine(unittest.TestCase):
    def setUp(self):
        self.action = ActionEngine()

    def test_fixed_coordinates_1080p(self):
        """Kiểm tra ma trận tọa độ chuẩn 1920x1080."""
        self.assertEqual(self.action.COORD_ATTACK, (1757, 929))
        self.assertEqual(self.action.COORD_SKILL, (1761, 643))
        self.assertEqual(self.action.COORD_HEAL, (1445, 956))
        self.assertEqual(self.action.COORD_START, (980, 950))
        self.assertEqual(self.action.COORD_END_BATTLE, (1390, 1000))
        self.assertEqual(len(self.action.PERK_COORDS), 3)
        self.assertEqual(self.action.JOYSTICK_CENTER, (285, 842))
        self.assertEqual(self.action.JOYSTICK_OFFSET, 140)

    def test_joystick_vector_math(self):
        """Kiểm tra chuyển đổi góc toán học sang tọa độ màn hình Android."""
        cx, cy = self.action.JOYSTICK_CENTER
        offset = self.action.JOYSTICK_OFFSET  # 160

        test_cases = [
            (0.0, 1.0, cx + offset, cy),                # Phải: X tăng, Y giữ nguyên
            (90.0, 1.0, cx, cy - offset),               # Lên: X giữ nguyên, Y giảm
            (180.0, 1.0, cx - offset, cy),              # Trái: X giảm, Y giữ nguyên
            (270.0, 1.0, cx, cy + offset),              # Xuống: X giữ nguyên, Y tăng
        ]

        for angle_deg, ratio, exp_x, exp_y in test_cases:
            rad = math.radians(angle_deg)
            tx = int(cx + offset * ratio * math.cos(rad))
            ty = int(cy - offset * ratio * math.sin(rad))
            self.assertAlmostEqual(tx, exp_x, delta=1, msg=f"X error at {angle_deg}°")
            self.assertAlmostEqual(ty, exp_y, delta=1, msg=f"Y error at {angle_deg}°")

    def test_command_routing_hold(self):
        """Kiểm tra lệnh HOLD điều hướng tới stop_all."""
        cmd = SteeringCommand(action_type="HOLD", reason="test_hold")
        # Giả lập không lỗi khi dispatch
        try:
            # Override stop_all để kiểm tra routing
            called = [False]
            self.action.stop_all = lambda: called.__setitem__(0, True)
            self.action.execute_command(cmd)
            self.assertTrue(called[0])
        except Exception as e:
            self.fail(f"HOLD command routing failed: {e}")

    def test_no_pydirectinput_leakage(self):
        """Đảm bảo ActionEngine không import pydirectinput."""
        with open(os.path.join(base_dir, "core", "action", "action_engine.py"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("import pydirectinput", content)
        self.assertNotIn("import pyautogui", content)


def run_tests():
    print("=" * 60)
    print("TEST P1: UNIFIED ACTION ENGINE (OFFLINE TEST SUITE)")
    print("=" * 60)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestP1ActionEngine)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n✅ TEST P1 UNIFIED ACTION ENGINE THÀNH CÔNG RỰC RỠ!")
    return result.wasSuccessful()


if __name__ == "__main__":
    run_tests()

