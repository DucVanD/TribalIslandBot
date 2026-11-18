# -*- coding: utf-8 -*-
"""
core/navigation/stuck_detector.py
Phát hiện kẹt góc / kẹt cọc gỗ và đề xuất hướng giải cứu (Breakout Vector).
"""

import time
import math
from typing import Tuple, Optional


class StuckDetector:
    """
    StuckDetector:
    Theo dõi quãng đường di chuyển thực tế của nhân vật trong cửa sổ thời gian trượt.
    Nếu nhân vật bị kẹt không di chuyển trong quá 1.5 giây, sinh tín hiệu giải cứu.
    """

    def __init__(self, stuck_threshold_seconds: float = 1.5, min_move_distance: float = 35.0):
        self.stuck_threshold = stuck_threshold_seconds
        self.min_move_dist = min_move_distance

        self.last_pos: Optional[Tuple[int, int]] = None
        self.last_pos_time: float = time.time()
        self.is_stuck_flag: bool = False

    def update(self, current_pos: Tuple[int, int]) -> Tuple[bool, float]:
        """
        Cập nhật vị trí hiện tại.
        Trả về: (is_stuck, stuck_duration)
        """
        now = time.time()
        if self.last_pos is None:
            self.last_pos = current_pos
            self.last_pos_time = now
            return False, 0.0

        dist = math.hypot(current_pos[0] - self.last_pos[0], current_pos[1] - self.last_pos[1])

        if dist >= self.min_move_dist:
            # Đang di chuyển tốt -> Reset timer
            self.last_pos = current_pos
            self.last_pos_time = now
            self.is_stuck_flag = False
            return False, 0.0
        else:
            # Đứng im hoặc dao động nhỏ tại chỗ
            duration = now - self.last_pos_time
            if duration >= self.stuck_threshold:
                self.is_stuck_flag = True
                return True, duration
            return False, duration

    def reset(self):
        self.last_pos = None
        self.last_pos_time = time.time()
        self.is_stuck_flag = False

