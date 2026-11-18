# -*- coding: utf-8 -*-
"""
tests/test_p5_decision.py
Kiểm thử 3 tầng phân cấp quyết định: Safety Rules -> Tactical -> Adaptive Scoring.
"""

import os
import sys

base_dir = os.path.dirname(os.path.dirname(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.common_types import Entity, WorldState
from core.decision.decision_engine import DecisionEngine

def test_decision():
    print("=" * 60)
    print("TEST P5: HYBRID DECISION ENGINE")
    print("=" * 60)

    de = DecisionEngine(hp_critical_percent=35.0)

    # 1. Thử nghiệm Cấp 1: Safety Rules - Hồi máu khẩn cấp khi HP < 35%
    w_heal = WorldState(player_hp=25.0)
    cmd_heal = de.decide(w_heal, [])
    print(f"1. HP tụt thấp (25%): Lệnh ra = {cmd_heal.action_type} ({cmd_heal.reason})")
    assert cmd_heal.action_type == "HEAL"

    # 2. Thử nghiệm Cấp 1: Safety Rules - Thoát hiểm khi quái áp sát (< 160px)
    w_danger = WorldState(
        player_pos=(500, 500),
        player_hp=100.0,
        nearest_enemy=Entity(id=1, category='enemy', center_x=520, center_y=510),
        nearest_enemy_dist=22.3
    )
    cmd_escape = de.decide(w_danger, [])
    print(f"2. Quái áp sát quá gần: Lệnh ra = {cmd_escape.action_type} góc {cmd_escape.angle_degrees:.1f}° ({cmd_escape.reason})")
    assert cmd_escape.action_type == "MOVE"

    # 3. Thử nghiệm Cấp 2: Đạn bị chắn bởi cọc gỗ
    w_blocked = WorldState(
        player_pos=(500, 500),
        player_hp=100.0,
        has_clear_shot=False,
        suggested_escape_angle=270.0
    )
    cmd_los = de.decide(w_blocked, [])
    print(f"3. Bị cọc gỗ cản đường đạn: Lệnh ra = {cmd_los.action_type} góc {cmd_los.angle_degrees}° ({cmd_los.reason})")
    assert cmd_los.action_type == "MOVE" and cmd_los.angle_degrees == 270.0

    # 4. Thử nghiệm Cấp 3: Adaptive Action Scoring
    w_tactical = WorldState(
        player_pos=(960, 540),
        player_hp=100.0,
        nearest_enemy=Entity(id=1, category='enemy', center_x=960, center_y=200),
        nearest_enemy_dist=340.0,
        has_clear_shot=True
    )
    cmd_tactical = de.decide(w_tactical, [])
    print(f"4. Tối ưu hóa di chuyển: Lệnh ra = {cmd_tactical.action_type} góc {cmd_tactical.angle_degrees}° ({cmd_tactical.reason})")
    assert cmd_tactical.action_type == "MOVE"

    print("\n✅ TEST P5 HYBRID DECISION THÀNH CÔNG RỰC RỠ!")
    return True

if __name__ == "__main__":
    test_decision()

