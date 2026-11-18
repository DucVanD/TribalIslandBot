# -*- coding: utf-8 -*-
"""
tests/test_p7_demonstration_and_memory.py
Kiểm thử toàn diện chuỗi Demonstration Learning (P2-P4) và Procedural Memory (P7):
- P2: DemonstrationRecorder (Session, Frame, HUMAN/BOT provenance)
- P3: BehaviorSegmenter (Phân loại Phase & Phân đoạn)
- P4: ConditionalStrategyReplayer (Preconditions & Abort Monitoring)
- P6: 4-Tier Decision Engine Integration
- P7: Procedural Memory (Pattern persistence)
"""

import os
import sys
import unittest

base_dir = os.path.dirname(os.path.dirname(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.common_types import Entity, WorldState, SteeringCommand, DemonstrationFrame
from core.memory.database import Database
from core.memory.memory_manager import MemoryManager
from core.demonstration.demonstration_recorder import DemonstrationRecorder
from core.demonstration.behavior_segmenter import BehaviorSegmenter
from core.demonstration.conditional_replayer import ConditionalStrategyReplayer
from core.decision.decision_engine import DecisionEngine


class TestDemonstrationAndMemory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_db_path = os.path.join(base_dir, "data", "test_unified_memory.db")
        if os.path.exists(test_db_path):
            try:
                os.remove(test_db_path)
            except Exception:
                pass
        cls.db = Database(db_path=test_db_path)
        cls.memory = MemoryManager(db=cls.db)

    def test_01_demonstration_recorder(self):
        """P2: Kiểm tra ghi nhận phiên thị phạm đồng bộ."""
        recorder = DemonstrationRecorder(db=self.db, save_screenshots=False)
        session_id = recorder.start_session(source_type="HUMAN", target_floor=71)
        self.assertIsNotNone(session_id)
        self.assertEqual(recorder.source_type, "HUMAN")

        world = WorldState(player_pos=(960, 540), player_hp=95.0, nearest_enemy_dist=400.0)
        action = SteeringCommand(action_type="MOVE", angle_degrees=90.0, reason="test_swipe")

        frame = recorder.record_frame(world, action)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.source, "HUMAN")
        self.assertEqual(frame.frame_id, 1)

        recorder.end_session(quality_score=0.98)
        self.assertFalse(recorder.is_recording)

        # Kiểm tra dữ liệu trong SQLite
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT total_frames, source_type, quality_score FROM demonstration_sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            self.assertEqual(row["total_frames"], 1)
            self.assertEqual(row["source_type"], "HUMAN")
            self.assertEqual(row["quality_score"], 0.98)

    def test_02_behavior_segmenter(self):
        """P3: Kiểm tra phân loại phase và phân đoạn hành vi."""
        segmenter = BehaviorSegmenter(db=self.db)

        # 1. State 1: Approach (quái ở rất xa)
        w_approach = WorldState(nearest_enemy=Entity(id=1, category='enemy', center_x=100, center_y=100), nearest_enemy_dist=700.0)
        self.assertEqual(segmenter.classify_phase(w_approach), "APPROACH")

        # 2. State 2: Combat (quái ở cự ly kiting)
        w_combat = WorldState(nearest_enemy=Entity(id=1, category='enemy', center_x=500, center_y=500), nearest_enemy_dist=420.0)
        self.assertEqual(segmenter.classify_phase(w_combat), "COMBAT")

        # 3. State 3: Retreat (quái áp sát)
        w_retreat = WorldState(nearest_enemy=Entity(id=1, category='enemy', center_x=900, center_y=540), nearest_enemy_dist=120.0)
        self.assertEqual(segmenter.classify_phase(w_retreat), "RETREAT")

        # 4. State 4: Stuck
        w_stuck = WorldState(is_stuck=True)
        self.assertEqual(segmenter.classify_phase(w_stuck), "STUCK_RECOVERY")

        # Tạo chuỗi frames mẫu
        frames = [
            DemonstrationFrame(frame_id=1, session_id=1, timestamp=1.0, world_state=w_approach, action=SteeringCommand(angle_degrees=90.0)),
            DemonstrationFrame(frame_id=2, session_id=1, timestamp=2.0, world_state=w_approach, action=SteeringCommand(angle_degrees=90.0)),
            DemonstrationFrame(frame_id=3, session_id=1, timestamp=3.0, world_state=w_combat, action=SteeringCommand(angle_degrees=180.0)),
        ]
        segments = segmenter.segment_frames(frames)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].phase_type, "APPROACH")
        self.assertEqual(segments[1].phase_type, "COMBAT")

    def test_03_conditional_replayer_and_decision(self):
        """P4 & P6: Kiểm tra Replay có điều kiện và tích hợp vào 4-Tier Decision Engine."""
        replayer = ConditionalStrategyReplayer()
        decision = DecisionEngine(hp_critical_percent=35.0, replayer=replayer)

        # Precondition check: Máu thấp -> Từ chối replay
        w_low_hp = WorldState(player_hp=30.0, nearest_enemy_dist=400.0)
        self.assertFalse(replayer.check_preconditions(w_low_hp))

        # Precondition check: Máu tốt -> Chấp nhận replay
        w_safe = WorldState(player_hp=90.0, nearest_enemy_dist=420.0, confidence=0.90)
        self.assertTrue(replayer.check_preconditions(w_safe))

        # Tạo một segment mẫu để phát lại
        from core.common_types import BehaviorSegment
        sample_commands = [
            SteeringCommand(action_type="MOVE", angle_degrees=45.0),
            SteeringCommand(action_type="MOVE", angle_degrees=135.0)
        ]
        seg = BehaviorSegment(
            segment_id=10, session_id=1, phase_type="COMBAT",
            start_frame=1, end_frame=2, start_time=1.0, end_time=2.0,
            command_sequence=sample_commands
        )

        started = replayer.start_replay(seg, w_safe)
        self.assertTrue(started)

        # Lệnh 1 từ Replayer
        cmd1 = decision.decide(w_safe, obstacles=[])
        self.assertEqual(cmd1.action_type, "MOVE")
        self.assertEqual(cmd1.angle_degrees, 45.0)
        self.assertIn("demo_replay", cmd1.reason)

        # Giả lập tình huống khẩn cấp: Quái áp sát < 160px -> Safety Rules phải NGẮT Replay
        w_danger = WorldState(
            player_pos=(960, 540),
            player_hp=90.0,
            nearest_enemy=Entity(id=1, category='enemy', center_x=960, center_y=450),
            nearest_enemy_dist=90.0  # Nguy hiểm!
        )
        cmd_safety = decision.decide(w_danger, obstacles=[])
        # Safety Rules ngắt và giật ngược hướng thoát quái
        self.assertIn("enemy_too_close", cmd_safety.reason)
        self.assertIsNone(replayer.active_segment, "Replayer should be aborted by Safety Rules!")

    def test_04_procedural_memory(self):
        """P7: Kiểm tra lưu trữ và truy xuất Procedural Memory."""
        pattern_name = "kiting_circular_ccw"
        trigger = {"enemy_count": 3, "ideal_distance": 450}
        actions = [{"angle": 90, "hold_ms": 400}, {"angle": 180, "hold_ms": 400}]

        success = self.memory.save_procedural_pattern(pattern_name, trigger, actions)
        self.assertTrue(success)

        retrieved = self.memory.get_procedural_pattern(pattern_name)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["pattern_name"], pattern_name)
        self.assertEqual(retrieved["trigger_conditions"]["ideal_distance"], 450)
        self.assertEqual(len(retrieved["action_sequence"]), 2)


def run_tests():
    print("=" * 60)
    print("TEST P7: UNIFIED DEMONSTRATION & PROCEDURAL MEMORY")
    print("=" * 60)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestDemonstrationAndMemory)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n✅ TEST P7 DEMONSTRATION & PROCEDURAL MEMORY THÀNH CÔNG RỰC RỠ!")
    return result.wasSuccessful()


if __name__ == "__main__":
    run_tests()

