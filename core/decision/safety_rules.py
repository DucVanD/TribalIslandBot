# -*- coding: utf-8 -*-
"""
core/decision/safety_rules.py
Tầng Safety Rules (Cấp 1 - Quyền ưu tiên cao nhất).
Cưỡng chế can thiệp trong các tình huống nguy hiểm:
- HP xuống dưới ngưỡng an toàn -> Bơm máu khẩn cấp
- Quái áp sát quá gần -> Thoát hiểm ngay lập tức
- Bị kẹt góc / cọc gỗ -> Kích hoạt Breakout Vector
- Mất độ tin cậy thị giác -> Fallback về kiting cổ điển
"""

import math
import time
from typing import Optional
from core.common_types import WorldState, SteeringCommand


class SafetyRules:
    """
    SafetyRules có quyền ngắt ngang (override) mọi quyết định di chuyển thông thường.
    """

    def __init__(self, hp_critical_percent: float = 35.0, danger_enemy_dist: float = 160.0):
        self.hp_critical_percent = hp_critical_percent
        self.danger_enemy_dist = danger_enemy_dist
        self.last_heal_time: float = 0.0
        self.heal_cooldown: float = 3.0  # Tối thiểu 3s giữa 2 lần bấm đùi gà

    def evaluate(self, world: WorldState) -> Optional[SteeringCommand]:
        """
        Đánh giá trạng thái thế giới.
        Trả về SteeringCommand khẩn cấp nếu có nguy cơ cao, ngược lại trả về None.
        """
        now = time.time()

        # 1. Khẩn cấp: Hồi máu nếu HP < ngưỡng và đã qua cooldown
        if 0.0 < world.player_hp < self.hp_critical_percent:
            if (now - self.last_heal_time) > self.heal_cooldown:
                self.last_heal_time = now
                return SteeringCommand(
                    action_type="HEAL",
                    reason=f"critical_hp_{world.player_hp:.1f}%"
                )

        # 2. Khẩn cấp: Quái áp sát quá gần (< danger_enemy_dist)
        if world.nearest_enemy and world.nearest_enemy_dist < self.danger_enemy_dist:
            px, py = world.player_pos
            ex = world.nearest_enemy.center_x
            ey = world.nearest_enemy.center_y
            # Hướng chạy ngược lại hoàn toàn với vị trí quái
            dx = px - ex
            dy = py - ey
            # Góc toán học: Android Y hướng xuống
            escape_rad = math.atan2(-dy, dx)
            escape_deg = (math.degrees(escape_rad) + 360.0) % 360.0
            return SteeringCommand(
                action_type="MOVE",
                angle_degrees=escape_deg,
                distance_ratio=1.0,
                duration_ms=450,
                reason=f"enemy_too_close_{world.nearest_enemy_dist:.0f}px"
            )

        # 3. Khẩn cấp: Phát hiện kẹt (Stuck)
        if world.is_stuck and world.suggested_escape_angle is not None:
            return SteeringCommand(
                action_type="MOVE",
                angle_degrees=world.suggested_escape_angle,
                distance_ratio=1.0,
                duration_ms=600,
                reason="stuck_recovery_breakout"
            )

        # 4. Dự phòng: Độ tin cậy nhận diện thấp (< 40%) -> Fallback Kiting an toàn
        if world.confidence < 0.40:
            # Chạy theo chu kỳ elip dự phòng an toàn
            fallback_angles = [45.0, 140.0, 225.0, 320.0]
            cycle_idx = int(now / 1.5) % len(fallback_angles)
            return SteeringCommand(
                action_type="MOVE",
                angle_degrees=fallback_angles[cycle_idx],
                distance_ratio=0.8,
                duration_ms=450,
                reason="low_confidence_fallback"
            )

        return None

