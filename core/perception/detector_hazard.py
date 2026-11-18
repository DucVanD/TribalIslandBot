# -*- coding: utf-8 -*-
"""
core/perception/detector_hazard.py
Nhận diện vật cản (Cọc gỗ tròn, Tường chắn) từ khung hình.
"""

import cv2
import numpy as np
import os
from typing import List, Tuple, Optional
from core.common_types import Entity


class HazardDetector:
    """
    HazardDetector:
    Phát hiện các cọc gỗ tròn (Tree Stumps) và vật cản trên sàn.
    Kết hợp Template Matching với dải màu gỗ và phân tích hình học tròn.
    """

    def __init__(self, assets_dir: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.assets_dir = assets_dir or os.path.join(base_dir, "assets")
        self.stump_template = None
        self._load_templates()

    def _load_templates(self):
        stump_path = os.path.join(self.assets_dir, "stump_sample.png")
        if os.path.exists(stump_path):
            self.stump_template = cv2.imread(stump_path)

    def detect(self, frame: np.ndarray) -> List[Entity]:
        """
        Quét và trả về danh sách các Entity(category='obstacle_stump').
        """
        if frame is None or frame.size == 0:
            return []

        h_img, w_img = frame.shape[:2]
        scale = w_img / 1920.0
        obstacles: List[Entity] = []
        found_coords: List[Tuple[int, int]] = []

        # 1. Template Matching nếu có ảnh mẫu
        if self.stump_template is not None:
            tpl = self.stump_template
            if scale != 1.0:
                new_w = max(10, int(tpl.shape[1] * scale))
                new_h = max(10, int(tpl.shape[0] * scale))
                tpl = cv2.resize(tpl, (new_w, new_h))

            th, tw = tpl.shape[:2]
            res = cv2.matchTemplate(frame, tpl, cv2.TM_CCOEFF_NORMED)
            # Ngưỡng phát hiện cọc gỗ
            locs = np.where(res >= 0.58)
            for pt in zip(*locs[::-1]):
                cx = int(pt[0] + tw / 2)
                cy = int(pt[1] + th / 2)

                # Bỏ qua vùng UI: Joystick (trái dưới) & Nút bắn (phải dưới) & Top bar
                if cy > h_img * 0.80 and (cx < w_img * 0.35 or cx > w_img * 0.75):
                    continue
                if cy < h_img * 0.08:
                    continue

                # Loại bỏ các điểm quá gần nhau (Non-maximum suppression cục bộ)
                too_close = False
                for fx, fy in found_coords:
                    if (cx - fx)**2 + (cy - fy)**2 < (50 * scale)**2:
                        too_close = True
                        break

                if not too_close:
                    found_coords.append((cx, cy))
                    score = float(res[pt[1], pt[0]])
                    obstacles.append(Entity(
                        id=len(obstacles) + 1,
                        category="obstacle_stump",
                        center_x=cx,
                        center_y=cy,
                        radius=int(40 * scale),
                        confidence=min(0.95, score)
                    ))

        # 2. Phân đoạn màu gỗ / đầu cọc tròn (HSV Wood Segment)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        # Màu gỗ / vân cọc tròn
        mask_wood = cv2.inRange(hsv, (10, 60, 60), (25, 230, 200))
        # Loại trừ UI
        mask_wood[:int(h_img * 0.08), :] = 0
        mask_wood[int(h_img * 0.85):, :] = 0
        mask_wood[:, :int(w_img * 0.05)] = 0
        mask_wood[:, int(w_img * 0.95):] = 0

        cnts, _ = cv2.findContours(mask_wood, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            # Cọc gỗ thường có dạng khối gần vuông / tròn
            min_dim = int(25 * scale)
            max_dim = int(90 * scale)
            if min_dim <= w <= max_dim and min_dim <= h <= max_dim:
                aspect = float(w) / float(max(1, h))
                if 0.7 <= aspect <= 1.4:
                    cx = int(x + w / 2)
                    cy = int(y + h / 2)

                    # Bỏ qua vùng UI góc
                    if cy > h_img * 0.75 and (cx < w_img * 0.35 or cx > w_img * 0.75):
                        continue

                    too_close = False
                    for fx, fy in found_coords:
                        if (cx - fx)**2 + (cy - fy)**2 < (45 * scale)**2:
                            too_close = True
                            break

                    if not too_close:
                        found_coords.append((cx, cy))
                        obstacles.append(Entity(
                            id=len(obstacles) + 1,
                            category="obstacle_stump",
                            center_x=cx,
                            center_y=cy,
                            radius=int(38 * scale),
                            confidence=0.75
                        ))

        return obstacles
