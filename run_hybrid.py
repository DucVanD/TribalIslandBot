# -*- coding: utf-8 -*-
"""
run_hybrid.py
Script chạy thực chiến Autonomous Hybrid Agent (Level 3).
Hoạt động ngầm 100% qua ADB - Không chiếm chuột, không chiếm bàn phím.
Tự động: Nhận diện Quái, Cọc gỗ -> Kiểm tra tầm nhìn đạn (LOS) -> Bẻ lái né cọc -> Tự lưu kinh nghiệm SQLite.
"""

import sys
import os
import time

base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.hybrid_agent import HybridAgent


def main():
    print("=" * 70)
    print("🚀 KHỞI ĐỘNG TRIBAL ISLAND BOT – AUTONOMOUS HYBRID AGENT (LEVEL 3)")
    print("=" * 70)
    print("• Cơ chế: Điều khiển ngầm 100% qua ADB (Chuột/Phím máy tính tự do).")
    print("• Tầm nhìn: Tự quét quái vật, cọc gỗ, thanh máu người chơi.")
    print("• Né kẹt: Tự động phát hiện cọc gỗ cản đường đạn và bẻ lái mở góc bắn.")
    print("• Bộ nhớ: Lưu lại kết quả từng tầng vào SQLite (data/tribal_memory.db).")
    print("=" * 70)
    print("👉 Nhấn Ctrl + C bất kỳ lúc nào để DỪNG BOT AN TOÀN.\n")

    agent = HybridAgent(
        target_floor=71,
        hp_critical_percent=35.0,
        log_callback=print
    )

    success = agent.start()
    if not success:
        print("\n❌ Không thể kết nối tới BlueStacks!")
        print("Vui lòng kiểm tra:")
        print("  1. Đã bật BlueStacks 5 chưa?")
        print("  2. Vào BlueStacks Settings > Advanced > Đã BẬT 'Android Debug Bridge (ADB)' chưa?")
        print("  3. Thử khởi động lại BlueStacks nếu vừa mới bật ADB.")
        return

    try:
        while agent.is_running:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[!] Nhận lệnh ngắt Ctrl + C từ bàn phím. Đang dừng bot...")
        agent.stop()
        print("[!] Đã dừng bot và lưu toàn bộ kết quả vào bộ nhớ an toàn.")


if __name__ == "__main__":
    main()

