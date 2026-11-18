# -*- coding: utf-8 -*-
"""
tests/test_p2_perception.py
Kiểm thử độc lập tầng Perception trên khung hình mẫu (không cần kết nối BlueStacks).
"""

import os
import sys
import cv2

base_dir = os.path.dirname(os.path.dirname(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.perception.perception_engine import PerceptionEngine

def test_perception_offline():
    print("=" * 60)
    print("TEST P2: PERCEPTION ENGINE (OFFLINE TEST SUITE)")
    print("=" * 60)

    test_img = os.path.join(base_dir, "assets", "video_level1_flow", "frame_015_22.5s.png")
    if not os.path.exists(test_img):
        print(f"[CẢNH BÁO] Không tìm thấy ảnh test tại: {test_img}")
        return False

    frame = cv2.imread(test_img)
    pe = PerceptionEngine()

    result = pe.analyze(frame, check_ocr_floor=False)

    print(f"1. Khung hình: {frame.shape[1]}x{frame.shape[0]}")
    print(f"2. Người chơi (Player): {result.player}")
    print(f"3. Số quái vật phát hiện: {len(result.enemies)}")
    print(f"4. Số cọc gỗ/vật cản: {len(result.obstacles)}")
    print(f"5. Độ tin cậy tổng thể (Confidence): {result.overall_confidence:.2f}")

    assert result.player is not None, "Player detection failed!"
    assert result.overall_confidence >= 0.70, "Confidence is too low!"
    print("\n✅ TEST P2 PERCEPTION THÀNH CÔNG RỰC RỠ!")
    return True

if __name__ == "__main__":
    test_perception_offline()

