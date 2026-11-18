# -*- coding: utf-8 -*-
"""
core/demonstration/trajectory_extractor.py
Trích xuất quỹ đạo di chuyển và hành vi của người chơi từ video thị phạm (Demonstration Videos).
Phân tích:
- Tọa độ người chơi (x_t, y_t) qua từng mốc thời gian
- Vector di chuyển (dx, dy) và góc di chuyển thực tế của con người
- Khoảng cách duy trì tới quái vật
- Tần suất đổi hướng và nhịp độ kiting
"""

import cv2
import os
import math
import json
import time
from typing import List, Dict, Any, Optional

from core.perception.detector_player import PlayerDetector
from core.perception.detector_enemy import EnemyDetector


class TrajectoryExtractor:
    """
    TrajectoryExtractor:
    Phân tích video gameplay của người chơi mẫu, trích xuất dữ liệu hành vi (Demonstration Data)
    để nạp vào mô hình ra quyết định thích ứng (Adaptive Decision).
    """

    def __init__(self, sample_interval_frames: int = 6):
        self.sample_interval = sample_interval_frames
        self.player_detector = PlayerDetector()
        self.enemy_detector = EnemyDetector()

    def extract_from_video(self, video_path: str, max_frames: int = 1500) -> List[Dict[str, Any]]:
        """
        Trích xuất chuỗi hành động từ 1 file video gameplay.
        """
        if not os.path.exists(video_path):
            print(f"[TrajectoryExtractor] ❌ Không tìm thấy video: {video_path}")
            return []

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        trajectory: List[Dict[str, Any]] = []
        frame_idx = 0
        last_pos = None

        print(f"[TrajectoryExtractor] 🎬 Bắt đầu phân tích: {os.path.basename(video_path)} ({total_video_frames} frames, FPS: {fps:.1f})")

        while cap.isOpened() and frame_idx < max_frames:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            if frame_idx % self.sample_interval == 0:
                t_sec = frame_idx / fps
                player = self.player_detector.detect(frame)

                if player and player.confidence > 0.60:
                    curr_pos = (player.center_x, player.center_y)
                    
                    angle_deg = None
                    speed = 0.0
                    if last_pos is not None:
                        dx = curr_pos[0] - last_pos[0]
                        dy = curr_pos[1] - last_pos[1]
                        dist = math.hypot(dx, dy)
                        dt = self.sample_interval / fps
                        speed = dist / dt

                        if dist > 8.0:
                            # Hệ tọa độ: Android Y hướng xuống
                            rad = math.atan2(-dy, dx)
                            angle_deg = (math.degrees(rad) + 360.0) % 360.0

                    # Quét quái vật xung quanh
                    enemies = self.enemy_detector.detect(frame, player_pos=curr_pos)
                    nearest_dist = 9999.0
                    for e in enemies:
                        d = math.hypot(e.center_x - curr_pos[0], e.center_y - curr_pos[1])
                        if d < nearest_dist:
                            nearest_dist = d

                    trajectory.append({
                        "frame_idx": frame_idx,
                        "time_sec": round(t_sec, 2),
                        "player_x": curr_pos[0],
                        "player_y": curr_pos[1],
                        "angle_deg": round(angle_deg, 1) if angle_deg is not None else None,
                        "speed_px_per_sec": round(speed, 1),
                        "nearest_enemy_dist": round(nearest_dist, 1) if nearest_dist < 9000 else None,
                        "enemies_count": len(enemies)
                    })

                    last_pos = curr_pos

            frame_idx += 1

        cap.release()
        print(f"[TrajectoryExtractor] ✅ Đã trích xuất {len(trajectory)} mốc hành vi người chơi.")
        return trajectory

    def save_trajectory(self, trajectory: List[Dict[str, Any]], output_path: str):
        """Lưu dữ liệu quỹ đạo ra file JSON."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(trajectory, f, indent=2, ensure_ascii=False)
        print(f"[TrajectoryExtractor] 💾 Đã lưu dữ liệu thị phạm vào: {output_path}")

