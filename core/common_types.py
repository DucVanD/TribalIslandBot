# -*- coding: utf-8 -*-
"""
core/common_types.py
Chứa toàn bộ các cấu trúc dữ liệu chuẩn (dataclass) dùng chung cho hệ thống TribalIslandBot.
Đảm bảo loosely coupled giữa Perception, World Model, Decision, Action và Memory.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import time


@dataclass
class Entity:
    """Đại diện cho một thực thể trên màn hình (Player, Enemy, Obstacle, Boss, Portal)."""
    id: int
    category: str        # 'player', 'enemy', 'boss', 'obstacle_stump', 'obstacle_wall', 'portal'
    center_x: int
    center_y: int
    radius: int = 40
    confidence: float = 1.0
    hp_percent: float = 100.0
    velocity: Tuple[float, float] = (0.0, 0.0)  # (vx, vy) pixel/giây

    @property
    def pos(self) -> Tuple[int, int]:
        return (self.center_x, self.center_y)


@dataclass
class PerceptionResult:
    """Kết quả phân tích thị giác toàn diện của 1 khung hình."""
    timestamp: float = field(default_factory=time.time)
    frame_id: int = 0
    player: Optional[Entity] = None
    enemies: List[Entity] = field(default_factory=list)
    obstacles: List[Entity] = field(default_factory=list)
    portal: Optional[Entity] = None
    
    # Trạng thái UI
    hp_percent: float = 100.0
    current_floor: int = 1
    is_level_up: bool = False
    is_lobby: bool = False
    is_battle_end: bool = False
    end_btn_coords: Optional[Tuple[int, int]] = None
    overall_confidence: float = 1.0
    shard_count: Optional[int] = None


@dataclass
class WorldState:
    """Trạng thái thế giới game được tổng hợp cho Decision Engine."""
    timestamp: float = field(default_factory=time.time)
    player_pos: Tuple[int, int] = (960, 540)
    player_hp: float = 100.0
    current_floor: int = 1
    game_state: str = "FIGHTING"        # 'LOBBY', 'FIGHTING', 'LEVEL_UP', 'FLOOR_EXIT', 'DEAD'
    
    nearest_enemy: Optional[Entity] = None
    nearest_enemy_dist: float = 9999.0
    enemies_count: int = 0
    
    has_clear_shot: bool = True         # Đường bắn tới quái gần nhất có thông suốt không
    blocking_obstacle: Optional[Entity] = None
    
    is_stuck: bool = False
    stuck_duration: float = 0.0
    suggested_escape_angle: Optional[float] = None

    portal: Optional[Entity] = None
    portal_angle: Optional[float] = None
    portal_dist: Optional[float] = None
    shard_count: Optional[int] = None
    
    confidence: float = 1.0


@dataclass
class SteeringCommand:
    """Lệnh hành động gửi xuống Action Engine."""
    action_type: str = "MOVE"           # 'MOVE', 'ATTACK', 'SKILL', 'HEAL', 'SELECT_PERK', 'HOLD'
    angle_degrees: float = 90.0         # 0=Phải, 90=Lên, 180=Trái, 270=Xuống
    distance_ratio: float = 1.0         # 0.2 -> 1.0 (độ lệch cần gạt)
    duration_ms: int = 400              # Thời gian giữ phím/swipe
    perk_index: int = 1                 # Dùng khi SELECT_PERK (1, 2, 3)
    reason: str = "normal_kiting"       # Lý do ra quyết định (phục vụ log & debug)


@dataclass
class DemonstrationFrame:
    """Khung dữ liệu ghi nhận thị phạm đồng bộ (P2)."""
    frame_id: int
    session_id: int
    timestamp: float
    world_state: WorldState
    action: SteeringCommand
    source: str = "HUMAN"               # 'HUMAN' hoặc 'BOT'
    game_event: Optional[str] = None    # 'NORMAL', 'KILL', 'HIT', 'HEAL', 'PERK'
    screenshot_path: Optional[str] = None


@dataclass
class BehaviorSegment:
    """Đoạn phân tích hành vi chiến thuật (P3)."""
    segment_id: int
    session_id: int
    phase_type: str                     # 'APPROACH', 'COMBAT', 'RETREAT', 'STUCK_RECOVERY'
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    outcome: str = "COMPLETED"          # 'COMPLETED', 'INTERRUPTED', 'DIED'
    quality_score: float = 1.0
    command_sequence: List[SteeringCommand] = field(default_factory=list)


@dataclass
class StrategyCandidate:
    """Chiến lược ứng viên được trích xuất từ dữ liệu thị phạm (P4)."""
    candidate_id: int
    name: str
    source_segment_ids: List[int]
    preconditions: Dict[str, Any]       # Ngưỡng máu tối thiểu, cự ly quái, phase...
    expected_outcome: Dict[str, Any]
    confidence: float = 0.5
    lifecycle_state: str = "OBSERVED"   # 'OBSERVED', 'CANDIDATE', 'VALIDATED', 'DEPRECATED'
    version: int = 1


@dataclass
class ProceduralPattern:
    """Mẫu thao tác thủ tục trong Procedural Memory (P7)."""
    pattern_id: int
    pattern_name: str
    trigger_conditions: Dict[str, Any]
    action_sequence: List[Dict[str, Any]]
    success_rate: float = 0.5
    use_count: int = 0


