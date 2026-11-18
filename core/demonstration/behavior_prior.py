# -*- coding: utf-8 -*-
"""
core/demonstration/behavior_prior.py
BehaviorPrior:
Tổng hợp phân phối xác suất hành vi của người chơi mẫu từ dữ liệu thị phạm (Demonstration Data).
Chấm điểm mức độ tương đồng giữa hành động ứng viên và phản xạ thực tế của người chơi.
"""

import os
import json
import math
from typing import List, Dict, Optional


class BehaviorPrior:
    """
    BehaviorPrior cung cấp điểm thưởng hành vi Demonstration Score:
    Score_demo(a) phản ánh mức độ tự nhiên, mượt mà và nhịp kiting như người thật.
    """

    def __init__(self, trajectories_dir: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.traj_dir = trajectories_dir or os.path.join(base_dir, "data", "demonstrations", "trajectories")
        self.demonstrated_angles: List[float] = []
        self.load_demonstrations()

    def load_demonstrations(self):
        """Tải toàn bộ file JSON quỹ đạo đã trích xuất."""
        if not os.path.exists(self.traj_dir):
            return

        for fname in os.listdir(self.traj_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.traj_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for item in data:
                            ang = item.get("angle_deg")
                            if ang is not None:
                                self.demonstrated_angles.append(float(ang))
                except Exception as e:
                    print(f"[BehaviorPrior] Lỗi đọc {fname}: {e}")

        if self.demonstrated_angles:
            print(f"[BehaviorPrior] 🧠 Đã nạp {len(self.demonstrated_angles)} mẫu hành vi người chơi.")

    def get_demonstration_score(self, candidate_angle: float, last_angle: Optional[float] = None,
                                enemy_dist: Optional[float] = None) -> float:
        """
        Tính điểm mức độ phù hợp với hành vi người chơi [0, 100].
        - Ưu tiên góc di chuyển tạo quỹ đạo cong mượt mà (chênh lệch với last_angle khoảng 30° - 60°).
        - Trừ điểm nếu bị đổi hướng giật cục 180° (đâm sầm ngược lại) trừ khi khẩn cấp.
        """
        score = 60.0  # Điểm cơ sở

        if last_angle is not None:
            # Độ lệch góc giữa hướng trước và hướng ứng viên
            diff = abs(candidate_angle - last_angle)
            if diff > 180.0:
                diff = 360.0 - diff

            # Người chơi thật thường lướt vòng cung (chênh lệch 30° - 70° giữa các nhịp)
            if 25.0 <= diff <= 75.0:
                score += 30.0  # Thưởng cho chuyển động vòng cung mượt
            elif diff <= 25.0:
                score += 20.0  # Giữ tiếp hướng cũ
            elif diff > 135.0:
                score -= 35.0  # Phạt đổi hướng 180 độ đột ngột

        # Nếu có quái ở cự ly kiting lý tưởng (350 - 550px), người chơi thường duy trì hướng tiếp tuyến
        if enemy_dist is not None:
            if 350.0 <= enemy_dist <= 550.0:
                score += 10.0

        return max(0.0, min(100.0, score))

