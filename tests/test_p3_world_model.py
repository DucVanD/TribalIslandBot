# -*- coding: utf-8 -*-
"""
tests/test_p3_world_model.py
Kiểm thử độc lập World Model và thuật toán phát hiện đạn bị chắn cọc gỗ (Blocked LOS).
"""

import os
import sys

base_dir = os.path.dirname(os.path.dirname(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.common_types import Entity, PerceptionResult
from core.world.world_model import WorldModel

def test_world_model():
    print("=" * 60)
    print("TEST P3: WORLD MODEL & LINE OF SIGHT")
    print("=" * 60)

    wm = WorldModel()

    # Tình huống: Người chơi ở (523, 243), Quái ở (100, 215), Cọc gỗ ở (347, 208) chắn giữa
    player = Entity(id=0, category='player', center_x=523, center_y=243)
    enemy = Entity(id=1, category='enemy', center_x=100, center_y=215)
    obstacle = Entity(id=2, category='obstacle_stump', center_x=347, center_y=208, radius=40)

    p_res = PerceptionResult(player=player, enemies=[enemy], obstacles=[obstacle])
    world = wm.update(p_res)

    print("1. Kiểm tra phát hiện đạn bị cản (Blocked LOS):")
    print(f"   - has_clear_shot: {world.has_clear_shot} (Kỳ vọng: False)")
    print(f"   - Khoảng cách quái gần nhất: {world.nearest_enemy_dist:.1f}px")
    print(f"   - Vật cản gây chặn: {world.blocking_obstacle.category if world.blocking_obstacle else None}")
    print(f"   - Góc thoát hiểm gợi ý: {world.suggested_escape_angle:.1f}°")

    assert world.has_clear_shot is False, "LOS detection failed! Should be blocked."
    assert world.blocking_obstacle is not None, "Blocking obstacle should be identified."

    # Tình huống 2: Đã né khỏi cọc gỗ, đường đạn thông thoáng
    p_res_clear = PerceptionResult(player=player, enemies=[enemy], obstacles=[])
    world_clear = wm.update(p_res_clear)
    print("\n2. Kiểm tra đường đạn thông thoáng (Clear LOS):")
    print(f"   - has_clear_shot: {world_clear.has_clear_shot} (Kỳ vọng: True)")

    assert world_clear.has_clear_shot is True, "LOS should be clear."
    print("\n✅ TEST P3 WORLD MODEL THÀNH CÔNG RỰC RỠ!")
    return True

if __name__ == "__main__":
    test_world_model()

