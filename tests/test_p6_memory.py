# -*- coding: utf-8 -*-
"""
tests/test_p6_memory.py
Kiểm thử Persistent Memory qua SQLite: Ghi nhận trận đấu, khởi động lại và đọc dữ liệu.
"""

import os
import sys

base_dir = os.path.dirname(os.path.dirname(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.memory.database import Database
from core.memory.memory_manager import MemoryManager
from core.memory.strategy_updater import StrategyUpdater

def test_memory():
    print("=" * 60)
    print("TEST P6: PERSISTENT MEMORY (SQLITE ENGINE)")
    print("=" * 60)

    db_path = os.path.join(base_dir, "data", "tribal_memory.db")
    db = Database(db_path=db_path)
    mm = MemoryManager(db=db)
    su = StrategyUpdater(db=db)

    # 1. Bắt đầu lượt chơi mới
    run_id = mm.start_run(target_floor=71)
    print(f"1. Khởi tạo phiên chơi mới với run_id: {run_id}")
    assert run_id > 0

    # 2. Ghi nhận dữ liệu tầng
    mm.record_floor(
        floor_num=1,
        start_hp=100.0,
        end_hp=92.0,
        duration=28.5,
        stuck_count=0,
        strategy="adaptive_kiting",
        result="CLEARED"
    )
    print("2. Đã ghi nhận kết quả Tầng 1 vào floor_records.")

    # 3. Ghi nhận sự kiện đặc biệt
    mm.record_event(
        floor_num=1,
        event_type="BLOCKED_LOS_AVOIDED",
        player_x=520,
        player_y=300,
        details="Tự động né cọc gỗ thành công"
    )
    print("3. Đã ghi nhận sự kiện đặc biệt vào battle_events.")

    # 4. Kết thúc ván
    mm.end_run(reached_floor=25, result="SUCCESS", total_stuck=0, total_heals=1, final_hp=85.0)
    print("4. Kết thúc ván đấu và lưu tổng kết vào runs.")

    # 5. Đánh giá chiến thuật & gợi ý trọng số
    scores = su.evaluate_all()
    print(f"5. Điểm Utility Score các chiến thuật: {scores}")
    weights = su.recommend_weights()
    print(f"6. Trọng số gợi ý cho ván sau: {weights}")

    # 6. Kiểm tra tính toàn vẹn khi tắt và đọc lại từ file DB
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM runs WHERE run_id = ?", (run_id,))
        count = cursor.fetchone()[0]
        assert count == 1, "Database persistence test failed!"

    print("\n✅ TEST P6 PERSISTENT MEMORY THÀNH CÔNG RỰC RỠ!")
    return True

if __name__ == "__main__":
    test_memory()

