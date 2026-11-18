import time
import random
import json
import os
import pyautogui

try:
    import pydirectinput
    pydirectinput.PAUSE = 0.01
except ImportError:
    print("[CẢNH BÁO] Chưa cài thư viện 'pydirectinput'. Chạy: pip install pydirectinput")
    pydirectinput = None

try:
    import pygetwindow as gw
except ImportError:
    gw = None


def auto_focus_bluestacks():
    """
    Kích hoạt và ÉP Windows chuyển quyền điều khiển (Focus) sang BlueStacks
    bằng cách CLICK TRỰC TIẾP vào thanh tiêu đề của BlueStacks (chống bị gõ phím vào terminal).
    """
    if not gw:
        return False
    try:
        target_win = None
        for w in gw.getAllWindows():
            title = w.title.strip()
            if "bluestacks" in title.lower() and "overlay" not in title.lower() and title != "":
                if "app player" in title.lower():
                    target_win = w
                    break
                if not target_win:
                    target_win = w

        if target_win:
            if target_win.isMinimized:
                target_win.restore()
            try:
                target_win.activate()
            except Exception:
                pass
            
            # BÍ QUYẾT: Click chuột 1 cái vào thanh tiêu đề BlueStacks
            # để Windows chuyển con trỏ phím rời khỏi Terminal sang BlueStacks 100%!
            click_x = target_win.left + 200
            click_y = target_win.top + 15
            pyautogui.click(click_x, click_y)
            print(f"🎯 [AUTO-FOCUS] Đã click kích hoạt BlueStacks tại ({click_x}, {click_y})!")
            time.sleep(0.4)
            return True
        else:
            print("[CẢNH BÁO] Không tìm thấy cửa sổ BlueStacks App Player. Vui lòng mở game trước!")
    except Exception as e:
        print(f"[CẢNH BÁO] Lỗi auto-focus: {e}")
    return False


def load_config():
    base_dir = os.path.dirname(__file__)
    keys_path = os.path.join(base_dir, "config", "key_mapping.json")
    settings_path = os.path.join(base_dir, "config", "settings.json")

    keys = {
        "movement": ["w", "a", "s", "d"],
        "attack": "j",
        "heal_item": "l",
        "special_skill": "space",
        "select_perk": ["1", "2", "3"]
    }
    settings = {
        "attack_interval": 0.22,
        "attack_hold_time": 0.06
    }

    if os.path.exists(keys_path):
        with open(keys_path, "r", encoding="utf-8") as f:
            keys.update(json.load(f))
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            settings.update(json.load(f))

    return keys, settings


def tap_key(key, hold_time=0.06):
    """
    Giữ phím trong hold_time (60ms) để BlueStacks ghi nhận tín hiệu chắc chắn 100%.
    """
    if not pydirectinput:
        return
    try:
        pydirectinput.keyDown(key)
        time.sleep(hold_time)
        pydirectinput.keyUp(key)
    except Exception as e:
        print(f"Lỗi bấm phím {key}: {e}")


def simulate_combat(duration=12):
    """
    Giả lập chiến đấu:
    1. Tự động Click thanh tiêu đề BlueStacks để giành quyền focus từ Terminal.
    2. Giữ 'W' 1.5s chạy thẳng lên trên thoát hốc cửa hẹp.
    3. Vừa chạy vừa đánh theo vòng tròn Kiting (W -> D -> S -> A).
    """
    if pydirectinput is None:
        print("[LỖI] Không thể chạy do thiếu pydirectinput.")
        return

    keys, settings = load_config()
    movement_keys = keys.get("movement", ["w", "a", "s", "d"])
    attack_key = keys.get("attack", "j")
    skill_key = keys.get("special_skill", "space")

    attack_interval = settings.get("attack_interval", 0.22)
    attack_hold_time = settings.get("attack_hold_time", 0.06)

    print("=" * 65)
    print("TEST COMBAT (AUTO-FOCUS CHUẨN + KITING VÒNG TRÒN)")
    print(f"Phím Di Chuyển: {movement_keys} | Phím Đánh: [{attack_key.upper()}] | Chiêu: [{skill_key.upper()}]")
    print(f"Nhịp đánh: Giữ {attack_hold_time*1000:.0f}ms, nghỉ {attack_interval*1000:.0f}ms (~4 lần/giây)")
    print("=" * 65)

    # 1. Ép tiêu điểm rời khỏi Terminal và chuyển thẳng sang BlueStacks
    auto_focus_bluestacks()

    print("Bắt đầu trong 2 giây...")
    for i in range(2, 0, -1):
        print(f"{i}...")
        time.sleep(1)

    # BƯỚC 1: THOÁT HỐC CỬA ĐẦU TẦNG
    print("\n🚀 [BƯỚC 1] Xuất phát: Giữ [W] chạy thẳng lên trên (1.5 giây)...")
    pydirectinput.keyDown("w")
    start_w = time.time()
    while time.time() - start_w < 1.5:
        tap_key(attack_key, hold_time=attack_hold_time)
        time.sleep(attack_interval)
    pydirectinput.keyUp("w")
    print("   -> Đã vào phòng rộng thành công!")

    # BƯỚC 2: CHIẾN ĐẤU VỚI NHỊP ĐỘ CHUẨN (KITING)
    print(f"\n⚔️ [BƯỚC 2] Bắt đầu đảo hướng di chuyển và xả đạn trong {duration} giây...")
    start_time = time.time()
    
    kiting_pattern = ['w', 'd', 's', 'a']
    step_idx = 0
    current_direction = kiting_pattern[step_idx]
    pydirectinput.keyDown(current_direction)
    print(f"[*] Hướng di chuyển đầu tiên: [{current_direction.upper()}]")

    last_dir_change = time.time()
    last_skill_time = time.time()
    attack_count = 0

    try:
        while time.time() - start_time < duration:
            # Bấm tấn công với nhịp vừa phải (~4-5 lần/giây)
            tap_key(attack_key, hold_time=attack_hold_time)
            attack_count += 1
            print(f"⚔️ Bắn đòn thứ {attack_count:02d} (Phím {attack_key.upper()})")

            now = time.time()
            # Dùng skill (Space)
            if now - last_skill_time > 4.0:
                tap_key(skill_key, hold_time=0.06)
                print(f"⚡ [KỸ NĂNG] Nhấn phím: [{skill_key.upper()}]")
                last_skill_time = now

            # Di chuyển Kiting theo chu kỳ vòng tròn
            if now - last_dir_change > 2.5:
                pydirectinput.keyUp(current_direction)
                step_idx = (step_idx + 1) % len(kiting_pattern)
                current_direction = kiting_pattern[step_idx]
                pydirectinput.keyDown(current_direction)
                print(f"🔄 Kiting vòng tròn: Hướng [{current_direction.upper()}]")
                last_dir_change = now

            time.sleep(attack_interval)

    except KeyboardInterrupt:
        print("\n[!] Dừng khẩn cấp bằng phím tắt Ctrl+C.")
    finally:
        pydirectinput.keyUp(current_direction)
        print("=" * 65)
        print(f"Hoàn thành! Đã tung ra {attack_count} đòn đánh nhịp chuẩn.")
        print("Đã nhả toàn bộ phím an toàn.")
        print("=" * 65)


if __name__ == "__main__":
    simulate_combat(duration=10)
