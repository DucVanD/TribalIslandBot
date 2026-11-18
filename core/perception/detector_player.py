# -*- coding: utf-8 -*-
"""
core/perception/detector_player.py
Nhận diện vị trí người chơi (Player) từ thanh máu xanh lá cây trên đầu.
"""

import cv2
import numpy as np
from typing import Optional, Tuple
from core.common_types import Entity


class PlayerDetector:
    """
    PlayerDetector:
    Phân đoạn thanh máu xanh lá cây (Green HP bar) phía trên đầu nhân vật.
    Tính toán tọa độ trung tâm người chơi kèm Confidence score.
    """

    def __init__(self, ref_width: int = 1920, ref_height: int = 1080):
        self.ref_width = ref_width
        self.ref_height = ref_height
        self.last_known_pos: Tuple[int, int] = (960, 540) # Mặc định tâm màn hình

    def detect(self, frame: np.ndarray) -> Optional[Entity]:
        """
        Nhận diện người chơi từ frame BGR.
        Trả về Entity(category='player') hoặc None nếu không thấy.
        """
        if frame is None or frame.size == 0:
            return None

        h_img, w_img = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Dải màu xanh lá cây đặc trưng của thanh máu nhân vật
        mask_green = cv2.inRange(hsv, (40, 140, 140), (85, 255, 255))

        # Loại bỏ vùng UI trên cùng (top bar, y < 12% h_img) và UI dưới cùng (joystick/skill, y > 88% h_img)
        mask_clean = mask_green.copy()
        mask_clean[:int(h_img * 0.12), :] = 0
        mask_clean[int(h_img * 0.88):, :] = 0

        cnts, _ = cv2.findContours(mask_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_entity = None
        best_score = 0.0

        scale = w_img / 1920.0

        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            # Thanh máu nhân vật có chiều rộng từ 25 -> 240px, chiều cao từ 4 -> 35px
            min_w = int(25 * scale)
            max_w = int(240 * scale)
            min_h = int(4 * scale)
            max_h = int(35 * scale)

            if min_w <= w <= max_w and min_h <= h <= max_h:
                aspect = float(w) / float(max(1, h))
                if 2.0 <= aspect <= 15.0:
                    center_x = int(x + w / 2)
                    center_y = int(y + h / 2 + (35 * scale))

                    # Ưu tiên thanh máu nằm gần khu vực trung tâm điều khiển
                    dist_to_center = ((center_x - w_img / 2) ** 2 + (center_y - h_img / 2) ** 2) ** 0.5
                    center_bonus = max(0.0, 1.0 - (dist_to_center / (w_img * 0.5)))
                    confidence = min(0.98, 0.70 + min(0.20, (w * h) / (1500.0 * scale)) + center_bonus * 0.10)

                    score = (w * h) / 1000.0 + center_bonus * 2.0
                    if score > best_score:
                        best_score = score
                        best_entity = Entity(
                            id=0,
                            category="player",
                            center_x=center_x,
                            center_y=center_y,
                            radius=int(35 * scale),
                            confidence=confidence,
                            hp_percent=100.0
                        )

        if best_entity:
            self.last_known_pos = (best_entity.center_x, best_entity.center_y)
            return best_entity

        # Nếu không nhận diện được, trả về Entity dự phòng với confidence thấp
        return Entity(
            id=0,
            category="player",
            center_x=self.last_known_pos[0],
            center_y=self.last_known_pos[1],
            radius=int(35 * scale),
            confidence=0.35,
            hp_percent=100.0
        )

