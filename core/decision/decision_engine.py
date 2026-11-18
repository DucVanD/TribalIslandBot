# -*- coding: utf-8 -*-
"""
core/decision/decision_engine.py
Phase P6: Hybrid Decision Engine
DecisionEngine là bộ não điều phối hành động 4 tầng phân cấp:
- Cấp 1: Safety Rules (Ưu tiên tuyệt đối)
- Cấp 2: Tactical Re-positioning (Mở góc bắn khi đạn bị chặn bởi cọc gỗ)
- Cấp 3: Demonstration Strategy Replay (Tái sử dụng chiến thuật người mẫu có điều kiện)
- Cấp 4: Adaptive Action Scoring (Tối ưu hóa di chuyển 360 độ bằng hàm chấm điểm 5 thành phần)
"""

from typing import List, Optional, Dict
import time
from core.common_types import WorldState, SteeringCommand, Entity
from core.navigation.vector_steering import VectorSteering
from core.demonstration.conditional_replayer import ConditionalStrategyReplayer
from .safety_rules import SafetyRules
from .combat_knowledge import CombatKnowledge


class DecisionEngine:
    """
    DecisionEngine nhận WorldState và sinh ra duy nhất một SteeringCommand tối ưu nhất.
    Tuân thủ nghiêm ngặt nguyên tắc Single Ownership: Chỉ một tầng sở hữu quyền thực thi tại một thời điểm.
    """

    def __init__(self, hp_critical_percent: float = 35.0,
                 replayer: Optional[ConditionalStrategyReplayer] = None):
        self.safety_rules = SafetyRules(hp_critical_percent=hp_critical_percent)
        self.steering = VectorSteering()
        self.replayer = replayer or ConditionalStrategyReplayer()
        self.combat_knowledge = CombatKnowledge()
        self.kiting_step = 0
        self.portal_search_started = time.monotonic()
        self.portal_search_angles = (90.0, 135.0, 180.0, 225.0, 270.0, 315.0, 0.0, 45.0)

    def reset_portal_search(self):
        """Start portal-search timing afresh after leaving a floor entrance."""
        self.portal_search_started = time.monotonic()
        self.steering.last_chosen_angle = None

    def set_scoring_weights(self, w_s: float, w_d: float, w_l: float, w_m: float, w_demo: float = 0.15):
        """Cập nhật trọng số từ Persistent Memory & Demonstration Prior."""
        self.steering.set_weights(w_s, w_d, w_l, w_m, w_demo=w_demo)

    def decide(self, world: WorldState, obstacles: List[Entity],
               memory_bias: Optional[Dict[float, float]] = None) -> SteeringCommand:
        """
        Quyết định hành động dựa trên 4 tầng phân cấp từ trên xuống dưới.
        """
        # 0. Trạng thái giao diện đặc biệt
        if world.game_state == "LEVEL_UP":
            return SteeringCommand(action_type="SELECT_PERK", perk_index=1, reason="level_up_perk")

        if world.game_state == "LOBBY":
            return SteeringCommand(action_type="HOLD", reason="lobby_idle")

        if world.game_state == "BATTLE_END":
            return SteeringCommand(action_type="HOLD", reason="battle_end_idle")

        # 1. CẤP 1: Safety Rules (Ưu tiên tuyệt đối)
        safety_cmd = self.safety_rules.evaluate(world)
        if safety_cmd is not None:
            # Ngắt ngay chuỗi replay nếu Safety Rules can thiệp
            if self.replayer.active_segment is not None:
                self.replayer.stop_replay()
            return safety_cmd

        # 2. CẤP 2: Tactical Line of Sight (Đạn bị cản bởi cọc gỗ)
        if not world.has_clear_shot and world.suggested_escape_angle is not None:
            if self.replayer.active_segment is not None:
                self.replayer.stop_replay()
            return SteeringCommand(
                action_type="MOVE",
                angle_degrees=world.suggested_escape_angle,
                distance_ratio=0.9,
                duration_ms=450,
                reason="blocked_los_reposition"
            )

        # 2.5 CẤP 2.5: Tri thức thực chiến Level 4 (Tactical Burst khi quái yếu máu)
        if world.nearest_enemy is not None:
            stance = self.combat_knowledge.evaluate_combat_stance(
                enemy_dist=world.nearest_enemy_dist,
                enemy_hp_percent=world.nearest_enemy.hp_percent,
                player_hp_percent=world.player_hp
            )
            if stance == "BURST":
                return SteeringCommand(
                    action_type="ATTACK",
                    duration_ms=250,
                    reason="tactical_burst_finish_off"
                )

        # 3. CẤP 3: Demonstration Strategy Replay (Nếu đang có replay tích cực và an toàn)
        replay_cmd = self.replayer.get_next_command(world)
        if replay_cmd is not None:
            return replay_cmd

        # 4. Khi đã dọn sạch quái trong phòng: Di chuyển vào Cổng dịch chuyển
        if world.enemies_count == 0:
            if world.portal_angle is not None and world.portal_dist is not None:
                self.portal_search_started = time.monotonic()
                # Nếu đã tiếp cận rất sát cổng (< 80px), thực hiện bước sải chân dứt khoát xuyên qua cổng
                if world.portal_dist < 80.0:
                    return SteeringCommand(
                        action_type="MOVE",
                        angle_degrees=world.portal_angle,
                        distance_ratio=1.0,
                        duration_ms=1100,
                        reason="enter_portal_cross_threshold"
                    )
                # Bẻ lái di chuyển chính xác theo góc thực tế hướng về tâm cổng (tránh bị lệch khi camera trôi)
                return SteeringCommand(
                    action_type="MOVE",
                    angle_degrees=world.portal_angle,
                    distance_ratio=1.0,
                    duration_ms=1100,
                    reason=f"move_to_portal_targeted_{world.portal_angle:.0f}"
                )
            else:
                if world.current_floor >= 5 and world.current_floor % 10 == 5:
                    # Empty milestone floors are route-finding tasks. Use the
                    # obstacle-aware north-progress scorer instead of cycling
                    # through a compass sweep that can send the player backward.
                    angle, score = self.steering.find_route_angle(world, obstacles)
                    return SteeringCommand(
                        action_type="MOVE",
                        angle_degrees=angle,
                        distance_ratio=1.0,
                        duration_ms=1100,
                        reason=f"route_floor_exploration_{score:.1f}",
                    )
                # Sweep the room instead of driving into one wall forever.
                elapsed = max(0.0, time.monotonic() - self.portal_search_started)
                # Hold each exploratory heading long enough to make spatial
                # progress instead of circling through all directions quickly.
                index = int(elapsed / 4.8) % len(self.portal_search_angles)
                return SteeringCommand(
                    action_type="MOVE",
                    angle_degrees=self.portal_search_angles[index],
                    distance_ratio=1.0,
                    duration_ms=1400,
                    reason=f"portal_search_sweep_{self.portal_search_angles[index]:.0f}"
                )

        # 5. CẤP 4: Adaptive Action Scoring (Tối ưu góc di chuyển 360 độ kiting khi giao tranh)
        best_angle, score = self.steering.find_best_angle(world, obstacles, memory_bias=memory_bias)
        
        return SteeringCommand(
            action_type="MOVE",
            angle_degrees=best_angle,
            distance_ratio=1.0,
            duration_ms=450,
            reason=f"adaptive_scoring_{score:.1f}"
        )
