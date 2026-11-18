# -*- coding: utf-8 -*-
"""
core/demonstration/conditional_replayer.py
Phase P4: Conditional Strategy Replay
Tái sử dụng chiến thuật mẫu của người chơi có điều kiện:
- Kiểm tra điều kiện tiên quyết (Preconditions Check)
- Giám sát điều kiện hủy bỏ khẩn cấp (Abort Conditions)
- Thực thi chuỗi lệnh SteeringCommand mượt mà
- Nhường quyền ngay lập tức cho Safety Rules khi gặp nguy hiểm
"""

import time
from typing import Optional, List, Dict, Any, Tuple

from core.common_types import WorldState, SteeringCommand, BehaviorSegment, StrategyCandidate


class ConditionalStrategyReplayer:
    """
    ConditionalStrategyReplayer:
    Bộ điều khiển phát lại chiến lược thị phạm có bảo vệ an toàn chủ động.
    """

    def __init__(self, min_confidence: float = 0.70, min_hp_threshold: float = 50.0):
        self.min_confidence = min_confidence
        self.min_hp_threshold = min_hp_threshold

        self.active_segment: Optional[BehaviorSegment] = None
        self.replay_index: int = 0
        self.replay_start_time: float = 0.0
        self.replay_start_hp: float = 100.0

    def check_preconditions(self, world: WorldState, segment: Optional[BehaviorSegment] = None) -> bool:
        """
        Kiểm tra xem điều kiện hiện tại có an toàn và phù hợp để kích hoạt replay không.
        """
        # 1. Độ tin cậy thị giác phải đủ cao
        if world.confidence < self.min_confidence:
            return False

        # 2. HP phải ở mức an toàn
        if world.player_hp < self.min_hp_threshold:
            return False

        # 3. Không được đang trong tình trạng kẹt
        if world.is_stuck:
            return False

        # 4. Quái vật không được quá gần (< 200px)
        if world.nearest_enemy and world.nearest_enemy_dist < 200.0:
            return False

        # 5. Phải đang trong trạng thái giao chiến bình thường
        if world.game_state != "FIGHTING":
            return False

        return True

    def start_replay(self, segment: BehaviorSegment, world: WorldState) -> bool:
        """
        Bắt đầu một chuỗi replay từ BehaviorSegment.
        """
        if not self.check_preconditions(world, segment):
            return False

        if not segment.command_sequence:
            return False

        self.active_segment = segment
        self.replay_index = 0
        self.replay_start_time = time.time()
        self.replay_start_hp = world.player_hp
        return True

    def check_abort_conditions(self, world: WorldState) -> Tuple[bool, str]:
        """
        Kiểm tra xem có cần hủy bỏ (abort) chuỗi replay ngay lập tức không.
        Trả về: (should_abort, reason)
        """
        if self.active_segment is None:
            return False, "no_active_replay"

        # 1. Hủy nếu máu tụt quá 15% trong lúc replay
        if (self.replay_start_hp - world.player_hp) > 15.0:
            return True, "hp_dropped_over_15_percent"

        # 2. Hủy nếu bị kẹt
        if world.is_stuck:
            return True, "character_stuck_during_replay"

        # 3. Hủy nếu quái áp sát nguy hiểm
        if world.nearest_enemy and world.nearest_enemy_dist < 160.0:
            return True, "enemy_too_close_during_replay"

        # 4. Hủy nếu mất độ tin cậy thị giác
        if world.confidence < 0.40:
            return True, "low_confidence_during_replay"

        # 5. Hủy nếu game đổi trạng thái (Lên cấp, về sảnh, chết)
        if world.game_state != "FIGHTING":
            return True, f"game_state_changed_to_{world.game_state}"

        return False, "ok"

    def get_next_command(self, world: WorldState) -> Optional[SteeringCommand]:
        """
        Lấy lệnh tiếp theo trong chuỗi replay nếu điều kiện an toàn được đảm bảo.
        """
        if self.active_segment is None:
            return None

        # Kiểm tra điều kiện ngắt khẩn cấp
        should_abort, reason = self.check_abort_conditions(world)
        if should_abort:
            self.stop_replay()
            return None

        # Lấy lệnh tại bước hiện tại
        if self.replay_index < len(self.active_segment.command_sequence):
            cmd = self.active_segment.command_sequence[self.replay_index]
            self.replay_index += 1
            # Gắn nhãn reason phục vụ log
            cmd.reason = f"demo_replay_seg{self.active_segment.segment_id}_step{self.replay_index}"
            return cmd
        else:
            # Hoàn tất chuỗi replay
            self.stop_replay()
            return None

    def stop_replay(self):
        """Dừng replay và reset trạng thái."""
        self.active_segment = None
        self.replay_index = 0
