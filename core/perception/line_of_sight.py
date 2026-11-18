import cv2
import numpy as np
from typing import List, Tuple, Optional


class LineOfSightChecker:
    """
    LineOfSightChecker kiểm tra xem đường đạn giữa Người chơi và Quái vật
    có bị chặn bởi các vật cản (như Cọc gỗ, Tảng đá, Bờ tường) hay không.
    """

    def __init__(self):
        pass

    @staticmethod
    def is_segment_intersecting_circle(p1: Tuple[int, int], p2: Tuple[int, int],
                                       circle_center: Tuple[int, int], radius: int) -> bool:
        """
        Kiểm tra đoạn thẳng p1->p2 (đường đạn) có cắt qua hình tròn bán kính radius (vật cản cọc gỗ) không.
        """
        x1, y1 = p1
        x2, y2 = p2
        cx, cy = circle_center

        # Vector p1 -> p2
        dx = x2 - x1
        dy = y2 - y1
        line_len_sq = dx * dx + dy * dy

        if line_len_sq == 0:
            return (cx - x1)**2 + (cy - y1)**2 <= radius**2

        # Chiếu tâm hình tròn lên đoạn thẳng (từ 0.0 -> 1.0)
        t = max(0.0, min(1.0, ((cx - x1) * dx + (cy - y1) * dy) / line_len_sq))

        # Tọa độ điểm gần nhất trên đoạn thẳng
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy

        dist_sq = (cx - closest_x)**2 + (cy - closest_y)**2
        return dist_sq <= (radius**2)

    def check_los(self, player_pos: Tuple[int, int], target_pos: Tuple[int, int],
                  obstacles: List[Tuple[int, int]], obstacle_radius: int = 45) -> Tuple[bool, Optional[Tuple[int, int]]]:
        """
        Kiểm tra tầm bắn (Line of Sight):
        - player_pos: Tọa độ người chơi (x, y)
        - target_pos: Tọa độ quái vật mục tiêu (x, y)
        - obstacles: Danh sách tọa độ tâm các cọc gỗ [(x, y), ...]
        - obstacle_radius: Bán kính an toàn của cọc gỗ

        Trả về:
        - has_clear_shot: True nếu đường bắn thông thoáng, False nếu bị chặn
        - blocking_obstacle: Tọa độ cọc gỗ gây cản trở (nếu có)
        """
        for obs in obstacles:
            if self.is_segment_intersecting_circle(player_pos, target_pos, obs, obstacle_radius):
                return False, obs
        return True, None

