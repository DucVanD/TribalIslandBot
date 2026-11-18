# -*- coding: utf-8 -*-
"""
tests/test_p4_navigation.py
Kiểm thử độc lập Vector Steering và Stuck Detector.
"""

import os
import sys

base_dir = os.path.dirname(os.path.dirname(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.common_types import Entity, WorldState
from core.navigation.vector_steering import VectorSteering
from core.navigation.stuck_detector import StuckDetector

def test_navigation():
    print("=" * 60)
    print("TEST P4: ADAPTIVE NAVIGATION & VECTOR STEERING")
    print("=" * 60)

    steering = VectorSteering()
    
    # Người chơi ở giữa phòng (960, 540), quái ở phía trên (960, 250)
    player_pos = (960, 540)
    nearest_enemy = Entity(id=1, category='enemy', center_x=960, center_y=250)
    world = WorldState(
        player_pos=player_pos,
        nearest_enemy=nearest_enemy,
        nearest_enemy_dist=290.0,
        has_clear_shot=True
    )

    best_angle, score = steering.find_best_angle(world, obstacles=[])
    print(f"1. Góc di chuyển tối ưu: {best_angle}° với điểm số Score: {score:.1f}")
    assert 0.0 <= best_angle <= 360.0

    # Kiểm tra StuckDetector
    sd = StuckDetector(stuck_threshold_seconds=0.1, min_move_distance=20.0)
    sd.update((500, 500))
    import time; time.sleep(0.15)
    is_stuck, dur = sd.update((502, 501))
    print(f"2. Kiểm tra phát hiện kẹt: is_stuck={is_stuck}, duration={dur:.2f}s")
    assert is_stuck is True, "Stuck detector failed to trigger!"

    print("\n✅ TEST P4 NAVIGATION THÀNH CÔNG RỰC RỠ!")
    return True

if __name__ == "__main__":
    test_navigation()

