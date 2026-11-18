import os
import tempfile
import unittest

from core.common_types import SteeringCommand, WorldState
from core.demonstration.offline_synchronizer import OfflineDemonstrationSynchronizer
from core.decision.decision_engine import DecisionEngine
from core.learning.adaptive_learner import AdaptiveLearner
from core.memory.database import Database
from core.navigation.vector_steering import VectorSteering


class TestAdaptiveLearning(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.temp_dir.name, "learning.db"))
        self.learner = AdaptiveLearner(self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _complete_shadow_warmup(self, world):
        for run_id in (900, 901):
            policy_id, role = self.learner.begin_episode(run_id)
            self.assertEqual(role, "SHADOW")
            self.assertEqual(policy_id, 1)  # active policy still controls actions
            for _ in range(50):
                self.assertIsNotNone(self.learner.record_shadow_recommendation(run_id, world))
            self.assertEqual(self.learner.finish_episode(run_id, 20, 71, "FAILED")["decision"], "SHADOW_COMPLETE")

    def test_sync_key_state_and_duration(self):
        sync = OfflineDemonstrationSynchronizer(self.db)
        events = [
            {"rel_t": 0.2, "event": "DOWN", "key": "w"},
            {"rel_t": 0.3, "event": "DOWN", "key": "d"},
            {"rel_t": 0.7, "event": "UP", "key": "w"},
            {"rel_t": 0.9, "event": "UP", "key": "d"},
        ]
        self.assertEqual(sync.get_active_keys_at_time(0.5, events), ["d", "w"])
        self.assertEqual(sync.get_active_keys_at_time(0.8, events), ["d"])
        command = sync.keys_to_steering_command(["w", "d"], duration_ms=375)
        self.assertEqual(command.action_type, "MOVE")
        self.assertEqual(command.angle_degrees, 45.0)
        self.assertEqual(command.duration_ms, 375)
        self.assertEqual(sync._video_epoch(r"D:\clips\2026-11-17 14-57-02.mp4"),
                         sync._video_epoch("2026-11-17 14-57-02.mp4"))

    def test_candidate_uses_demo_and_bot_outcomes_and_promotes_after_canary(self):
        world = WorldState(player_hp=80, nearest_enemy_dist=420, enemies_count=1)
        for _ in range(12):
            self.learner.record_example(world, SteeringCommand(action_type="MOVE", angle_degrees=90), "HUMAN")
        for _ in range(8):
            self.learner.record_example(world, SteeringCommand(action_type="MOVE", angle_degrees=0), "HUMAN")
        candidate_id = self.learner.build_candidate()
        self.assertIsNotNone(candidate_id)
        self.assertIsNotNone(self.learner._get_policy(candidate_id))
        self._complete_shadow_warmup(world)

        run_id = 1
        promotion = None
        for _ in range(5):
            _, role = self.learner.begin_episode(run_id)
            self.assertEqual(role, "CANDIDATE")
            self.learner.finish_episode(run_id, 60, 71, "SUCCESS", safety_events=0)
            run_id += 1
            _, role = self.learner.begin_episode(run_id)
            self.assertEqual(role, "BASELINE")
            promotion = self.learner.finish_episode(run_id, 30, 71, "FAILED", safety_events=0)
            run_id += 1
        self.assertEqual(promotion["decision"], "PROMOTED")
        with self.db.get_connection() as conn:
            active = conn.execute("SELECT version FROM learning_policies WHERE status='ACTIVE'").fetchone()
        self.assertEqual(active["version"], 2)

    def test_low_confidence_and_safety_reject_policy_scores(self):
        low_confidence = WorldState(confidence=0.2)
        self.learner.record_example(low_confidence, SteeringCommand(), "HUMAN")
        with self.db.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM learning_examples").fetchone()[0]
        self.assertEqual(count, 0)

        # Persisted score lookup is a preference only; hard safety remains in DecisionEngine.
        world = WorldState(player_hp=80, nearest_enemy_dist=420, enemies_count=1)
        for _ in range(20):
            self.learner.record_example(world, SteeringCommand(angle_degrees=90), "HUMAN")
        self.assertIsNotNone(self.learner.build_candidate())
        self._complete_shadow_warmup(world)
        policy_id, _ = self.learner.begin_episode(100)
        self.assertIsNotNone(self.learner.score_action(world, 90))
        self.assertIsNotNone(policy_id)

        steering = VectorSteering(w_s=0, w_d=0, w_l=0, w_m=0, w_demo=1)
        steering.adaptive_learner = self.learner
        steering.find_best_angle(world, [])
        self.assertEqual(steering.last_chosen_angle, 90.0)

        decision = DecisionEngine(hp_critical_percent=35)
        decision.steering.adaptive_learner = self.learner
        urgent = WorldState(player_hp=20, nearest_enemy_dist=50, enemies_count=1)
        self.assertEqual(decision.decide(urgent, []).action_type, "HEAL")

    def test_partial_run_examples_refresh_candidate_but_evaluated_candidate_is_frozen(self):
        world = WorldState(player_hp=80, nearest_enemy_dist=420, enemies_count=1)
        action = SteeringCommand(angle_degrees=90)
        for _ in range(20):
            self.learner.record_example(world, action, "HUMAN")
        candidate_id = self.learner.build_candidate()
        before = self.learner._get_policy(candidate_id)
        self.assertEqual(before["sample_count"], 20)

        # Simulate transitions accumulated during a run that the user stopped.
        for _ in range(20):
            self.learner.record_example(world, SteeringCommand(angle_degrees=0), "BOT", reward=-2.0)
        refreshed = self.learner.refresh_candidate()
        self.assertEqual(refreshed["decision"], "REFRESHED")
        self.assertEqual(refreshed["sample_count"], 40)
        after = self.learner._get_policy(candidate_id)
        self.assertEqual(after["sample_count"], 40)
        self.assertNotEqual(before["scores"], after["scores"])

        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO policy_evaluations (policy_id, run_id, role, score, safety_events) VALUES (?, ?, 'CANDIDATE', 10, 0)",
                         (candidate_id, 999))
        for _ in range(20):
            self.learner.record_example(world, SteeringCommand(angle_degrees=180), "BOT", reward=5.0)
        frozen = self.learner.refresh_candidate()
        self.assertEqual(frozen["decision"], "FROZEN_FOR_EVALUATION")
        self.assertEqual(self.learner._get_policy(candidate_id)["sample_count"], 40)

    def test_post_promotion_regression_rolls_back(self):
        world = WorldState(player_hp=80, nearest_enemy_dist=420, enemies_count=1)
        for _ in range(20):
            self.learner.record_example(world, SteeringCommand(angle_degrees=90), "HUMAN")
        self.learner.build_candidate()
        self._complete_shadow_warmup(world)
        run_id = 200
        for _ in range(5):
            self.learner.begin_episode(run_id)
            self.learner.finish_episode(run_id, 60, 71, "SUCCESS", safety_events=0)
            run_id += 1
            self.learner.begin_episode(run_id)
            outcome = self.learner.finish_episode(run_id, 30, 71, "FAILED", safety_events=0)
            run_id += 1
        self.assertEqual(outcome["decision"], "PROMOTED")

        for _ in range(5):
            _, role = self.learner.begin_episode(run_id)
            self.assertEqual(role, "CANDIDATE")
            outcome = self.learner.finish_episode(run_id, 10, 71, "FAILED", safety_events=2)
            run_id += 1
        self.assertEqual(outcome["decision"], "ROLLED_BACK")
        with self.db.get_connection() as conn:
            active = conn.execute("SELECT version FROM learning_policies WHERE status='ACTIVE'").fetchone()
        self.assertEqual(active["version"], 1)


if __name__ == "__main__":
    unittest.main()
