# -*- coding: utf-8 -*-
"""
tests/test_p8_hybrid_passive_recording.py
Kiểm thử Phương án 3: Hybrid Passive Recording:
- PassiveInputLogger: Định dạng sự kiện và chuyển tiếp không chặn phím
- OfflineDemonstrationSynchronizer: Đồng bộ log phím với mốc thời gian video
- Chuyển đổi tổ hợp phím thành SteeringCommand chuẩn xác (W-A-S-D, J, L, Space, 1-2-3)
"""

import os
import sys
import unittest

base_dir = os.path.dirname(os.path.dirname(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.demonstration.passive_input_logger import PassiveInputLogger, KEY_MAP
from core.demonstration.offline_synchronizer import OfflineDemonstrationSynchronizer


class TestHybridPassiveRecording(unittest.TestCase):
    def setUp(self):
        self.sync = OfflineDemonstrationSynchronizer()

    def test_key_mapping_coverage(self):
        """Kiểm tra bảng mã phím đầy đủ các phím điều khiển Tribal Island."""
        self.assertEqual(KEY_MAP[0x57], "w")
        self.assertEqual(KEY_MAP[0x41], "a")
        self.assertEqual(KEY_MAP[0x53], "s")
        self.assertEqual(KEY_MAP[0x44], "d")
        self.assertEqual(KEY_MAP[0x4A], "j")
        self.assertEqual(KEY_MAP[0x4C], "l")
        self.assertEqual(KEY_MAP[0x20], "space")
        self.assertEqual(KEY_MAP[0x31], "1")

    def test_keys_to_steering_command_movement(self):
        """Kiểm tra chuyển đổi phím di chuyển sang góc độ toán học."""
        # W (Lên = 90 độ)
        cmd_w = self.sync.keys_to_steering_command(["w"])
        self.assertEqual(cmd_w.action_type, "MOVE")
        self.assertEqual(cmd_w.angle_degrees, 90.0)

        # D (Phải = 0 độ)
        cmd_d = self.sync.keys_to_steering_command(["d"])
        self.assertEqual(cmd_d.action_type, "MOVE")
        self.assertEqual(cmd_d.angle_degrees, 0.0)

        # W + D (Chéo lên phải = 45 độ)
        cmd_wd = self.sync.keys_to_steering_command(["w", "d"])
        self.assertEqual(cmd_wd.action_type, "MOVE")
        self.assertEqual(cmd_wd.angle_degrees, 45.0)

        # S + A (Chéo xuống trái = 225 độ)
        cmd_sa = self.sync.keys_to_steering_command(["s", "a"])
        self.assertEqual(cmd_sa.action_type, "MOVE")
        self.assertEqual(cmd_sa.angle_degrees, 225.0)

    def test_keys_to_steering_command_actions(self):
        """Kiểm tra chuyển đổi phím hành động chiến đấu."""
        # J (Bắn thường)
        cmd_j = self.sync.keys_to_steering_command(["j"])
        self.assertEqual(cmd_j.action_type, "ATTACK")

        # L (Hồi máu)
        cmd_l = self.sync.keys_to_steering_command(["l"])
        self.assertEqual(cmd_l.action_type, "HEAL")

        # Space (Kỹ năng)
        cmd_space = self.sync.keys_to_steering_command(["space"])
        self.assertEqual(cmd_space.action_type, "SKILL")

        # 1 (Chọn perk 1)
        cmd_perk = self.sync.keys_to_steering_command(["1"])
        self.assertEqual(cmd_perk.action_type, "SELECT_PERK")
        self.assertEqual(cmd_perk.perk_index, 1)

    def test_get_active_keys_at_time(self):
        """Kiểm tra xác định trạng thái phím đang giữ tại mốc thời gian."""
        events = [
            {"rel_t": 1.0, "event": "DOWN", "key": "w"},
            {"rel_t": 1.2, "event": "DOWN", "key": "d"},
            {"rel_t": 2.0, "event": "UP", "key": "w"},
            {"rel_t": 2.5, "event": "UP", "key": "d"},
        ]

        # Tại t = 0.5s: Chưa có phím nào
        self.assertEqual(self.sync.get_active_keys_at_time(0.5, events), [])

        # Tại t = 1.5s: Đang giữ W và D
        keys_15 = sorted(self.sync.get_active_keys_at_time(1.5, events))
        self.assertEqual(keys_15, ["d", "w"])

        # Tại t = 2.2s: Đã nhả W, chỉ còn giữ D
        keys_22 = self.sync.get_active_keys_at_time(2.2, events)
        self.assertEqual(keys_22, ["d"])

        # Tại t = 3.0s: Đã nhả hết
        self.assertEqual(self.sync.get_active_keys_at_time(3.0, events), [])


def run_tests():
    print("=" * 60)
    print("TEST P8: HYBRID PASSIVE RECORDING & INPUT SYNCHRONIZER")
    print("=" * 60)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestHybridPassiveRecording)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n✅ TEST P8 HYBRID PASSIVE RECORDING THÀNH CÔNG RỰC RỠ!")
    return result.wasSuccessful()


if __name__ == "__main__":
    run_tests()

