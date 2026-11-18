# -*- coding: utf-8 -*-
"""
core/world/world_model.py
WorldModel tổng hợp các thực thể từ PerceptionResult thành WorldState.
Quản lý:
- Khoảng cách đến quái vật gần nhất
- Đánh giá tầm nhìn đạn (Line of Sight) với cọc gỗ
- Phát hiện kẹt góc / kẹt cọc gỗ (Stuck Status)
- Tính toán vector thoát hiểm gợi ý (suggested_escape_angle)
"""

import time
import math
from typing import Optional, Tuple, List

from core.common_types import PerceptionResult, WorldState, Entity
from core.perception.line_of_sight import LineOfSightChecker
from core.navigation.stuck_detector import StuckDetector


class WorldModel:
    """
    WorldModel duy trì nhận thức không gian thống nhất của phòng chơi.
    Biến đổi tọa độ pixel thành trạng thái chiến thuật.
    """

    def __init__(self):
        self.los_checker = LineOfSightChecker()
        self.stuck_detector = StuckDetector(stuck_threshold_seconds=1.2, min_move_distance=30.0)
        
        # Theo dõi lịch sử vị trí để phát hiện kẹt
        self.last_player_pos: Tuple[int, int] = (960, 540)
        self.last_pos_time: float = time.time()
        self.last_blocked_los_time: Optional[float] = None
        self.stuck_escape_counter: int = 0
        self.last_portal_angle: Optional[float] = None
        self.last_portal_dist: Optional[float] = None
        self.last_portal_time: Optional[float] = None

    def update(self, perception: PerceptionResult) -> WorldState:
        """
        Cập nhật mô hình thế giới từ PerceptionResult mới nhất.
        """
        now = perception.timestamp or time.time()
        
        # 1. Xác định vị trí người chơi
        if perception.player is not None:
            player_pos = (perception.player.center_x, perception.player.center_y)
        else:
            player_pos = self.last_player_pos

        # 2. Tìm quái vật gần nhất
        nearest_enemy: Optional[Entity] = None
        min_enemy_dist = 9999.0

        for enemy in perception.enemies:
            dist = math.hypot(enemy.center_x - player_pos[0], enemy.center_y - player_pos[1])
            if dist < min_enemy_dist:
                min_enemy_dist = dist
                nearest_enemy = enemy

        # 3. Phân tích Line of Sight (đường đạn)
        has_clear_shot = True
        blocking_obs: Optional[Entity] = None

        if nearest_enemy is not None and perception.obstacles:
            target_pos = (nearest_enemy.center_x, nearest_enemy.center_y)
            obs_coords = [(obs.center_x, obs.center_y) for obs in perception.obstacles]
            
            is_clear, blocked_coord = self.los_checker.check_los(
                player_pos=player_pos,
                target_pos=target_pos,
                obstacles=obs_coords,
                obstacle_radius=42
            )
            has_clear_shot = is_clear
            if not is_clear and blocked_coord is not None:
                for obs in perception.obstacles:
                    if (obs.center_x, obs.center_y) == blocked_coord:
                        blocking_obs = obs
                        break

        # 4. Phát hiện kẹt (Stuck Detection: chỉ kích hoạt khi có quái mà bị cọc gỗ cản đạn > 1.2s)
        # Lưu ý: Trong game Top-Down, Camera khóa vào nhân vật (nhân vật luôn ở tâm màn hình).
        # Do đó không dùng độ dịch chuyển pixel màn hình để tránh báo kẹt giả mạo.
        is_stuck = False
        stuck_duration = 0.0
        suggested_escape_angle: Optional[float] = None

        if nearest_enemy is not None and not has_clear_shot:
            if self.last_blocked_los_time is None:
                self.last_blocked_los_time = now
            elif (now - self.last_blocked_los_time) > 1.2:
                is_stuck = True
                stuck_duration = now - self.last_blocked_los_time
        else:
            self.last_blocked_los_time = None
            self.stuck_detector.reset()

        # Tính góc thoát hiểm nếu bị cản đạn hoặc kẹt
        if not has_clear_shot or is_stuck:
            if blocking_obs is not None:
                # Thoát theo hướng ngược hướng với cọc gỗ
                dx = player_pos[0] - blocking_obs.center_x
                dy = player_pos[1] - blocking_obs.center_y
                escape_rad = math.atan2(-dy, dx)
                escape_deg = (math.degrees(escape_rad) + 360.0) % 360.0
                suggested_escape_angle = escape_deg
            else:
                self.stuck_escape_counter += 1
                escape_rotation = [90.0, 45.0, 135.0, 0.0, 180.0, 270.0]
                suggested_escape_angle = escape_rotation[(self.stuck_escape_counter - 1) % len(escape_rotation)]
        else:
            self.stuck_escape_counter = 0

        # Cập nhật mốc vị trí
        dist_moved = math.hypot(player_pos[0] - self.last_player_pos[0],
                                player_pos[1] - self.last_player_pos[1])
        if dist_moved > 30:
            self.last_player_pos = player_pos
            self.last_pos_time = now

        # 5. Phân tích Cổng dịch chuyển (Portal)
        portal_angle: Optional[float] = None
        portal_dist: Optional[float] = None
        if perception.portal is not None:
            p_cx = perception.portal.center_x
            p_cy = perception.portal.center_y
            dx = p_cx - player_pos[0]
            dy = -(p_cy - player_pos[1])  # Tọa độ toán học: dy > 0 hướng lên trên (Bắc)
            raw_angle = float((math.degrees(math.atan2(dy, dx))) % 360.0)
            raw_dist = float(math.hypot(dx, dy))
            if (self.last_portal_angle is not None and self.last_portal_time is not None
                    and now - self.last_portal_time <= 3.5):
                # A single noisy portal detection must not make the joystick
                # reverse across the room. Smooth the circular bearing and
                # cap its per-frame turn while still allowing gradual rerouting.
                delta = (raw_angle - self.last_portal_angle + 180.0) % 360.0 - 180.0
                delta = max(-35.0, min(35.0, delta))
                portal_angle = (self.last_portal_angle + 0.65 * delta) % 360.0
                portal_dist = 0.65 * raw_dist + 0.35 * self.last_portal_dist
            else:
                portal_angle = raw_angle
                portal_dist = raw_dist
            self.last_portal_angle = portal_angle
            self.last_portal_dist = portal_dist
            self.last_portal_time = now
        elif (self.last_portal_time is None or now - self.last_portal_time > 3.5):
            self.last_portal_angle = None
            self.last_portal_dist = None
            self.last_portal_time = None

        # 6. Xác định trạng thái game chung
        game_state = "FIGHTING"
        if perception.is_lobby:
            game_state = "LOBBY"
        elif perception.is_level_up:
            game_state = "LEVEL_UP"
        elif perception.is_battle_end:
            game_state = "BATTLE_END"
        elif perception.hp_percent <= 0.0 and perception.overall_confidence > 0.8:
            game_state = "DEAD"

        return WorldState(
            timestamp=now,
            player_pos=player_pos,
            player_hp=perception.hp_percent,
            current_floor=perception.current_floor,
            game_state=game_state,
            nearest_enemy=nearest_enemy,
            nearest_enemy_dist=min_enemy_dist,
            enemies_count=len(perception.enemies),
            has_clear_shot=has_clear_shot,
            blocking_obstacle=blocking_obs,
            is_stuck=is_stuck,
            stuck_duration=stuck_duration,
            suggested_escape_angle=suggested_escape_angle,
            portal=perception.portal,
            portal_angle=portal_angle,
            portal_dist=portal_dist,
            shard_count=perception.shard_count,
            confidence=perception.overall_confidence
        )

    def reset_portal_track(self):
        """Forget the previous floor's portal bearing after a floor transition."""
        self.last_portal_angle = None
        self.last_portal_dist = None
        self.last_portal_time = None

