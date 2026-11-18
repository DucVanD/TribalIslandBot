import sys
import os
import argparse

# Đảm bảo đường dẫn thư mục gốc nằm trong sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.manager_run import RunManager


def parse_arguments():
    parser = argparse.ArgumentParser(description="Tribal Island Auto Bot")
    parser.add_argument("--cli", action="store_true", help="Chạy chế độ dòng lệnh (không cần giao diện GUI)")
    parser.add_argument("--floor", type=int, default=71, help="Tầng mục tiêu kết thúc lượt (mặc định: 71)")
    parser.add_argument("--hp", type=int, default=30, help="Phần trăm máu để kích hoạt bơm đùi gà (mặc định: 30)")
    parser.add_argument("--repeat", action="store_true", default=True, help="Tự động lặp lại sau khi kết thúc lượt")
    return parser.parse_args()


def run_cli_mode(manager):
    print("=" * 60)
    print("KHỞI ĐỘNG TRIBAL ISLAND BOT Ở CHẾ ĐỘ DÒNG LỆNH (CLI)")
    print(f"Mục tiêu tầng: {manager.target_floor} | Ngưỡng máu: {manager.hp_heal_threshold}%")
    print("Nhấn Ctrl + C để dừng bot bất kỳ lúc nào.")
    print("=" * 60)
    try:
        manager.start()
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[!] Đang dừng bot...")
        manager.stop()
        print("[!] Đã thoát an toàn.")


def main():
    # Tạo thư mục assets nếu chưa có
    assets_dir = os.path.join(BASE_DIR, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    args = parse_arguments()
    manager = RunManager(
        target_floor=args.floor,
        hp_heal_threshold=args.hp,
        auto_repeat=args.repeat
    )

    if args.cli:
        run_cli_mode(manager)
    else:
        try:
            from gui.app_window import launch_gui, PYSIDE_AVAILABLE
            if PYSIDE_AVAILABLE:
                launch_gui(manager)
            else:
                print("[!] PySide6 chưa được cài đặt. Tự động chuyển sang chế độ CLI...")
                run_cli_mode(manager)
        except Exception as e:
            print(f"[!] Không thể mở giao diện GUI ({e}). Chuyển sang CLI...")
            run_cli_mode(manager)


if __name__ == "__main__":
    main()

