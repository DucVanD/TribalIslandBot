# -*- coding: utf-8 -*-
"""
core/perception/perception_engine.py
PerceptionEngine là bộ điều phối thị giác tập trung:
- Gọi PlayerDetector, EnemyDetector, HazardDetector
- Sử dụng VisionEngine để đọc UI (HP %, số tầng, Level Up, Lobby, Kết thúc trận)
- Đóng gói toàn bộ thành một đối tượng PerceptionResult thống nhất.
"""

import time
import math
import numpy as np
from typing import Optional

from core.common_types import PerceptionResult, Entity
from core.engine_vision import VisionEngine
from .detector_player import PlayerDetector
from .detector_enemy import EnemyDetector
from .detector_hazard import HazardDetector


class PerceptionEngine:
    """
    PerceptionEngine:
    Tầng nhận thức thị giác cao cấp của TribalIslandBot.
    Biến đổi ảnh thô (BGR frame) thành dữ liệu đối tượng có cấu trúc.
    """

    PORTAL_TRACK_TTL_SECONDS = 3.2

    def __init__(self, vision_engine: Optional[VisionEngine] = None):
        self.vision = vision_engine or VisionEngine()
        self.player_detector = PlayerDetector()
        self.enemy_detector = EnemyDetector()
        self.hazard_detector = HazardDetector()
        self.frame_counter = 0
        self._last_portal = None
        self._last_portal_time = 0.0

    def _portal_candidate_jumps(self, candidate: Entity, player_pos, now: float) -> bool:
        """Reject a sudden bearing/position jump while a portal track is fresh."""
        if (self._last_portal is None
                or now - self._last_portal_time >= self.PORTAL_TRACK_TTL_SECONDS):
            return False

        shift = math.hypot(
            candidate.center_x - self._last_portal.center_x,
            candidate.center_y - self._last_portal.center_y,
        )
        old_dx = self._last_portal.center_x - player_pos[0]
        old_dy = player_pos[1] - self._last_portal.center_y
        new_dx = candidate.center_x - player_pos[0]
        new_dy = player_pos[1] - candidate.center_y
        old_bearing = math.degrees(math.atan2(old_dy, old_dx)) % 360.0
        new_bearing = math.degrees(math.atan2(new_dy, new_dx)) % 360.0
        bearing_delta = abs((new_bearing - old_bearing + 180.0) % 360.0 - 180.0)
        return shift > 220.0 or bearing_delta > 45.0

    def reset_portal_track(self):
        """Drop a cached portal when the game advances to another floor."""
        self._last_portal = None
        self._last_portal_time = 0.0

    def analyze(self, frame: np.ndarray, check_ocr_floor: bool = False) -> PerceptionResult:
        """
        Phân tích toàn diện 1 khung hình.
        - frame: Ảnh BGR từ ActionEngine.fast_capture_screen()
        - check_ocr_floor: True nếu muốn gọi OCR đọc số tầng (nên chạy định kỳ vì OCR tốn CPU).
        """
        self.frame_counter += 1
        t_start = time.time()

        if frame is None or frame.size == 0:
            return PerceptionResult(timestamp=t_start, frame_id=self.frame_counter, overall_confidence=0.0)

        # 1. Quét trạng thái UI quan trọng
        hp_val = self.vision.get_hp_percentage(frame)
        is_lvl_up = self.vision.is_level_up_screen(frame)
        found_start, _ = self.vision.find_lobby_start_button(frame)
        shard_count = self.vision.detect_shard_count(frame, is_lobby=found_start)

        is_end = False
        end_btn_coords = None
        # Chỉ kiểm tra kết thúc trận khi không ở màn hình Lên Cấp hoặc Sảnh Chờ
        if not is_lvl_up and not found_start:
            is_end = self.vision.is_end_battle_screen(frame)
            if is_end:
                found_end_btn, detected_coords = self.vision.find_end_battle_button(frame)
                if found_end_btn:
                    end_btn_coords = detected_coords

        floor_num = 1
        if check_ocr_floor:
            floor_num = self.vision.detect_floor_number(frame) or 1

        # 2. Quét thực thể: Player
        player = self.player_detector.detect(frame)
        player_pos = (player.center_x, player.center_y) if player else None

        # 3. Quét thực thể: Quái vật
        enemies = self.enemy_detector.detect(frame, player_pos=player_pos)

        # 4. Quét thực thể: Cọc gỗ / Vật cản
        obstacles = self.hazard_detector.detect(frame)

        # 5. Quét thực thể: Cổng dịch chuyển (chỉ khi phòng đã thật sự sạch quái)
        portal_entity = None
        if len(enemies) == 0:
            previous_portal_pos = (
                (self._last_portal.center_x, self._last_portal.center_y)
                if self._last_portal is not None
                and t_start - self._last_portal_time < self.PORTAL_TRACK_TTL_SECONDS
                else None
            )
            found_portal, portal_coords = self.vision.find_portal(
                frame, player_pos=player_pos, previous_portal=previous_portal_pos
            )
            if found_portal and portal_coords:
                candidate = Entity(
                    id=999,
                    category="portal",
                    center_x=portal_coords[0],
                    center_y=portal_coords[1],
                    radius=int(60 * (w_img / 1920.0 if 'w_img' in locals() else frame.shape[1] / 1920.0)),
                    confidence=0.95
                )
                if not self._portal_candidate_jumps(candidate, player_pos, t_start):
                    self._last_portal = candidate
                    self._last_portal_time = t_start
                    portal_entity = candidate

            # Preserve a recent stable target for brief detector dropouts, so
            # one missed frame does not send the agent back to a fixed heading.
            if portal_entity is None and self._last_portal is not None:
                age = t_start - self._last_portal_time
                if age <= self.PORTAL_TRACK_TTL_SECONDS:
                    portal_entity = Entity(
                        id=999,
                        category="portal",
                        center_x=self._last_portal.center_x,
                        center_y=self._last_portal.center_y,
                        radius=self._last_portal.radius,
                        confidence=max(0.45, 0.80 - age * 0.2),
                    )

        if is_lvl_up or found_start or is_end:
            self._last_portal = None
            self._last_portal_time = 0.0

        # 6. Tính toán overall confidence
        confidence = 1.0
        if player is not None:
            confidence = min(confidence, player.confidence)
        else:
            confidence = 0.4

        result = PerceptionResult(
            timestamp=t_start,
            frame_id=self.frame_counter,
            player=player,
            enemies=enemies,
            obstacles=obstacles,
            portal=portal_entity,
            hp_percent=hp_val if hp_val is not None else 100.0,
            current_floor=floor_num,
            is_level_up=is_lvl_up,
            is_lobby=found_start,
            is_battle_end=is_end,
            end_btn_coords=end_btn_coords,
            overall_confidence=confidence,
            shard_count=shard_count,
        )

        return result
