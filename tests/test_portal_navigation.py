import unittest
from unittest.mock import Mock
from unittest.mock import patch

import cv2
import numpy as np

from core.common_types import Entity, PerceptionResult
from core.decision.decision_engine import DecisionEngine
from core.action.action_engine import ActionEngine
from core.hybrid_agent import HybridAgent
from core.engine_vision import VisionEngine
import core.engine_vision as engine_vision_module
from core.perception.perception_engine import PerceptionEngine
from core.world.world_model import WorldModel
from core.common_types import WorldState


class TestPortalNavigation(unittest.TestCase):
    def test_pale_portal_below_hud_is_detected_and_drives_heading(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        gold = cv2.cvtColor(np.uint8([[[25, 200, 255]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
        pale_cyan = cv2.cvtColor(np.uint8([[[88, 50, 255]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
        # Simulate the bright gold rim and pale cyan core in the actual floor 2 capture.
        cv2.ellipse(frame, (280, 315), (52, 68), 0, 0, 360, gold, -1)
        cv2.ellipse(frame, (280, 315), (31, 45), 0, 0, 360, pale_cyan, -1)
        vision = VisionEngine.__new__(VisionEngine)
        vision.templates = {}

        found, point = vision.find_portal(frame)
        self.assertTrue(found)
        self.assertAlmostEqual(point[0], 280, delta=8)
        self.assertAlmostEqual(point[1], 315, delta=8)

        world = WorldModel().update(PerceptionResult(
            timestamp=1.0,
            player=type("Player", (), {"center_x": 979, "center_y": 426})(),
            enemies=[],
            portal=type("Portal", (), {"center_x": point[0], "center_y": point[1]})(),
            overall_confidence=0.9,
        ))
        cmd = DecisionEngine().decide(world, obstacles=[])
        self.assertIn("move_to_portal_targeted", cmd.reason)
        self.assertGreater(cmd.angle_degrees, 135)
        self.assertLess(cmd.angle_degrees, 180)

    def test_portal_detector_prefers_continuous_track_over_larger_new_candidate(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        gold = cv2.cvtColor(np.uint8([[[25, 200, 255]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
        pale_cyan = cv2.cvtColor(np.uint8([[[88, 50, 255]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
        for center, axes in [((450, 320), (48, 65)), ((1000, 320), (56, 72))]:
            cv2.ellipse(frame, center, axes, 0, 0, 360, gold, -1)
            cv2.ellipse(frame, center, (int(axes[0] * .58), int(axes[1] * .62)),
                        0, 0, 360, pale_cyan, -1)
        vision = VisionEngine.__new__(VisionEngine)
        vision.templates = {}

        found, point = vision.find_portal(frame, player_pos=(1000, 550), previous_portal=(450, 320))
        self.assertTrue(found)
        self.assertAlmostEqual(point[0], 450, delta=15)

    def test_portal_heading_smoothing_prevents_single_frame_reversal(self):
        model = WorldModel()
        player = type("Player", (), {"center_x": 960, "center_y": 500})()
        first = model.update(PerceptionResult(
            timestamp=10.0, player=player, portal=Entity(1, "portal", 960, 200), enemies=[]
        ))
        second = model.update(PerceptionResult(
            timestamp=10.8, player=player, portal=Entity(1, "portal", 1260, 500), enemies=[]
        ))
        turn = abs((second.portal_angle - first.portal_angle + 180) % 360 - 180)
        self.assertLessEqual(turn, 23.0)

    def test_empty_room_without_portal_uses_sweep_not_fixed_north(self):
        cmd = DecisionEngine().decide(WorldState(enemies_count=0), obstacles=[])
        self.assertIn("portal_search_sweep", cmd.reason)
        self.assertEqual(cmd.angle_degrees, 90.0)
        self.assertGreaterEqual(cmd.duration_ms, 1200)

    def test_empty_milestone_floor_uses_obstacle_aware_route_search(self):
        world = WorldState(current_floor=15, enemies_count=0)
        cmd = DecisionEngine().decide(world, obstacles=[])
        self.assertIn("route_floor_exploration", cmd.reason)
        self.assertEqual(cmd.angle_degrees, 90.0)
        self.assertNotIn("portal_search_sweep", cmd.reason)

        blocked_north = Entity(id=2, category="obstacle_stump", center_x=960, center_y=350, radius=60)
        detour = DecisionEngine().decide(world, obstacles=[blocked_north])
        self.assertIn("route_floor_exploration", detour.reason)
        self.assertIn(detour.angle_degrees, (45.0, 135.0))

    def test_portal_search_waits_for_combat_clearance(self):
        agent = HybridAgent.__new__(HybridAgent)
        agent._floor_saw_enemy = False
        agent._floor_no_enemy_since = None
        agent._floor_exit_completed_at = 100.0
        agent.current_floor = 1

        empty = WorldState(enemies_count=0)
        self.assertFalse(agent._portal_search_ready(empty, 105.9))
        self.assertTrue(agent._portal_search_ready(empty, 106.0))

        agent._floor_saw_enemy = True
        agent._floor_no_enemy_since = 200.0
        self.assertFalse(agent._portal_search_ready(empty, 202.3))
        self.assertTrue(agent._portal_search_ready(empty, 202.4))
        self.assertFalse(agent._portal_search_ready(WorldState(enemies_count=1), 210.0))

    def test_empty_milestone_floor_search_starts_after_spawn_corridor(self):
        agent = HybridAgent.__new__(HybridAgent)
        agent._floor_saw_enemy = False
        agent._floor_no_enemy_since = None
        agent._floor_exit_completed_at = None
        agent.current_floor = 25
        agent._spawn_exit_steps_remaining = 1
        self.assertFalse(agent._portal_search_ready(WorldState(enemies_count=0), 1.0))
        agent._spawn_exit_steps_remaining = 0
        self.assertTrue(agent._portal_search_ready(WorldState(enemies_count=0), 1.1))

    def test_shard_gain_does_not_mark_room_clear_or_override_visible_enemies(self):
        agent = HybridAgent.__new__(HybridAgent)
        agent._floor_saw_enemy = False
        agent._floor_no_enemy_since = None
        agent._floor_exit_completed_at = 0.0
        agent.current_floor = 11

        agent._update_floor_enemy_evidence(WorldState(enemies_count=1, shard_count=54), 10.0)
        self.assertFalse(agent._portal_search_ready(
            WorldState(enemies_count=1, shard_count=54), 100.0
        ))
        self.assertFalse(agent._portal_search_ready(
            WorldState(enemies_count=0, shard_count=55), 11.0
        ))
        agent._update_floor_enemy_evidence(WorldState(enemies_count=0, shard_count=55), 10.8)
        self.assertFalse(agent._portal_search_ready(
            WorldState(enemies_count=0, shard_count=55), 13.1
        ))
        self.assertTrue(agent._portal_search_ready(
            WorldState(enemies_count=0, shard_count=55), 13.21
        ))

    def test_floor_reset_clears_combat_evidence_and_stale_portal_track(self):
        agent = HybridAgent.__new__(HybridAgent)
        agent.perception = Mock()
        agent.world_model = Mock()
        agent._floor_saw_enemy = True
        agent._floor_no_enemy_since = 12.0
        agent._floor_exit_completed_at = 5.0
        agent._last_combat_verify_log = 15.0

        agent._reset_floor_combat_phase()

        self.assertFalse(agent._floor_saw_enemy)
        self.assertIsNone(agent._floor_no_enemy_since)
        agent.perception.reset_portal_track.assert_called_once_with()
        agent.world_model.reset_portal_track.assert_called_once_with()

    def test_shard_counter_ocr_reads_digits_from_upper_right_hud(self):
        if engine_vision_module.pytesseract is None:
            self.skipTest("pytesseract is not installed")
        vision = VisionEngine.__new__(VisionEngine)
        with patch.object(engine_vision_module.pytesseract, "image_to_string", return_value=" 53\n") as ocr:
            self.assertEqual(vision.detect_shard_count(np.zeros((1080, 1920, 3), dtype=np.uint8)), 53)
            self.assertIn("--psm 7", ocr.call_args.kwargs["config"])
            self.assertIn("tessedit_char_whitelist=0123456789", ocr.call_args.kwargs["config"])
            self.assertEqual(vision.detect_shard_count(
                np.zeros((1080, 1920, 3), dtype=np.uint8), is_lobby=True
            ), 53)
            self.assertIn("--psm 8", ocr.call_args.kwargs["config"])

    def test_portal_track_rejects_a_sudden_opposite_bearing(self):
        perception = object.__new__(PerceptionEngine)
        perception._last_portal = Entity(id=1, category="portal", center_x=1005, center_y=228)
        perception._last_portal_time = 10.0
        self.assertFalse(perception._portal_candidate_jumps(
            Entity(id=2, category="portal", center_x=1035, center_y=240), (962, 389), 10.5
        ))
        self.assertTrue(perception._portal_candidate_jumps(
            Entity(id=3, category="portal", center_x=820, center_y=330), (962, 389), 10.5
        ))

    def test_sustained_move_uses_long_known_swipe(self):
        action = ActionEngine.__new__(ActionEngine)
        action.JOYSTICK_CENTER = (285, 842)
        action.JOYSTICK_OFFSET = 140
        action.swipe = Mock()

        action.move_angle_sustained(90, duration_ms=1400)
        action.swipe.assert_called_once_with(285, 842, 285, 702, duration_ms=1400)


if __name__ == "__main__":
    unittest.main()
