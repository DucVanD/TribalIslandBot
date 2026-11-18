# -*- coding: utf-8 -*-
"""
core/demonstration/demonstration_recorder.py
Phase P2: Demonstration Recorder
Ghi nhận đồng bộ toàn diện phiên chơi:
- Trạng thái thế giới (WorldState)
- Lệnh hành động / thao tác (SteeringCommand)
- Dấu thời gian (Timestamp) & Frame ID
- Nhãn phân biệt dữ liệu: HUMAN vs BOT
- Lưu trữ vào cơ sở dữ liệu SQLite (bảng demonstration_sessions, demonstration_frames)
"""

import os
import time
import cv2
import threading
from typing import Optional, List, Dict, Any

from core.common_types import WorldState, SteeringCommand, DemonstrationFrame
from core.memory.database import Database


class DemonstrationRecorder:
    """
    DemonstrationRecorder:
    Bộ ghi nhận dữ liệu thị phạm đồng bộ, phục vụ trích xuất chiến thuật và huấn luyện phản xạ.
    """

    def __init__(self, db: Optional[Database] = None, save_screenshots: bool = False):
        self.db = db or Database()
        self.save_screenshots = save_screenshots
        self.active_session_id: Optional[int] = None
        self.source_type: str = "HUMAN"  # 'HUMAN' hoặc 'BOT'
        self.frame_counter: int = 0
        self.is_recording: bool = False
        self._lock = threading.Lock()

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.screenshot_dir = os.path.join(base_dir, "data", "demonstrations", "screenshots")

    def start_session(self, source_type: str = "HUMAN", target_floor: int = 71) -> int:
        """
        Khởi tạo phiên ghi nhận dữ liệu mới.
        """
        with self._lock:
            self.source_type = source_type if source_type in ["HUMAN", "BOT"] else "HUMAN"
            self.frame_counter = 0
            self.is_recording = True

            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO demonstration_sessions (source_type, target_floor, quality_score)
                VALUES (?, ?, 1.0)
                """, (self.source_type, target_floor))
                conn.commit()
                self.active_session_id = cursor.lastrowid

            if self.save_screenshots:
                session_folder = os.path.join(self.screenshot_dir, f"session_{self.active_session_id}")
                os.makedirs(session_folder, exist_ok=True)

            print(f"[DemonstrationRecorder] ⏺️ Đã bắt đầu phiên ghi nhận Session #{self.active_session_id} (Nguồn: {self.source_type})")
            return self.active_session_id

    def record_frame(self, world_state: WorldState, action: SteeringCommand,
                     frame_bgr: Optional[any] = None, game_event: str = "NORMAL") -> Optional[DemonstrationFrame]:
        """
        Ghi nhận đồng bộ 1 khung hình thao tác.
        """
        if not self.is_recording or self.active_session_id is None:
            return None

        with self._lock:
            self.frame_counter += 1
            now = time.time()
            screenshot_path = None

            # Lưu ảnh chụp màn hình định kỳ hoặc khi có sự kiện đặc biệt nếu bật chế độ
            if self.save_screenshots and frame_bgr is not None:
                if self.frame_counter % 15 == 0 or game_event != "NORMAL":
                    session_folder = os.path.join(self.screenshot_dir, f"session_{self.active_session_id}")
                    fname = f"frame_{self.frame_counter:06d}.jpg"
                    screenshot_path = os.path.join(session_folder, fname)
                    try:
                        cv2.imwrite(screenshot_path, frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    except Exception:
                        screenshot_path = None

            demo_frame = DemonstrationFrame(
                frame_id=self.frame_counter,
                session_id=self.active_session_id,
                timestamp=now,
                world_state=world_state,
                action=action,
                source=self.source_type,
                game_event=game_event,
                screenshot_path=screenshot_path
            )

            # Ghi vào SQLite
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                    INSERT INTO demonstration_frames (
                        session_id, timestamp, player_x, player_y, player_hp,
                        action_type, action_angle, game_state, nearest_enemy_dist,
                        enemies_count, screenshot_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        self.active_session_id,
                        now,
                        world_state.player_pos[0],
                        world_state.player_pos[1],
                        world_state.player_hp,
                        action.action_type,
                        action.angle_degrees,
                        world_state.game_state,
                        world_state.nearest_enemy_dist,
                        world_state.enemies_count,
                        screenshot_path
                    ))
                    conn.commit()
            except Exception as e:
                print(f"[DemonstrationRecorder] Lỗi lưu frame: {e}")

            return demo_frame

    def end_session(self, quality_score: float = 1.0):
        """
        Kết thúc phiên ghi nhận và chốt tổng kết.
        """
        if not self.is_recording or self.active_session_id is None:
            return

        with self._lock:
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                    UPDATE demonstration_sessions
                    SET end_time = CURRENT_TIMESTAMP,
                        total_frames = ?,
                        quality_score = ?
                    WHERE session_id = ?
                    """, (self.frame_counter, quality_score, self.active_session_id))
                    conn.commit()
            except Exception as e:
                print(f"[DemonstrationRecorder] Lỗi kết thúc session: {e}")

            print(f"[DemonstrationRecorder] ⏹️ Đã kết thúc Session #{self.active_session_id}: {self.frame_counter} frames ghi nhận.")
            self.is_recording = False
            self.active_session_id = None

