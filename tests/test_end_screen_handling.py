import unittest

import cv2
import numpy as np

from core.engine_vision import VisionEngine
from core.perception.perception_engine import PerceptionEngine


class _VisionStub:
    def get_hp_percentage(self, _frame):
        return 100.0

    def is_level_up_screen(self, _frame):
        return False

    def find_lobby_start_button(self, _frame):
        return False, None

    def is_end_battle_screen(self, _frame):
        return False

    def detect_floor_number(self, _frame):
        return 61

    def detect_shard_count(self, _frame, is_lobby=False):
        return None

    def find_portal(self, _frame, player_pos=None, previous_portal=None):
        return False, None


class TestEndScreenHandling(unittest.TestCase):
    def setUp(self):
        self.vision = VisionEngine.__new__(VisionEngine)
        self.vision.templates = {}
        self.vision.ref_width = 1920
        self.vision.ref_height = 1080

    def test_end_button_selects_lower_right_target(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        yellow = (0, 255, 255)
        # A decoy yellow control is outside the end-button location.
        cv2.rectangle(frame, (900, 900), (1100, 980), yellow, -1)
        cv2.rectangle(frame, (1370, 920), (1620, 1030), yellow, -1)

        found, point = self.vision.find_end_battle_button(frame)
        self.assertTrue(found)
        self.assertGreaterEqual(point[0], 1370)
        self.assertGreaterEqual(point[1], 920)

    def test_end_banner_confirms_end_screen(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        original = self.vision.match_template

        def match_template(_roi, name, threshold=0.8):
            if name == "sample_end_battle":
                return True, 0.95, (0, 0)
            return original(_roi, name, threshold)

        self.vision.match_template = match_template
        self.assertTrue(self.vision.is_end_battle_screen(frame))

    def test_unrelated_yellow_control_is_not_an_end_screen(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.rectangle(frame, (900, 900), (1100, 980), (0, 255, 255), -1)
        found, _ = self.vision.find_end_battle_button(frame)
        self.assertFalse(found)
        self.assertFalse(self.vision.is_end_battle_screen(frame))

    def test_floor_ocr_uses_existing_detector_method(self):
        perception = PerceptionEngine.__new__(PerceptionEngine)
        perception.vision = _VisionStub()
        perception.player_detector = type("Player", (), {"detect": lambda _self, _frame: None})()
        perception.enemy_detector = type("Enemies", (), {"detect": lambda _self, _frame, player_pos=None: []})()
        perception.hazard_detector = type("Hazards", (), {"detect": lambda _self, _frame: []})()
        perception.frame_counter = 0
        perception._last_portal = None
        perception._last_portal_time = 0.0

        result = perception.analyze(np.zeros((20, 20, 3), dtype=np.uint8), check_ocr_floor=True)
        self.assertEqual(result.current_floor, 61)


if __name__ == "__main__":
    unittest.main()
