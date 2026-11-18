# -*- coding: utf-8 -*-
"""
core/decision/combat_knowledge.py
Tích hợp tri thức thực chiến và công thức sát thương dịch ngược từ nsbl.
Kết hợp mô phỏng sát thương native (DamageEngine) và thông số kỹ năng gốc.
"""

import os
import sys
from typing import Optional, Tuple

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
nsbl_tools = os.path.join(base_dir, "nsbl", "tools")
if nsbl_tools not in sys.path:
    sys.path.insert(0, nsbl_tools)

try:
    from damage_engine import DamageEngine
except ImportError:
    DamageEngine = None


class CombatKnowledge:
    """
    CombatKnowledge:
    Cung cấp thông số vật lý và toán học chuẩn xác từ mã nguồn gốc game:
    - Sát thương, chí mạng, giáp qua DamageEngine
    - Phân loại chiến thuật: KITE vs BURST dựa trên Time-to-Kill (TTK)
    - Cấu hình nút chuẩn từ config.skill.functionreleasebuttonoperation.txt
    """

    # Danh mục ID nút bấm thao tác gốc từ config.skill
    BUTTON_ATTACK_ID = 10078
    BUTTON_SKILL_HERO_ID = 20078
    BUTTON_SKILL_ACTIVE_ID = 30078
    BUTTON_ITEM_HEAL_ID = 40078
    JOYSTICK_ROCKER_ID = 50078

    # Thông số động lực học nhân vật (từ heroconfig.txt)
    HERO_BASE_SPEED = 200.0        # units / giây
    HERO_OPTIMAL_KITE_DIST = 450.0 # pixels trên màn 1920x1080
    HERO_MELEE_DANGER_DIST = 160.0 # cự ly quái cận chiến gây nguy hiểm

    def __init__(self):
        self.damage_engine = DamageEngine() if DamageEngine else None

    def calculate_dps(self, base_attack: float = 240.0, target_defense: float = 76.0,
                      crit_rate: float = 15.0, crit_mult: float = 150.0) -> float:
        """
        Tính toán DPS trung bình dựa trên công thức toán native của libcocos2dcpp.so.
        """
        if self.damage_engine:
            dmg, is_crit = self.damage_engine.calculate_damage(
                p1_base_atk=base_attack,
                p2_target_def=target_defense,
                p3_crit_rate=crit_rate,
                p4_armor_pen=0.0,
                p5_crit_dmg=crit_mult,
                p6_dmg_res=0.0,
                crit_override=False
            )
            # Nhịp bắn chuẩn: ~2 phát / giây
            return float(dmg * 2.0)
        else:
            # Fallback tính toán xấp xỉ
            net_dmg = max(10.0, base_attack - target_defense * 0.5)
            return net_dmg * 2.0

    def evaluate_combat_stance(self, enemy_dist: float, enemy_hp_percent: float,
                               player_hp_percent: float) -> str:
        """
        Đánh giá tư thế chiến đấu thông minh (Level 4):
        - 'BURST': Quái gần chết (HP < 20%) và an toàn -> Đứng yên xả đạn dứt điểm ngay lập tức.
        - 'EMERGENCY_ESCAPE': Quái áp sát dưới 160px -> Thoát hiểm ngay.
        - 'KITE': Duy trì khoảng cách lý tưởng (450px) vừa di chuyển vừa bắn.
        """
        if enemy_dist < self.HERO_MELEE_DANGER_DIST:
            return "EMERGENCY_ESCAPE"

        # Nếu quái gần chết (dưới 20% máu) và máu bản thân an toàn (> 40%):
        # Không cần chạy vòng vo tốn thời gian, xả đạn dứt điểm luôn!
        if enemy_hp_percent < 20.0 and player_hp_percent > 40.0 and enemy_dist < 550.0:
            return "BURST"

        return "KITE"

