import time
import random
import threading
import json
import os

try:
    import pydirectinput
    pydirectinput.PAUSE = 0.01
except ImportError:
    pydirectinput = None


def tap_key(key, hold_time=0.06):
    """
    Giữ phím trong hold_time giây (mặc định 60ms) để giả lập Android/BlueStacks
    kịp ghi nhận tín hiệu chắc chắn 100%.
    """
    if not pydirectinput:
        return
    try:
        pydirectinput.keyDown(key)
        time.sleep(hold_time)
        pydirectinput.keyUp(key)
    except Exception as e:
        print(f"[CombatEngine] Lỗi bấm phím {key}: {e}")


class CombatEngine:
    """
    CombatEngine chịu trách nhiệm mô phỏng các thao tác bàn phím:
    - Di chuyển lên trên (W) khi mới vào tầng để thoát khỏi hốc cửa hẹp
    - CHIẾN THUẬT KITING (LÙA QUÁI VÒNG TRÒN): Chạy theo vòng W -> D -> S -> A (hoặc ngược lại)
      để quái dồn thành một cụm chạy sau lưng, né tối đa sát thương và chống kẹt góc.
    - Tự động spam nút đánh thường (J) với nhịp độ người thật (~4 lần/giây) tránh bị trượt đòn
    - Kích hoạt kỹ năng đặc biệt (Space)
    - Sử dụng đùi gà hồi máu khi nhận tín hiệu (L)
    - Chọn kỹ năng khi lên cấp (1, 2, 3)
    - Chế độ tự sát (đứng yên chờ quái hạ gục khi đã đạt tầng mục tiêu)
    """

    def __init__(self, key_config_path=None, settings_path=None):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        self.key_config_path = key_config_path or os.path.join(base_dir, "config", "key_mapping.json")
        self.settings_path = settings_path or os.path.join(base_dir, "config", "settings.json")

        self.keys = self._load_keys()
        self.settings = self._load_settings()

        self.attack_interval = self.settings.get("attack_interval", 0.22)
        self.attack_hold_time = self.settings.get("attack_hold_time", 0.06)

        self.is_running = False
        self.is_paused = False
        self.suicide_mode = False  # Đứng yên để chết nhận rương
        
        self._thread = None
        self._lock = threading.Lock()
        self.current_direction = None

        # Chiến thuật Kiting (Vòng tròn xuôi/ngược chiều kim đồng hồ)
        self.kiting_patterns = [
            ['w', 'd', 's', 'a'],  # Xuôi chiều kim đồng hồ: Lên -> Phải -> Xuống -> Trái
            ['w', 'a', 's', 'd']   # Ngược chiều kim đồng hồ: Lên -> Trái -> Xuống -> Phải
        ]
        self.current_pattern_idx = 0
        self.kiting_step = 0

    def _load_keys(self):
        default_keys = {
            "movement": ["w", "a", "s", "d"],
            "attack": "j",
            "heal_item": "l",
            "special_skill": "space",
            "select_perk": ["1", "2", "3"]
        }
        if os.path.exists(self.key_config_path):
            try:
                with open(self.key_config_path, "r", encoding="utf-8") as f:
                    return {**default_keys, **json.load(f)}
            except Exception as e:
                print(f"[CombatEngine] Lỗi đọc key mapping: {e}")
        return default_keys

    def _load_settings(self):
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[CombatEngine] Lỗi đọc settings: {e}")
        return {}

    def enter_room(self, duration=1.5):
        """
        Khi mới vào tầng hoặc bắt đầu lượt, nhân vật nằm trong hốc cửa hẹp.
        Cần giữ phím 'W' để chạy thẳng lên trên vào giữa phòng rộng.
        """
        if not pydirectinput or self.suicide_mode or self.is_paused:
            return
        print("[CombatEngine] 🚪 Xuất phát đầu tầng: Giữ [W] tiến vào giữa phòng...")
        with self._lock:
            self._release_all_movement_keys()
            pydirectinput.keyDown("w")
            self.current_direction = "w"

        attack_key = self.keys.get("attack", "j")
        start = time.time()
        while time.time() - start < duration:
            tap_key(attack_key, hold_time=self.attack_hold_time)
            time.sleep(self.attack_interval)

        with self._lock:
            pydirectinput.keyUp("w")
            self.current_direction = None
        print("[CombatEngine] ✅ Đã vào phòng rộng thành công!")

    def start(self, enter_first=True):
        if self._thread and self._thread.is_alive():
            return
        self.is_running = True
        self.is_paused = False
        self.suicide_mode = False
        self._thread = threading.Thread(target=self._combat_loop, args=(enter_first,), daemon=True)
        self._thread.start()
        print("[CombatEngine] Đã khởi động luồng chiến đấu Kiting (Lùa quái vòng tròn).")

    def stop(self):
        self.is_running = False
        self._release_all_movement_keys()
        print("[CombatEngine] Đã dừng luồng chiến đấu.")

    def pause(self):
        """Tạm dừng di chuyển và tấn công (dùng khi lên cấp hoặc load màn)."""
        self.is_paused = True
        self._release_all_movement_keys()
        print("[CombatEngine] Đã tạm dừng thao tác.")

    def resume(self):
        self.is_paused = False
        print("[CombatEngine] Tiếp tục thao tác chiến đấu.")

    def set_suicide_mode(self, enabled=True):
        self.suicide_mode = enabled
        if enabled:
            self._release_all_movement_keys()
            print("[CombatEngine] Bật chế độ TỰ SÁT: Đứng yên chờ kết thúc trận.")

    def trigger_heal(self):
        heal_key = self.keys.get("heal_item", "l")
        tap_key(heal_key, hold_time=0.06)
        print(f"[CombatEngine] -> 🍗 ĐÃ DÙNG ĐÙI GÀ HỒI MÁU (Phím {heal_key})")

    def trigger_skill(self):
        skill_key = self.keys.get("special_skill", "space")
        tap_key(skill_key, hold_time=0.06)
        print(f"[CombatEngine] -> ⚡ ĐÃ DÙNG KỸ NĂNG (Phím {skill_key})")

    def select_perk(self, index: int):
        perk_keys = self.keys.get("select_perk", ["1", "2", "3"])
        if 1 <= index <= len(perk_keys):
            key = perk_keys[index - 1]
            tap_key(key, hold_time=0.06)
            print(f"[CombatEngine] -> 🌟 ĐÃ CHỌN KỸ NĂNG {index} (Phím {key})")

    def _release_all_movement_keys(self):
        if not pydirectinput:
            return
        for k in self.keys.get("movement", ["w", "a", "s", "d"]):
            try:
                pydirectinput.keyUp(k)
            except Exception:
                pass
        self.current_direction = None

    def _kiting_next_direction(self):
        """
        Di chuyển theo chu kỳ vòng tròn để gom quái đi theo sau lưng (Kiting).
        Thỉnh thoảng đảo chiều quay (xuôi / ngược kim đồng hồ) để tránh kẹt địa hình.
        """
        if not pydirectinput or self.suicide_mode or self.is_paused:
            return

        pattern = self.kiting_patterns[self.current_pattern_idx]
        next_direction = pattern[self.kiting_step % len(pattern)]
        self.kiting_step += 1

        # Cứ sau 1 vòng (4 bước), có 20% khả năng đổi chiều quay (clockwise <-> counter-clockwise)
        if self.kiting_step % len(pattern) == 0 and random.random() < 0.25:
            self.current_pattern_idx = 1 - self.current_pattern_idx
            # print("[CombatEngine] 🔄 Đảo chiều quay vòng tròn lùa quái!")

        with self._lock:
            if self.current_direction and self.current_direction != next_direction:
                try:
                    pydirectinput.keyUp(self.current_direction)
                except Exception:
                    pass
            try:
                pydirectinput.keyDown(next_direction)
            except Exception:
                pass
            self.current_direction = next_direction

    def _combat_loop(self, enter_first=True):
        if not pydirectinput:
            print("[CombatEngine] LỖI: Chưa cài pydirectinput!")
            return

        # Bước 1: Thoát khỏi hốc cửa hẹp nếu xuất phát
        if enter_first:
            self.enter_room(duration=1.5)

        attack_key = self.keys.get("attack", "j")
        last_dir_change = time.time()
        last_skill_trigger = time.time()
        
        self._kiting_next_direction()

        while self.is_running:
            if self.is_paused:
                time.sleep(0.1)
                continue

            if self.suicide_mode:
                time.sleep(0.2)
                continue

            now = time.time()

            # 1. Spam phím tấn công thường (J) với nhịp chuẩn người bấm (~4 lần/giây)
            tap_key(attack_key, hold_time=self.attack_hold_time)

            # 2. Dùng skill nhân vật (mỗi 4s)
            if now - last_skill_trigger > 4.0:
                self.trigger_skill()
                last_skill_trigger = now

            # 3. Chạy theo cung vòng tròn kiting (sau mỗi 2.0 - 2.8s chuyển cạnh tiếp theo)
            if now - last_dir_change > random.uniform(2.0, 2.8):
                self._kiting_next_direction()
                last_dir_change = now

            time.sleep(self.attack_interval)

        self._release_all_movement_keys()
