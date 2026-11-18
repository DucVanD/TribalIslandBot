"""Contextual tabular policy learning with bounded, episode-level promotion."""

import json
import math
from collections import defaultdict
from typing import Any, Dict, Optional, Tuple

from core.common_types import SteeringCommand, WorldState
from core.memory.database import Database


class AdaptiveLearner:
    """Learns action preferences from demonstrations and bot transitions.

    This intentionally remains a small contextual model: discrete state buckets,
    auditable action scores, SQLite persistence, and no unconstrained exploration.
    A candidate is only used in alternating evaluation episodes and never bypasses
    the decision engine's safety rules.
    """

    MIN_CANDIDATE_EXAMPLES = 20
    MIN_SHADOW_OBSERVATIONS = 100
    MIN_SHADOW_RUNS = 2
    MIN_EVAL_RUNS_PER_POLICY = 5
    MAX_EVAL_RUNS_PER_POLICY = 10
    PROMOTION_MARGIN = 0.05

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.current_policy_id: Optional[int] = None
        self.current_policy_role = "BASELINE"
        self._active_episode_policy_id: Optional[int] = None
        self._active_evaluation_id: Optional[int] = None
        self._policy_cache: Dict[int, Optional[Dict[str, Any]]] = {}

    @staticmethod
    def context_key(world: WorldState) -> str:
        if world.is_stuck:
            phase = "STUCK"
        elif world.player_hp < 35 or world.nearest_enemy_dist < 160:
            phase = "RETREAT"
        elif world.enemies_count and world.nearest_enemy_dist <= 550:
            phase = "COMBAT"
        else:
            phase = "APPROACH"
        hp_bucket = "LOW" if world.player_hp < 35 else "MID" if world.player_hp < 70 else "HIGH"
        if world.nearest_enemy_dist < 160:
            distance_bucket = "CLOSE"
        elif world.nearest_enemy_dist <= 350:
            distance_bucket = "NEAR"
        elif world.nearest_enemy_dist <= 650:
            distance_bucket = "RANGE"
        else:
            distance_bucket = "FAR"
        enemy_bucket = "0" if world.enemies_count == 0 else "1" if world.enemies_count == 1 else "2+"
        return f"{phase}|{hp_bucket}|{distance_bucket}|{enemy_bucket}"

    @staticmethod
    def action_key(action: SteeringCommand) -> str:
        if action.action_type == "MOVE":
            angle = int(round(action.angle_degrees / 45.0) * 45) % 360
            return f"MOVE:{angle}"
        return action.action_type.upper()

    @classmethod
    def state_payload(cls, world: WorldState) -> Dict[str, Any]:
        return {
            "context": cls.context_key(world),
            "player_hp": round(world.player_hp, 2),
            "enemy_distance": round(world.nearest_enemy_dist, 2),
            "enemies_count": int(world.enemies_count),
            "is_stuck": bool(world.is_stuck),
            "floor": int(world.current_floor),
            "game_state": world.game_state,
            "confidence": round(world.confidence, 3),
        }

    @classmethod
    def action_payload(cls, action: SteeringCommand) -> Dict[str, Any]:
        return {
            "key": cls.action_key(action),
            "type": action.action_type,
            "angle": float(action.angle_degrees),
            "duration_ms": int(action.duration_ms),
            "distance_ratio": float(action.distance_ratio),
            "reason": action.reason,
        }

    def record_example(self, world: WorldState, action: SteeringCommand, source: str,
                       session_id: Optional[int] = None, run_id: Optional[int] = None,
                       reward: Optional[float] = None, eligible: bool = True) -> None:
        if not eligible or world.confidence < 0.50:
            return
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO learning_examples
                   (run_id, session_id, source, context_key, action_key, state_json,
                    action_json, reward, eligible)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (run_id, session_id, source.upper(), self.context_key(world), self.action_key(action),
                 json.dumps(self.state_payload(world)), json.dumps(self.action_payload(action)), reward),
            )

    def record_transition(self, run_id: int, previous_world: WorldState,
                          action: SteeringCommand, world: WorldState) -> float:
        """Store an observed one-step outcome for the preceding bot action."""
        reward = 0.0
        reward += max(-5.0, min(5.0, (world.player_hp - previous_world.player_hp) * 0.5))
        reward += max(-3.0, min(3.0, (previous_world.enemies_count - world.enemies_count) * 1.5))
        if previous_world.is_stuck and not world.is_stuck:
            reward += 2.0
        if world.is_stuck and not previous_world.is_stuck:
            reward -= 2.0
        if world.current_floor > previous_world.current_floor:
            reward += 4.0 * (world.current_floor - previous_world.current_floor)
        reward = max(-10.0, min(10.0, reward))
        self.record_example(world=previous_world, action=action, source="BOT", run_id=run_id,
                            reward=reward, eligible=(previous_world.game_state == "FIGHTING"))
        return reward

    def _get_policy(self, policy_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if policy_id is None:
            return None
        if policy_id in self._policy_cache:
            return self._policy_cache[policy_id]
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT policy_json FROM learning_policies WHERE policy_id = ?", (policy_id,)).fetchone()
        if row is None:
            self._policy_cache[policy_id] = None
            return None
        try:
            policy = json.loads(row["policy_json"])
        except (TypeError, json.JSONDecodeError):
            policy = None
        self._policy_cache[policy_id] = policy
        return policy

    def score_action(self, world: WorldState, angle_degrees: float) -> Optional[float]:
        """Return a learned 0..100 preference, or None when no evidence exists."""
        if world.confidence < 0.50:
            return None
        context = self.context_key(world)
        action = SteeringCommand(action_type="MOVE", angle_degrees=angle_degrees)
        action_key = self.action_key(action)
        policy_id = self.current_policy_id
        if policy_id is None:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT policy_id FROM learning_policies WHERE status='ACTIVE' LIMIT 1").fetchone()
            policy_id = row["policy_id"] if row else None
        policy = self._get_policy(policy_id)
        context_scores = (policy or {}).get("scores", {}).get(context)
        if context_scores is not None and action_key not in context_scores:
            return 35.0
        score = context_scores.get(action_key) if context_scores is not None else None
        return float(score) if score is not None else None

    @staticmethod
    def _fit_scores(rows) -> Dict[str, Dict[str, float]]:
        """Fit auditable context/action preferences from examples."""
        by_context = defaultdict(lambda: defaultdict(lambda: {"human": 0, "bot_n": 0, "bot_reward": 0.0}))
        for row in rows:
            stats = by_context[row["context_key"]][row["action_key"]]
            if row["source"] == "HUMAN":
                stats["human"] += 1
            elif row["reward"] is not None:
                stats["bot_n"] += 1
                stats["bot_reward"] += float(row["reward"])

        scores: Dict[str, Dict[str, float]] = {}
        for context, actions in by_context.items():
            human_total = sum(a["human"] for a in actions.values())
            for action_key, stat in actions.items():
                human_rate = stat["human"] / max(1, human_total)
                demo_signal = (human_rate - (1.0 / 8.0)) * 35.0
                bot_n = stat["bot_n"]
                mean_reward = stat["bot_reward"] / bot_n if bot_n else 0.0
                outcome_signal = max(-20.0, min(20.0, mean_reward * 2.0))
                evidence = min(1.0, (stat["human"] + bot_n) / 8.0)
                value = max(0.0, min(100.0, 50.0 + evidence * (demo_signal + outcome_signal)))
                scores.setdefault(context, {})[action_key] = round(value, 3)
        return scores

    def refresh_candidate(self) -> Dict[str, Any]:
        """Refit an unevaluated candidate from all current examples.

        Once a candidate enters evaluation its weights are frozen so the canary
        compares one stable policy throughout.
        """
        with self.db.get_connection() as conn:
            candidate = conn.execute("SELECT policy_id, policy_json FROM learning_policies WHERE status='CANDIDATE' LIMIT 1").fetchone()
            if candidate is None:
                policy_id = self.build_candidate()
                return {"decision": "CREATED" if policy_id else "NO_CANDIDATE", "policy_id": policy_id}
            evaluated = conn.execute("SELECT 1 FROM policy_evaluations WHERE policy_id=? LIMIT 1", (candidate["policy_id"],)).fetchone()
            if evaluated:
                return {"decision": "FROZEN_FOR_EVALUATION", "policy_id": int(candidate["policy_id"])}
            rows = conn.execute("""SELECT context_key, action_key, source, reward FROM learning_examples
                WHERE eligible=1 AND source IN ('HUMAN','BOT')""").fetchall()
            old = json.loads(candidate["policy_json"] or "{}")
            old_count = int(old.get("sample_count", 0))
            if len(rows) < old_count + self.MIN_CANDIDATE_EXAMPLES:
                return {"decision": "NOT_ENOUGH_NEW_DATA", "policy_id": int(candidate["policy_id"]),
                        "new_examples": max(0, len(rows) - old_count)}
            payload = json.dumps({"scores": self._fit_scores(rows), "sample_count": len(rows),
                                  "method": "contextual_counts_v1"})
            conn.execute("UPDATE learning_policies SET policy_json=? WHERE policy_id=?",
                         (payload, candidate["policy_id"]))
            self._policy_cache.pop(int(candidate["policy_id"]), None)
            return {"decision": "REFRESHED", "policy_id": int(candidate["policy_id"]),
                    "new_examples": len(rows) - old_count, "sample_count": len(rows)}

    def build_candidate(self) -> Optional[int]:
        """Fit a new tabular candidate from eligible human and bot examples."""
        with self.db.get_connection() as conn:
            existing = conn.execute("SELECT policy_id FROM learning_policies WHERE status='CANDIDATE' LIMIT 1").fetchone()
            if existing:
                # Keep an untested candidate current as fresh partial-run outcomes arrive.
                self.refresh_candidate()
                return int(existing["policy_id"])
            rows = conn.execute("""SELECT context_key, action_key, source, reward FROM learning_examples
                                  WHERE eligible=1 AND source IN ('HUMAN','BOT')""").fetchall()
            active = conn.execute("SELECT policy_id, version, policy_json FROM learning_policies WHERE status='ACTIVE' LIMIT 1").fetchone()
            if len(rows) < self.MIN_CANDIDATE_EXAMPLES or active is None:
                return None
            trained_counts = []
            for policy_row in conn.execute("SELECT policy_json FROM learning_policies").fetchall():
                try:
                    trained_counts.append(int(json.loads(policy_row["policy_json"] or "{}").get("sample_count", 0)))
                except (TypeError, json.JSONDecodeError):
                    trained_counts.append(0)
            latest_trained_count = max(trained_counts, default=0)
            if len(rows) < latest_trained_count + self.MIN_CANDIDATE_EXAMPLES:
                return None
            promotion = conn.execute("SELECT promoted_at, promoted_after_eval_id FROM learning_policies WHERE policy_id=?", (active["policy_id"],)).fetchone()
            promoted_at = promotion["promoted_at"]
            if promoted_at:
                monitor_count = conn.execute("""SELECT COUNT(*) FROM policy_evaluations
                    WHERE policy_id=? AND role='CANDIDATE' AND evaluation_id > ?""",
                    (active["policy_id"], int(promotion["promoted_after_eval_id"] or 0))).fetchone()[0]
                if int(monitor_count) < self.MIN_EVAL_RUNS_PER_POLICY:
                    return None

            version = int(conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM learning_policies").fetchone()[0])
            payload = json.dumps({"scores": self._fit_scores(rows), "sample_count": len(rows), "method": "contextual_counts_v1"})
            cursor = conn.execute(
                "INSERT INTO learning_policies (version, status, policy_json) VALUES (?, 'CANDIDATE', ?)",
                (version, payload),
            )
            return int(cursor.lastrowid)

    def begin_episode(self, run_id: int) -> Tuple[Optional[int], str]:
        """Select candidate/baseline for a bounded alternating canary episode."""
        refresh = self.refresh_candidate()
        if refresh.get("decision") == "REFRESHED":
            print(f"[Learning] Candidate policy refreshed from {refresh['new_examples']} new examples "
                  f"(total {refresh['sample_count']}).")
        with self.db.get_connection() as conn:
            active = conn.execute("SELECT policy_id FROM learning_policies WHERE status='ACTIVE' LIMIT 1").fetchone()
            candidate = conn.execute("SELECT policy_id FROM learning_policies WHERE status='CANDIDATE' LIMIT 1").fetchone()
            if not active:
                return None, "BASELINE"
            policy_id = int(active["policy_id"])
            evaluation_id = int(candidate["policy_id"]) if candidate else policy_id
            role = "BASELINE"
            if candidate:
                candidate_id = int(candidate["policy_id"])
                shadow_count = int(conn.execute("SELECT COUNT(*) FROM policy_shadow_observations WHERE policy_id=?", (candidate_id,)).fetchone()[0])
                shadow_runs = int(conn.execute("SELECT COUNT(DISTINCT run_id) FROM policy_shadow_observations WHERE policy_id=?", (candidate_id,)).fetchone()[0])
                if shadow_count < self.MIN_SHADOW_OBSERVATIONS or shadow_runs < self.MIN_SHADOW_RUNS:
                    role = "SHADOW"
                else:
                    counts = conn.execute("SELECT role, COUNT(*) n FROM policy_evaluations WHERE policy_id=? GROUP BY role", (candidate_id,)).fetchall()
                    totals = {r["role"]: int(r["n"]) for r in counts}
                    if totals.get("CANDIDATE", 0) < self.MAX_EVAL_RUNS_PER_POLICY and totals.get("CANDIDATE", 0) <= totals.get("BASELINE", 0):
                        policy_id, role = candidate_id, "CANDIDATE"
            else:
                active_state = conn.execute("SELECT promoted_at FROM learning_policies WHERE policy_id=?", (policy_id,)).fetchone()
                if active_state and active_state["promoted_at"]:
                    role = "CANDIDATE"  # post-promotion rollback monitoring window
            self.current_policy_id = policy_id
            self.current_policy_role = role
            self._active_episode_policy_id = policy_id
            self._active_evaluation_id = evaluation_id
            return policy_id, role

    def record_shadow_recommendation(self, run_id: int, world: WorldState) -> Optional[SteeringCommand]:
        """Record what a candidate would do while the active policy controls the bot."""
        if self.current_policy_role != "SHADOW" or self._active_evaluation_id is None or world.confidence < 0.50:
            return None
        policy = self._get_policy(self._active_evaluation_id) or {}
        context = self.context_key(world)
        scores = policy.get("scores", {}).get(context)
        if not scores:
            return None
        candidates = []
        for angle in range(0, 360, 45):
            key = f"MOVE:{angle}"
            score = float(scores.get(key, 35.0))
            candidates.append((score, angle, key))
        score, angle, action_key = max(candidates)
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO policy_shadow_observations
                (policy_id, run_id, context_key, action_key, score) VALUES (?, ?, ?, ?, ?)""",
                (self._active_evaluation_id, run_id, context, action_key, score))
        return SteeringCommand(action_type="MOVE", angle_degrees=float(angle), reason="candidate_shadow")

    @staticmethod
    def episode_score(reached_floor: int, target_floor: int, result: str) -> float:
        progress = max(0.0, min(1.0, float(reached_floor) / max(1, target_floor)))
        won = 1.0 if result.upper() in {"SUCCESS", "WON", "COMPLETE"} else 0.0
        return round(70.0 * progress + 30.0 * won, 3)

    def finish_episode(self, run_id: int, reached_floor: int, target_floor: int,
                       result: str, safety_events: int = 0) -> Dict[str, Any]:
        """Persist episode score, decide promotion/rejection, and train next candidate."""
        policy_id = self._active_evaluation_id or self._active_episode_policy_id
        role = self.current_policy_role
        if policy_id is None:
            self.build_candidate()
            return {"role": role, "decision": "NO_POLICY"}
        if role == "SHADOW":
            self.current_policy_id = None
            self._active_episode_policy_id = None
            self._active_evaluation_id = None
            self.build_candidate()
            return {"role": role, "decision": "SHADOW_COMPLETE"}
        score = self.episode_score(reached_floor, target_floor, result)
        with self.db.get_connection() as conn:
            conn.execute("""INSERT OR IGNORE INTO policy_evaluations
                         (policy_id, run_id, role, score, safety_events) VALUES (?, ?, ?, ?, ?)""",
                         (policy_id, run_id, role, score, max(0, int(safety_events))))
            candidate = conn.execute("SELECT policy_id FROM learning_policies WHERE status='CANDIDATE' LIMIT 1").fetchone()
            decision = "RECORDED"
            if candidate:
                candidate_id = int(candidate["policy_id"])
                rows = conn.execute("SELECT role, score, safety_events FROM policy_evaluations WHERE policy_id=?", (candidate_id,)).fetchall()
                groups = {"BASELINE": [], "CANDIDATE": []}
                for row in rows:
                    groups[row["role"]].append((float(row["score"]), int(row["safety_events"])))
                baseline, trial = groups["BASELINE"], groups["CANDIDATE"]
                if len(baseline) >= self.MIN_EVAL_RUNS_PER_POLICY and len(trial) >= self.MIN_EVAL_RUNS_PER_POLICY:
                    base_mean = sum(x[0] for x in baseline) / len(baseline)
                    trial_mean = sum(x[0] for x in trial) / len(trial)
                    base_safety = sum(x[1] for x in baseline) / len(baseline)
                    trial_safety = sum(x[1] for x in trial) / len(trial)
                    improved = trial_mean >= base_mean + max(1.0, abs(base_mean) * self.PROMOTION_MARGIN)
                    safe = trial_safety <= base_safety + 0.25
                    if improved and safe:
                        conn.execute("UPDATE learning_policies SET status='ARCHIVED' WHERE status='ACTIVE'")
                        last_eval_id = conn.execute("SELECT COALESCE(MAX(evaluation_id), 0) FROM policy_evaluations WHERE policy_id=?", (candidate_id,)).fetchone()[0]
                        conn.execute("""UPDATE learning_policies SET status='ACTIVE', promoted_at=CURRENT_TIMESTAMP,
                            promoted_after_eval_id=? WHERE policy_id=?""", (last_eval_id, candidate_id))
                        decision = "PROMOTED"
                    elif len(baseline) >= self.MAX_EVAL_RUNS_PER_POLICY and len(trial) >= self.MAX_EVAL_RUNS_PER_POLICY:
                        conn.execute("UPDATE learning_policies SET status='REJECTED' WHERE policy_id=?", (candidate_id,))
                        decision = "REJECTED"
            else:
                active = conn.execute("SELECT policy_id, promoted_at FROM learning_policies WHERE status='ACTIVE' LIMIT 1").fetchone()
                if active and active["promoted_at"]:
                    current_id = int(active["policy_id"])
                    baseline_rows = conn.execute("""SELECT score, safety_events FROM policy_evaluations
                        WHERE policy_id=? AND role='BASELINE'""", (current_id,)).fetchall()
                    promoted_after_id = conn.execute("SELECT promoted_after_eval_id FROM learning_policies WHERE policy_id=?", (current_id,)).fetchone()["promoted_after_eval_id"]
                    monitor_rows = conn.execute("""SELECT score, safety_events FROM policy_evaluations
                        WHERE policy_id=? AND role='CANDIDATE' AND evaluation_id > ?""",
                        (current_id, int(promoted_after_id or 0))).fetchall()
                    if len(baseline_rows) >= self.MIN_EVAL_RUNS_PER_POLICY and len(monitor_rows) >= self.MIN_EVAL_RUNS_PER_POLICY:
                        base_mean = sum(float(r["score"]) for r in baseline_rows) / len(baseline_rows)
                        current_mean = sum(float(r["score"]) for r in monitor_rows) / len(monitor_rows)
                        base_safety = sum(int(r["safety_events"]) for r in baseline_rows) / len(baseline_rows)
                        current_safety = sum(int(r["safety_events"]) for r in monitor_rows) / len(monitor_rows)
                        regressed = current_mean < base_mean - max(1.0, abs(base_mean) * self.PROMOTION_MARGIN)
                        unsafe = current_safety > base_safety + 0.25
                        if regressed or unsafe:
                            previous = conn.execute("""SELECT policy_id FROM learning_policies
                                WHERE status='ARCHIVED' AND version < (SELECT version FROM learning_policies WHERE policy_id=?)
                                ORDER BY version DESC LIMIT 1""", (current_id,)).fetchone()
                            if previous:
                                conn.execute("UPDATE learning_policies SET status='ARCHIVED' WHERE policy_id=?", (current_id,))
                                conn.execute("UPDATE learning_policies SET status='ACTIVE' WHERE policy_id=?", (previous["policy_id"],))
                                decision = "ROLLED_BACK"
            conn.commit()
        self.current_policy_id = None
        self._active_episode_policy_id = None
        self._active_evaluation_id = None
        self.build_candidate()
        return {"role": role, "decision": decision, "score": score}
