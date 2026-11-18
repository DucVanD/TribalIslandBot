# -*- coding: utf-8 -*-
"""
core/navigation/vector_steering.py
Tính toán góc di chuyển tối ưu 360 độ dựa trên hàm chấm điểm hành động:
Score(theta) = w_s * S(theta) + w_d * D(theta) + w_l * L(theta) + w_m * M(theta)
"""

import math
from typing import List, Tuple, Dict, Optional
from core.common_types import WorldState, Entity
from core.perception.line_of_sight import LineOfSightChecker


class VectorSteering:
    """
    VectorSteering:
    Chấm điểm 8 hướng ứng viên và chọn góc di chuyển mang lại lợi thế chiến thuật cao nhất.
    """

    CANDIDATE_ANGLES = [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]

    def __init__(self, w_s: float = 0.30, w_d: float = 0.20, w_l: float = 0.25,
                 w_m: float = 0.10, w_demo: float = 0.15, behavior_prior=None):
        self.w_s = w_s        # Safety weight
        self.w_d = w_d        # Distance weight
        self.w_l = w_l        # Line of sight weight
        self.w_m = w_m        # Memory weight
        self.w_demo = w_demo  # Demonstration learning weight
        self.behavior_prior = behavior_prior
        self.adaptive_learner = None
        self.los_checker = LineOfSightChecker()
        self.ideal_dist = 450.0  # Cự ly kiting lý tưởng (pixels)
        self.last_chosen_angle: Optional[float] = None

    def set_weights(self, w_s: float, w_d: float, w_l: float, w_m: float, w_demo: float = 0.15):
        """Cập nhật trọng số từ Persistent Memory & Demonstration."""
        self.w_s = w_s
        self.w_d = w_d
        self.w_l = w_l
        self.w_m = w_m
        self.w_demo = w_demo

    def find_best_angle(self, world: WorldState, obstacles: List[Entity],
                        memory_bias: Optional[Dict[float, float]] = None) -> Tuple[float, float]:
        """
        Đánh giá các góc ứng viên và trả về (best_angle, best_score).
        """
        px, py = world.player_pos
        step_len = 160.0  # Dự đoán vị trí sau một nhịp swipe
        best_angle = 90.0
        best_score = -999.0

        for angle in self.CANDIDATE_ANGLES:
            rad = math.radians(angle)
            # Hệ tọa độ Android: Y hướng xuống nên -sin(rad)
            projected_x = px + step_len * math.cos(rad)
            projected_y = py - step_len * math.sin(rad)

            # 1. Điểm an toàn S(theta):
            # Không đâm vào tường mép màn hình (giới hạn an toàn: 150 < x < 1770, 150 < y < 930)
            score_s = 100.0
            if projected_x < 200 or projected_x > 1720 or projected_y < 160 or projected_y > 900:
                score_s -= 60.0

            # Né cọc gỗ
            for obs in obstacles:
                dist_obs = math.hypot(projected_x - obs.center_x, projected_y - obs.center_y)
                if dist_obs < (obs.radius + 50):
                    score_s -= 50.0

            # Né quái nếu projected pos quá gần quái
            if world.nearest_enemy:
                ex = world.nearest_enemy.center_x
                ey = world.nearest_enemy.center_y
                dist_enemy = math.hypot(projected_x - ex, projected_y - ey)
                if dist_enemy < 160.0:
                    score_s -= 70.0
                elif dist_enemy < 250.0:
                    score_s -= 30.0

            score_s = max(0.0, min(100.0, score_s))

            # 2. Điểm cự ly D(theta):
            score_d = 50.0
            if world.nearest_enemy:
                ex = world.nearest_enemy.center_x
                ey = world.nearest_enemy.center_y
                dist_enemy = math.hypot(projected_x - ex, projected_y - ey)
                # Càng gần cự ly lý tưởng (450px) càng điểm cao
                deviation = abs(dist_enemy - self.ideal_dist)
                score_d = max(0.0, 100.0 - (deviation / 4.0))
            else:
                # Khi chưa thấy quái hoặc đã dọn sạch phòng: Ưu tiên tiến lên trên (90°)
                angle_diff_to_up = abs(angle - 90.0)
                score_d = max(20.0, 100.0 - (angle_diff_to_up * 0.7))

            # 3. Điểm tầm nhìn đạn L(theta):
            score_l = 100.0
            if world.nearest_enemy and obstacles:
                ex = world.nearest_enemy.center_x
                ey = world.nearest_enemy.center_y
                obs_coords = [(obs.center_x, obs.center_y) for obs in obstacles]
                is_clear, _ = self.los_checker.check_los(
                    (int(projected_x), int(projected_y)),
                    (ex, ey),
                    obs_coords,
                    obstacle_radius=42
                )
                score_l = 100.0 if is_clear else 15.0

            # 4. Điểm kinh nghiệm M(theta):
            score_m = 50.0
            if memory_bias and angle in memory_bias:
                score_m = memory_bias[angle]

            # 5. Điểm mô phỏng thị phạm Demo(theta):
            score_demo = 60.0
            learned_score = None
            if self.adaptive_learner is not None:
                learned_score = self.adaptive_learner.score_action(world, angle)
            if learned_score is not None:
                score_demo = learned_score
            elif self.behavior_prior is not None:
                score_demo = self.behavior_prior.get_demonstration_score(
                    candidate_angle=angle,
                    last_angle=self.last_chosen_angle,
                    enemy_dist=world.nearest_enemy_dist if world.nearest_enemy else None
                )

            # Tổng hợp điểm số
            total_score = (self.w_s * score_s +
                           self.w_d * score_d +
                           self.w_l * score_l +
                           self.w_m * score_m +
                           self.w_demo * score_demo)

            if total_score > best_score:
                best_score = total_score
                best_angle = angle

        self.last_chosen_angle = best_angle
        return best_angle, best_score

    def find_route_angle(self, world: WorldState, obstacles: List[Entity]) -> Tuple[float, float]:
        """Choose a north-progressing route heading while avoiding visible blockers.

        This is for empty milestone floors: do not let combat demonstrations or
        learned kiting preferences turn portal search into a circular patrol.
        """
        px, py = world.player_pos
        step_len = 190.0
        best_angle, best_score = 90.0, float("-inf")
        for angle in (90.0, 45.0, 135.0, 0.0, 180.0, 315.0, 225.0, 270.0):
            rad = math.radians(angle)
            x = px + step_len * math.cos(rad)
            y = py - step_len * math.sin(rad)
            clearance = 100.0
            if x < 180 or x > 1740 or y < 150 or y > 930:
                clearance -= 70.0
            for obstacle in obstacles:
                distance = math.hypot(x - obstacle.center_x, y - obstacle.center_y)
                if distance < obstacle.radius + 35:
                    clearance -= 80.0
                elif distance < obstacle.radius + 85:
                    clearance -= 35.0
            angular_distance = abs((angle - 90.0 + 180.0) % 360.0 - 180.0)
            north_progress = 100.0 - angular_distance * 0.75
            score = 0.60 * north_progress + 0.40 * max(0.0, clearance)
            if self.last_chosen_angle is not None:
                reversal = abs((angle - self.last_chosen_angle + 180.0) % 360.0 - 180.0)
                if reversal >= 135.0:
                    score -= 12.0
            if score > best_score:
                best_angle, best_score = angle, score
        self.last_chosen_angle = best_angle
        return best_angle, best_score

