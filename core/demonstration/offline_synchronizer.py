# -*- coding: utf-8 -*-
"""Synchronize gameplay video and passive keyboard input for local learning."""

import argparse
import cv2
import datetime
import json
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from core.common_types import DemonstrationFrame, SteeringCommand
from core.demonstration.behavior_segmenter import BehaviorSegmenter
from core.learning.adaptive_learner import AdaptiveLearner
from core.memory.database import Database
from core.perception.perception_engine import PerceptionEngine
from core.world.world_model import WorldModel


class OfflineDemonstrationSynchronizer:
    """Fuse sampled visual state with the actual held-key state at each timestamp."""

    GAME_KEYS = {"w", "a", "s", "d", "j", "l", "space", "1", "2", "3"}

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        # Avoid loading vision templates for callers that only use key helpers.
        self.perception = None
        self.world_model = None
        self.segmenter = BehaviorSegmenter(db=self.db)
        self.learner = AdaptiveLearner(self.db)
        self.last_report: Dict[str, Any] = {}

    def load_input_log(self, log_path: str) -> Tuple[Optional[float], List[Dict[str, Any]]]:
        if not os.path.exists(log_path):
            return None, []
        start_epoch = None
        events = []
        with open(log_path, "r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    item = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if "session_start_epoch" in item:
                    start_epoch = float(item["session_start_epoch"])
                elif "rel_t" in item:
                    try:
                        item["rel_t"] = float(item["rel_t"])
                        events.append(item)
                    except (ValueError, TypeError):
                        continue
        events.sort(key=lambda event: event["rel_t"])
        return start_epoch, events

    @staticmethod
    def _video_epoch(video_path: str) -> Optional[float]:
        match = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}-\d{2}-\d{2})", os.path.basename(video_path))
        if not match:
            return None
        date_text, time_text = match.groups()
        try:
            # Timestamped recordings use the machine's local timezone.
            return datetime.datetime.strptime(
                f"{date_text} {time_text.replace('-', ':')}", "%Y-%m-%d %H:%M:%S"
            ).timestamp()
        except ValueError:
            return None

    @classmethod
    def _is_game_key(cls, key: str) -> bool:
        return key.lower() in cls.GAME_KEYS

    def get_active_keys_at_time(self, rel_time: float, events: List[Dict[str, Any]]) -> List[str]:
        active = set()
        for event in events:
            if float(event.get("rel_t", 0.0)) > rel_time:
                break
            key = str(event.get("key", "")).lower()
            if event.get("event") == "DOWN":
                active.add(key)
            elif event.get("event") == "UP":
                active.discard(key)
        return [key for key in sorted(active) if OfflineDemonstrationSynchronizer._is_game_key(key)]

    def keys_to_steering_command(self, active_keys: List[str], duration_ms: int = 200) -> SteeringCommand:
        keys = set(key.lower() for key in active_keys)
        if "l" in keys:
            return SteeringCommand(action_type="HEAL", duration_ms=duration_ms, reason="human_key_l")
        if "space" in keys:
            return SteeringCommand(action_type="SKILL", duration_ms=duration_ms, reason="human_key_space")
        for perk in ("1", "2", "3"):
            if perk in keys:
                return SteeringCommand(action_type="SELECT_PERK", perk_index=int(perk),
                                       duration_ms=duration_ms, reason=f"human_perk_{perk}")
        dx = int("d" in keys) - int("a" in keys)
        dy = int("w" in keys) - int("s" in keys)
        moving = dx != 0 or dy != 0
        angle = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0 if moving else 90.0
        action_type = "MOVE" if moving else "ATTACK" if "j" in keys else "HOLD"
        return SteeringCommand(
            action_type=action_type, angle_degrees=angle,
            distance_ratio=1.0 if moving else 0.0,
            duration_ms=max(25, min(2000, int(duration_ms))),
            reason=f"human_keys_{'+'.join(sorted(keys)) if keys else 'none'}",
        )

    @staticmethod
    def _estimated_duration_ms(lookup_time: float, events: List[Dict[str, Any]]) -> int:
        for event in events:
            if not OfflineDemonstrationSynchronizer._is_game_key(str(event.get("key", ""))):
                continue
            delta = float(event["rel_t"]) - lookup_time
            if delta > 0.001:
                return max(25, min(2000, round(delta * 1000)))
        return 200

    def process_session(self, video_path: str, log_path: Optional[str] = None,
                        sample_interval: int = 15, max_frames: int = 30000) -> List[DemonstrationFrame]:
        if not os.path.exists(video_path):
            self.last_report = {"training_eligible": False, "issues": ["video_missing"]}
            return []
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            cap.release()
            self.last_report = {"training_eligible": False, "issues": ["video_unreadable"]}
            return []

        start_epoch, events = self.load_input_log(log_path) if log_path else (None, [])
        video_epoch = self._video_epoch(video_path)
        has_log = bool(start_epoch is not None and video_epoch is not None and events)
        offset = video_epoch - start_epoch if has_log else 0.0
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 60.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0.0
        log_duration = max((e["rel_t"] for e in events), default=0.0)
        start_rel, end_rel = offset, offset + duration
        in_window_events = [e for e in events if start_rel <= e["rel_t"] <= end_rel]
        mapped_count = sum(self._is_game_key(str(e.get("key", ""))) for e in in_window_events)
        mapped_fraction = mapped_count / max(1, len(in_window_events))
        overlap = max(0.0, min(end_rel, log_duration) - max(start_rel, 0.0)) if has_log else 0.0
        temporal_coverage = min(1.0, overlap / duration) if duration > 0 else 0.0

        self.perception = PerceptionEngine()
        self.world_model = WorldModel()

        frames: List[DemonstrationFrame] = []
        examples = []
        trajectory = []
        tracked_count = 0
        last_player_pos = None
        sample_interval = max(1, int(sample_interval))
        max_frames = max(1, int(max_frames))
        try:
            # Seek directly to sample points. Decoding all 25k frames of a long
            # clip just to inspect every fifteenth frame makes offline learning
            # needlessly expensive.
            for frame_idx in range(0, min(total_frames, max_frames), sample_interval):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                t_sec = frame_idx / fps
                perception = self.perception.analyze(frame, check_ocr_floor=False)
                world = self.world_model.update(perception)
                tracked = perception.player is not None
                tracked_count += int(tracked)
                active_keys = []
                if has_log:
                    lookup_time = offset + t_sec
                    active_keys = self.get_active_keys_at_time(lookup_time, events)
                    action = self.keys_to_steering_command(
                        active_keys, self._estimated_duration_ms(lookup_time, events)
                    )
                else:
                    action_type, angle = "MOVE", 90.0
                    current_pos = world.player_pos
                    if last_player_pos is not None:
                        dx, dy = current_pos[0] - last_player_pos[0], current_pos[1] - last_player_pos[1]
                        if math.hypot(dx, dy) > 8.0:
                            angle = (math.degrees(math.atan2(-dy, dx)) + 360.0) % 360.0
                        else:
                            action_type = "ATTACK"
                    last_player_pos = current_pos
                    action = SteeringCommand(action_type=action_type, angle_degrees=angle,
                                             reason="vision_estimate_unverified")
                demo = DemonstrationFrame(frame_idx, 0, t_sec, world, action, "HUMAN")
                frames.append(demo)
                examples.append((world, action, active_keys, tracked, float(perception.overall_confidence)))
                if action.action_type == "MOVE":
                    trajectory.append({"frame_idx": frame_idx, "time_sec": round(t_sec, 2),
                                       "angle_deg": round(action.angle_degrees, 1),
                                       "enemy_dist": round(world.nearest_enemy_dist, 1)})
                if len(frames) % 100 == 0:
                    print(f"[OfflineSynchronizer] processed {frame_idx}/{total_frames} frames", flush=True)
        finally:
            cap.release()

        tracked_fraction = tracked_count / max(1, len(frames))
        issues = []
        if not has_log:
            issues.append("missing_or_unmatched_input_log")
        if not in_window_events:
            issues.append("no_input_events_in_video_window")
        if tracked_fraction < 0.60:
            issues.append("low_player_tracking_coverage")
        if mapped_fraction < 0.15:
            issues.append("low_mapped_input_fraction")
        if temporal_coverage < 0.95:
            issues.append("low_log_video_time_overlap")
        quality = max(0.0, min(1.0, 0.55 * tracked_fraction + 0.30 * mapped_fraction + 0.15 * temporal_coverage))
        eligible = bool(has_log and tracked_fraction >= 0.60 and mapped_fraction >= 0.15
                        and temporal_coverage >= 0.95 and quality >= 0.50)

        # Only create a persistent session after video decoding completed, so a
        # crash during perception cannot leave an apparently active empty session.
        with self.db.get_connection() as conn:
            cursor = conn.execute("""INSERT INTO demonstration_sessions
                (source_type, quality_score, target_floor) VALUES ('HUMAN', ?, 71)""", (quality,))
            session_id = int(cursor.lastrowid)
        for demo in frames:
            demo.session_id = session_id

        with self.db.get_connection() as conn:
            for demo, sample in zip(frames, examples):
                world, action, active_keys, tracked, confidence = sample
                frame_eligible = eligible and tracked and confidence >= 0.50
                conn.execute("""INSERT INTO demonstration_frames
                    (session_id, timestamp, player_x, player_y, player_hp, action_type, action_angle,
                     game_state, nearest_enemy_dist, enemies_count, action_duration_ms, input_keys_json,
                     confidence, training_eligible)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, demo.timestamp, world.player_pos[0], world.player_pos[1], world.player_hp,
                     action.action_type, action.angle_degrees, world.game_state, world.nearest_enemy_dist,
                     world.enemies_count, action.duration_ms, json.dumps(active_keys), confidence,
                     int(frame_eligible)))
            conn.execute("""UPDATE demonstration_sessions SET end_time=CURRENT_TIMESTAMP,
                total_frames=?, quality_score=? WHERE session_id=?""", (len(frames), quality, session_id))
            conn.execute("""INSERT INTO demonstration_sync_reports
                (session_id, video_path, log_path, video_duration_sec, log_duration_sec, time_offset_sec,
                 sampled_frames, tracked_frames, mapped_input_fraction, quality_score, training_eligible, issues_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, os.path.abspath(video_path), os.path.abspath(log_path) if log_path else None,
                 duration, log_duration if events else None, offset if has_log else None,
                 len(frames), tracked_count, mapped_fraction, quality, int(eligible), json.dumps(issues)))
            conn.commit()

        if eligible:
            for world, action, _keys, tracked, confidence in examples:
                if tracked and confidence >= 0.50:
                    self.learner.record_example(world, action, "HUMAN", session_id=session_id)
            self.segmenter.segment_frames(frames)
        candidate_policy_id = self.learner.build_candidate() if eligible else None

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        trajectory_dir = os.path.join(base_dir, "data", "demonstrations", "trajectories")
        os.makedirs(trajectory_dir, exist_ok=True)
        trajectory_path = os.path.join(trajectory_dir, os.path.splitext(os.path.basename(video_path))[0] + "_sync.json")
        with open(trajectory_path, "w", encoding="utf-8") as stream:
            json.dump(trajectory, stream, indent=2, ensure_ascii=False)

        self.last_report = {
            "session_id": session_id, "video_duration_sec": duration,
            "log_duration_sec": log_duration if events else None, "time_offset_sec": offset,
            "sampled_frames": len(frames), "tracked_frames": tracked_count,
            "tracking_fraction": tracked_fraction, "mapped_input_fraction": mapped_fraction,
            "temporal_coverage": temporal_coverage, "quality_score": quality,
            "training_eligible": eligible, "issues": issues,
            "candidate_policy_id": candidate_policy_id,
        }
        return frames


def main():
    parser = argparse.ArgumentParser(description="Synchronize a gameplay video and passive input log.")
    parser.add_argument("video", help="Timestamped gameplay MP4 path")
    parser.add_argument("--log", help="Matching passive input JSONL path")
    parser.add_argument("--sample-interval", type=int, default=15)
    args = parser.parse_args()
    synchronizer = OfflineDemonstrationSynchronizer()
    synchronizer.process_session(args.video, args.log, sample_interval=max(1, args.sample_interval))
    print(json.dumps(synchronizer.last_report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
