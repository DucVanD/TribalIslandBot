# -*- coding: utf-8 -*-
"""
core/demonstration/behavior_segmenter.py
Phase P3: Behavior Segmentation
Phân tích và phân đoạn luồng hành vi liên tục thành các pha chiến thuật có cấu trúc:
- APPROACH: Tiến vào phòng, tiếp cận phạm vi bắn lý tưởng
- COMBAT: Kiting, giữ cự ly bắn tỉa và mở góc đạn
- RETREAT: Thoát hiểm khi quái áp sát hoặc mất máu
- STUCK_RECOVERY: Phá vỡ góc kẹt địa hình hoặc né cọc gỗ che đạn
"""

from typing import List, Optional, Dict, Any
from core.common_types import DemonstrationFrame, BehaviorSegment, WorldState, SteeringCommand
from core.memory.database import Database


class BehaviorSegmenter:
    """
    BehaviorSegmenter:
    Nhận diện pha chiến thuật (Tactical Phase) và phân đoạn chuỗi dữ liệu thị phạm.
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def classify_phase(self, world: WorldState) -> str:
        """
        Xác định pha chiến thuật của một trạng thái game.
        """
        # 1. Pha thoát kẹt
        if world.is_stuck or (not world.has_clear_shot and world.suggested_escape_angle is not None):
            return "STUCK_RECOVERY"

        # 2. Pha rút lui khẩn cấp (quái quá gần hoặc máu thấp)
        if (world.nearest_enemy and world.nearest_enemy_dist < 160.0) or world.player_hp < 35.0:
            return "RETREAT"

        # 3. Pha giao chiến (Combat / Kiting)
        if world.nearest_enemy and world.nearest_enemy_dist <= 550.0:
            return "COMBAT"

        # 4. Pha tiếp cận (Approach)
        return "APPROACH"

    def segment_frames(self, frames: List[DemonstrationFrame]) -> List[BehaviorSegment]:
        """
        Phân đoạn danh sách các frame thành các BehaviorSegment liên tục.
        """
        if not frames:
            return []

        segments: List[BehaviorSegment] = []
        current_phase = self.classify_phase(frames[0].world_state)
        current_frames: List[DemonstrationFrame] = []

        for f in frames:
            phase = self.classify_phase(f.world_state)
            if phase != current_phase:
                if current_frames:
                    start_f = current_frames[0]
                    end_f = current_frames[-1]
                    seg = BehaviorSegment(
                        segment_id=len(segments) + 1,
                        session_id=start_f.session_id,
                        phase_type=current_phase,
                        start_frame=start_f.frame_id,
                        end_frame=end_f.frame_id,
                        start_time=start_f.timestamp,
                        end_time=end_f.timestamp,
                        outcome="COMPLETED",
                        quality_score=1.0,
                        command_sequence=[cf.action for cf in current_frames]
                    )
                    segments.append(seg)
                current_phase = phase
                current_frames = [f]
            else:
                current_frames.append(f)

        # Segment cuối cùng
        if current_frames:
            start_f = current_frames[0]
            end_f = current_frames[-1]
            seg = BehaviorSegment(
                segment_id=len(segments) + 1,
                session_id=start_f.session_id,
                phase_type=current_phase,
                start_frame=start_f.frame_id,
                end_frame=end_f.frame_id,
                start_time=start_f.timestamp,
                end_time=end_f.timestamp,
                outcome="COMPLETED",
                quality_score=1.0,
                command_sequence=[cf.action for cf in current_frames]
            )
            segments.append(seg)

        # Lưu thông tin segments vào SQLite nếu có kết nối
        self._save_segments_to_db(segments)
        return segments

    def _save_segments_to_db(self, segments: List[BehaviorSegment]):
        """Lưu danh sách phân đoạn vào bảng behavior_segments."""
        if not segments:
            return
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                for seg in segments:
                    cursor.execute("""
                    INSERT INTO behavior_segments (
                        session_id, phase_type, start_frame, end_frame,
                        duration_sec, outcome, quality_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        seg.session_id,
                        seg.phase_type,
                        seg.start_frame,
                        seg.end_frame,
                        max(0.0, seg.end_time - seg.start_time),
                        seg.outcome,
                        seg.quality_score
                    ))
                conn.commit()
        except Exception as e:
            print(f"[BehaviorSegmenter] Lỗi lưu behavior_segments: {e}")
