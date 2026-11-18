# -*- coding: utf-8 -*-
"""
core/perception/detector_enemy.py
Nhận diện quái vật và Boss từ khung hình dựa trên thanh máu đỏ mini và hình thái.
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional
from core.common_types import Entity


class EnemyDetector:
    """
    EnemyDetector:
    Phát hiện quái vật thông qua:
    - Thanh máu đỏ mini trên đầu quái vật.
    - Phân đoạn hình khối quái vật trong khu vực chiến đấu.
    - Loại trừ các nút bấm UI màu đỏ/cam (như nút Lửa tấn công).
    """

    def __init__(self, ref_width: int = 1920, ref_height: int = 1080):
        self.ref_width = ref_width
        self.ref_height = ref_height

    def detect(self, frame: np.ndarray, player_pos: Optional[Tuple[int, int]] = None) -> List[Entity]:
        """
        Quét và trả về danh sách các Entity(category='enemy').
        """
        if frame is None or frame.size == 0:
            return []

        h_img, w_img = frame.shape[:2]
        scale = w_img / 1920.0
        enemies: List[Entity] = []
        found_coords: List[Tuple[int, int]] = []

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # 1. Phát hiện qua dải màu đỏ của thanh máu quái (Red HP Bar)
        # HSV màu đỏ trải ở 2 dải: 0-10 và 170-180
        mask_r1 = cv2.inRange(hsv, (0, 115, 100), (10, 255, 255))
        mask_r2 = cv2.inRange(hsv, (170, 115, 100), (180, 255, 255))
        mask_red = cv2.bitwise_or(mask_r1, mask_r2)

        # Loại bỏ vùng UI (chính xác từng phần, không che khuất vùng sàn chiến đấu)
        # Top bar (HP người chơi và thông số tầng góc trên trái)
        mask_red[:int(h_img * 0.15), :int(w_img * 0.35)] = 0
        # Nút bắn to (Góc phải dưới: x > 80%, y > 74%)
        mask_red[int(h_img * 0.74):, int(w_img * 0.80):] = 0
        # Hàng kỹ năng perk ở đáy chính giữa (chỉ che vùng x từ 35% đến 65% ở sát mép đáy y > 92%)
        mask_red[int(h_img * 0.92):, int(w_img * 0.35):int(w_img * 0.65)] = 0

        cnts, _ = cv2.findContours(mask_red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            # Thanh máu quái mini có chiều rộng ~ 14 -> 120px, chiều cao ~ 2 -> 20px
            min_w = int(14 * scale)
            max_w = int(120 * scale)
            min_h = int(2 * scale)
            max_h = int(20 * scale)

            if min_w <= w <= max_w and min_h <= h <= max_h:
                aspect = float(w) / float(max(1, h))
                if 2.2 <= aspect <= 15.0:
                    cx = int(x + w / 2)
                    cy = int(y + h / 2 + (30 * scale))  # Thân quái nằm dưới thanh máu

                    # Tránh nhầm với người chơi nếu player_pos đã được xác định
                    if player_pos is not None:
                        dist_to_player = math_dist((cx, cy), player_pos)
                        if dist_to_player < (40 * scale):
                            continue

                    too_close = False
                    for fx, fy in found_coords:
                        if math_dist((cx, cy), (fx, fy)) < (60 * scale):
                            too_close = True
                            break

                    if not too_close:
                        found_coords.append((cx, cy))
                        enemies.append(Entity(
                            id=len(enemies) + 1,
                            category="enemy",
                            center_x=cx,
                            center_y=cy,
                            radius=int(45 * scale),
                            confidence=0.88,
                            hp_percent=100.0
                        ))

        return enemies


def math_dist(p1: Tuple[int, int], p2: Tuple[int, int]) -> float:
    return float(np.hypot(p1[0] - p2[0], p1[1] - p2[1]))

