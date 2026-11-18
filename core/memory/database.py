# -*- coding: utf-8 -*-
"""
core/memory/database.py
Quản lý kết nối và khởi tạo cơ sở dữ liệu SQLite cho TribalIslandBot.
Database file: data/tribal_memory.db
"""

import sqlite3
import os
import threading
from typing import Optional, Iterator
from contextlib import contextmanager


class Database:
    """
    Database:
    Quản lý SQLite thread-safe cho hệ thống lưu trữ kinh nghiệm của bot.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            data_dir = os.path.join(base_dir, "data")
            self.db_path = os.path.join(data_dir, "tribal_memory.db")
        else:
            self.db_path = db_path

        parent_dir = os.path.dirname(self.db_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        self._lock = threading.Lock()
        self.init_tables()

    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a thread-local SQLite connection and always close it on exit."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
        except Exception:
            pass
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init_tables(self):
        """Khởi tạo toàn bộ cấu trúc bảng theo chuẩn kiến trúc."""
        with self._lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # 1. Bảng runs: Lịch sử mỗi lượt chạy
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    target_floor INTEGER DEFAULT 71,
                    reached_floor INTEGER DEFAULT 1,
                    duration_seconds REAL DEFAULT 0.0,
                    result TEXT,
                    total_stuck_count INTEGER DEFAULT 0,
                    total_heals_used INTEGER DEFAULT 0,
                    final_hp_percent REAL DEFAULT 0.0
                );
                """)

                # 2. Bảng floor_records: Chi tiết từng tầng
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS floor_records (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    floor_number INTEGER,
                    start_hp_percent REAL,
                    end_hp_percent REAL,
                    duration_seconds REAL,
                    stuck_count INTEGER DEFAULT 0,
                    primary_strategy TEXT,
                    result TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
                """)

                # 3. Bảng battle_events: Sự kiện quan trọng (kẹt, mất máu, chết)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS battle_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    floor_number INTEGER,
                    event_type TEXT,
                    player_x INTEGER,
                    player_y INTEGER,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
                """)

                # 4. Bảng strategy_stats: Thống kê hiệu quả chiến thuật
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_stats (
                    strategy_name TEXT PRIMARY KEY,
                    total_uses INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    avg_hp_remaining REAL DEFAULT 0.0,
                    avg_duration_sec REAL DEFAULT 0.0,
                    utility_score REAL DEFAULT 0.0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # 5. Khởi tạo giá trị mặc định cho 3 chiến thuật chính nếu chưa có
                cursor.execute("SELECT COUNT(*) FROM strategy_stats")
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                    INSERT INTO strategy_stats (strategy_name, total_uses, success_count, avg_hp_remaining, avg_duration_sec, utility_score)
                    VALUES 
                        ('circular_kiting', 0, 0, 50.0, 50.0, 0.50),
                        ('adaptive_kiting', 0, 0, 60.0, 45.0, 0.60),
                        ('safe_distance', 0, 0, 70.0, 60.0, 0.55);
                    """)

                # 6. Bảng demonstration_sessions (P2)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS demonstration_sessions (
                    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    source_type TEXT CHECK(source_type IN ('HUMAN', 'BOT')) DEFAULT 'HUMAN',
                    total_frames INTEGER DEFAULT 0,
                    quality_score REAL DEFAULT 1.0,
                    target_floor INTEGER DEFAULT 71
                );
                """)

                # 7. Bảng demonstration_frames (P2)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS demonstration_frames (
                    frame_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    timestamp REAL,
                    player_x INTEGER,
                    player_y INTEGER,
                    player_hp REAL,
                    action_type TEXT,
                    action_angle REAL,
                    game_state TEXT,
                    nearest_enemy_dist REAL,
                    enemies_count INTEGER,
                    screenshot_path TEXT,
                    FOREIGN KEY(session_id) REFERENCES demonstration_sessions(session_id)
                );
                """)

                # 8. Bảng behavior_segments (P3)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS behavior_segments (
                    segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    phase_type TEXT CHECK(phase_type IN ('APPROACH', 'COMBAT', 'RETREAT', 'STUCK_RECOVERY')),
                    start_frame INTEGER,
                    end_frame INTEGER,
                    duration_sec REAL,
                    outcome TEXT,
                    quality_score REAL DEFAULT 1.0,
                    FOREIGN KEY(session_id) REFERENCES demonstration_sessions(session_id)
                );
                """)

                # 9. Bảng strategy_candidates (P4)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_candidates (
                    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    source_segment_ids TEXT,
                    preconditions_json TEXT,
                    expected_outcome_json TEXT,
                    confidence REAL DEFAULT 0.5,
                    lifecycle_state TEXT CHECK(lifecycle_state IN ('OBSERVED', 'CANDIDATE', 'VALIDATED', 'DEPRECATED')) DEFAULT 'OBSERVED',
                    version INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    validated_at TIMESTAMP
                );
                """)

                # 10. Bảng procedural_patterns (P7: Procedural Memory)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS procedural_patterns (
                    pattern_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_name TEXT UNIQUE,
                    trigger_conditions_json TEXT,
                    action_sequence_json TEXT,
                    success_rate REAL DEFAULT 0.5,
                    use_count INTEGER DEFAULT 0,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # 11. Bảng schema_migrations (P7: Database Versioning)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version INTEGER UNIQUE,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                );
                """)

                # Ghi nhận migration version 1 nếu chưa có
                cursor.execute("INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (1, 'Initial Unified P1-P8 Schema');")

                # Indexes để tăng tốc độ truy vấn
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_floor_records_run_id ON floor_records(run_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_battle_events_run_id ON battle_events(run_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_demo_frames_session ON demonstration_frames(session_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_segments_session ON behavior_segments(session_id);")

                # Learning data is deliberately additive so existing memory DBs migrate in place.
                cursor.execute("PRAGMA table_info(demonstration_frames)")
                frame_columns = {row[1] for row in cursor.fetchall()}
                for column, definition in {
                    "action_duration_ms": "INTEGER DEFAULT 200",
                    "input_keys_json": "TEXT DEFAULT '[]'",
                    "confidence": "REAL DEFAULT 1.0",
                    "training_eligible": "INTEGER DEFAULT 1",
                }.items():
                    if column not in frame_columns:
                        cursor.execute(f"ALTER TABLE demonstration_frames ADD COLUMN {column} {definition}")

                cursor.execute("""
                CREATE TABLE IF NOT EXISTS learning_examples (
                    example_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    session_id INTEGER,
                    source TEXT NOT NULL,
                    context_key TEXT NOT NULL,
                    action_key TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    action_json TEXT NOT NULL,
                    reward REAL,
                    eligible INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_context_action ON learning_examples(context_key, action_key, eligible)")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS learning_policies (
                    policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version INTEGER NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'CANDIDATE', 'REJECTED', 'ARCHIVED')),
                    policy_json TEXT NOT NULL,
                    promoted_at TIMESTAMP,
                    promoted_after_eval_id INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("PRAGMA table_info(learning_policies)")
                policy_columns = {row[1] for row in cursor.fetchall()}
                if "promoted_at" not in policy_columns:
                    cursor.execute("ALTER TABLE learning_policies ADD COLUMN promoted_at TIMESTAMP")
                if "promoted_after_eval_id" not in policy_columns:
                    cursor.execute("ALTER TABLE learning_policies ADD COLUMN promoted_after_eval_id INTEGER DEFAULT 0")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS policy_evaluations (
                    evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_id INTEGER NOT NULL,
                    run_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('BASELINE', 'CANDIDATE')),
                    score REAL NOT NULL,
                    safety_events INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(policy_id, run_id)
                )
                """)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS policy_shadow_observations (
                    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_id INTEGER NOT NULL,
                    run_id INTEGER NOT NULL,
                    context_key TEXT NOT NULL,
                    action_key TEXT NOT NULL,
                    score REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS demonstration_sync_reports (
                    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    video_path TEXT NOT NULL,
                    log_path TEXT,
                    video_duration_sec REAL NOT NULL,
                    log_duration_sec REAL,
                    time_offset_sec REAL,
                    sampled_frames INTEGER NOT NULL,
                    tracked_frames INTEGER NOT NULL,
                    mapped_input_fraction REAL NOT NULL,
                    quality_score REAL NOT NULL,
                    training_eligible INTEGER NOT NULL,
                    issues_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)

                cursor.execute("SELECT COUNT(*) FROM learning_policies WHERE status = 'ACTIVE'")
                if cursor.fetchone()[0] == 0:
                    cursor.execute(
                        "INSERT OR IGNORE INTO learning_policies (version, status, policy_json) VALUES (1, 'ACTIVE', '{}')"
                    )

                conn.commit()
