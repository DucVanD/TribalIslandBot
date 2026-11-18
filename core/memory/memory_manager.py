# -*- coding: utf-8 -*-
"""
core/memory/memory_manager.py
MemoryManager quản lý 3 tầng bộ nhớ:
- Working Memory (phiên hiện tại)
- Episodic Memory (lưu sự kiện, run, floor vào SQLite)
- Semantic Memory (kinh nghiệm tổng hợp, trọng số chiến thuật)
"""

import time
from typing import Optional, Tuple, Dict, Any, List

from .database import Database


class MemoryManager:
    """
    MemoryManager: Cổng giao tiếp chính giữa bot và cơ sở dữ liệu kinh nghiệm lâu dài.
    """

    BASELINE_WEIGHTS = (0.35, 0.25, 0.25, 0.15)  # (w_s, w_d, w_l, w_m)

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.active_run_id: Optional[int] = None
        self.run_start_time: float = time.time()
        self.current_weights = list(self.BASELINE_WEIGHTS)

    def start_run(self, target_floor: int = 71) -> int:
        """Bắt đầu một lượt chơi mới và lưu vào bảng runs."""
        self.run_start_time = time.time()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO runs (target_floor, result)
            VALUES (?, 'RUNNING')
            """, (target_floor,))
            conn.commit()
            self.active_run_id = cursor.lastrowid
            return self.active_run_id

    def end_run(self, reached_floor: int, result: str = "SUCCESS",
                total_stuck: int = 0, total_heals: int = 0, final_hp: float = 100.0):
        """Kết thúc lượt chơi và cập nhật tổng kết."""
        if self.active_run_id is None:
            return

        duration = time.time() - self.run_start_time
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE runs
            SET end_time = CURRENT_TIMESTAMP,
                reached_floor = ?,
                duration_seconds = ?,
                result = ?,
                total_stuck_count = ?,
                total_heals_used = ?,
                final_hp_percent = ?
            WHERE run_id = ?
            """, (reached_floor, duration, result, total_stuck, total_heals, final_hp, self.active_run_id))
            conn.commit()

        self.active_run_id = None

    def record_floor(self, floor_num: int, start_hp: float, end_hp: float,
                     duration: float, stuck_count: int, strategy: str, result: str):
        """Ghi nhận chi tiết kết quả của từng tầng."""
        if self.active_run_id is None:
            return

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO floor_records (run_id, floor_number, start_hp_percent, end_hp_percent,
                                       duration_seconds, stuck_count, primary_strategy, result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (self.active_run_id, floor_num, start_hp, end_hp, duration, stuck_count, strategy, result))
            conn.commit()

    def record_event(self, floor_num: int, event_type: str,
                     player_x: int, player_y: int, details: str = ""):
        """Ghi nhận sự kiện đặc biệt (kẹt, mất máu lớn, chết)."""
        if self.active_run_id is None:
            return

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO battle_events (run_id, floor_number, event_type, player_x, player_y, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (self.active_run_id, floor_num, event_type, player_x, player_y, details))
            conn.commit()

    def get_strategy_weights(self) -> Tuple[float, float, float, float]:
        """Lấy bộ trọng số quyết định hiện tại (w_s, w_d, w_l, w_m)."""
        return tuple(self.current_weights)

    def update_weights(self, w_s: float, w_d: float, w_l: float, w_m: float):
        """Cập nhật bộ trọng số mới với cơ chế an toàn."""
        # Giới hạn trong khoảng an toàn
        self.current_weights = [
            max(0.20, min(0.60, w_s)),
            max(0.15, min(0.40, w_d)),
            max(0.15, min(0.40, w_l)),
            max(0.05, min(0.30, w_m))
        ]

    def rollback_to_baseline(self):
        """Khôi phục toàn bộ trọng số về cấu hình chuẩn an toàn (Baseline)."""
        self.current_weights = list(self.BASELINE_WEIGHTS)
        print("[MemoryManager] ⚠️ Đã tự động kích hoạt ROLLBACK về trọng số an toàn Baseline!")

    # 4. Tầng Procedural Memory (P7: Mẫu thao tác chiến thuật)
    def save_procedural_pattern(self, name: str, trigger_conditions: Dict[str, Any],
                                action_sequence: List[Dict[str, Any]]) -> bool:
        """Lưu hoặc cập nhật mẫu thao tác thủ tục."""
        import json
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO procedural_patterns (pattern_name, trigger_conditions_json, action_sequence_json, last_used)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(pattern_name) DO UPDATE SET
                trigger_conditions_json = excluded.trigger_conditions_json,
                action_sequence_json = excluded.action_sequence_json,
                use_count = use_count + 1,
                last_used = CURRENT_TIMESTAMP
            """, (name, json.dumps(trigger_conditions), json.dumps(action_sequence)))
            conn.commit()
            return True

    def get_procedural_pattern(self, name: str) -> Optional[Dict[str, Any]]:
        """Lấy một mẫu thao tác thủ tục theo tên."""
        import json
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM procedural_patterns WHERE pattern_name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return {
                    "pattern_id": row["pattern_id"],
                    "pattern_name": row["pattern_name"],
                    "trigger_conditions": json.loads(row["trigger_conditions_json"]),
                    "action_sequence": json.loads(row["action_sequence_json"]),
                    "success_rate": row["success_rate"],
                    "use_count": row["use_count"]
                }
        return None

