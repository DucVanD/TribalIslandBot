import time
import threading
import pyautogui

try:
    import pygetwindow as gw
except ImportError:
    gw = None

from .engine_combat import CombatEngine
from .engine_vision import VisionEngine
from .hybrid_agent import HybridAgent


class RunState:
    IDLE = "IDLE"
    LOBBY = "LOBBY"
    FIGHTING = "FIGHTING"
    LEVEL_UP = "LEVEL_UP"
    SUICIDE = "SUICIDE"
    BATTLE_END = "BATTLE_END"


def get_bluestacks_window():
    """
    Tìm chính xác cửa sổ game BlueStacks App Player,
    loại bỏ cửa sổ vô hình 'BlueStacks Keymap Overlay'.
    """
    if not gw:
        return None
    try:
        # 1. Ưu tiên tìm cửa sổ chứa App Player
        for w in gw.getAllWindows():
            title = w.title.strip()
            if "bluestacks" in title.lower() and "overlay" not in title.lower() and title != "":
                if "app player" in title.lower():
                    return w

        # 2. Dự phòng: bất kỳ cửa sổ bluestacks nào không chứa chữ 'overlay'
        for w in gw.getAllWindows():
            title = w.title.strip()
            if "bluestacks" in title.lower() and "overlay" not in title.lower() and title != "":
                return w
    except Exception:
        pass
    return None


class RunManager:
    """
    RunManager là bộ não điều phối:
    - Bắt đúng cửa sổ 'BlueStacks App Player' (không bắt nhầm 'Keymap Overlay')
    - Chụp ảnh đúng vùng cửa sổ BlueStacks (dù kéo cửa sổ sang góc nào cũng chính xác 100%)
    - Tự động click nút vàng [Bắt Đầu / Tiếp Tục]
    - Điều phối chu kỳ cày rương tự động hoàn toàn
    """

    def __init__(self, target_floor=71, hp_heal_threshold=30, auto_repeat=True, log_callback=None, use_hybrid=True):
        self.target_floor = target_floor
        self.hp_heal_threshold = hp_heal_threshold
        self.auto_repeat = auto_repeat
        self.log_callback = log_callback or print
        self.use_hybrid = use_hybrid

        self.combat = CombatEngine()
        self.vision = VisionEngine()
        self.hybrid = HybridAgent(
            target_floor=target_floor,
            hp_critical_percent=hp_heal_threshold,
            log_callback=self.log
        )

        self.state = RunState.IDLE
        self.current_floor = 1
        self.is_running = False
        self._thread = None

        self.total_runs_completed = 0
        self.bs_win = None

    def log(self, message):
        if self.log_callback:
            self.log_callback(message)

    def focus_bluestacks_window(self):
        """Kích hoạt và nổi cửa sổ BlueStacks App Player lên phía trước."""
        win = get_bluestacks_window()
        if win:
            self.bs_win = win
            try:
                if win.isMinimized:
                    win.restore()
                win.activate()
                # Click chuột vào thanh tiêu đề BlueStacks để ép Windows chuyển quyền focus 100%
                click_x = win.left + 200
                click_y = win.top + 15
                pyautogui.click(click_x, click_y)
                self.log(f"[RunManager] 🎯 Đã kích hoạt và chuyển quyền điều khiển vào: '{win.title}'")
                time.sleep(0.4)
                return True
            except Exception as e:
                self.log(f"[CẢNH BÁO] Không thể kích hoạt cửa sổ: {e}")
        else:
            self.log("[CẢNH BÁO] Không tìm thấy cửa sổ 'BlueStacks App Player'. Vui lòng mở game trước!")
        return False

    def get_bluestacks_bbox(self):
        """Lấy tọa độ vùng cửa sổ BlueStacks (left, top, right, bottom)."""
        win = get_bluestacks_window()
        if win and win.width > 200 and win.height > 200:
            self.bs_win = win
            return (win.left, win.top, win.right, win.bottom)
        return None

    def start(self):
        if self.is_running:
            return

        if self.use_hybrid:
            self.hybrid.target_floor = self.target_floor
            self.hybrid.hp_critical_percent = self.hp_heal_threshold
            started = self.hybrid.start()
            if started:
                self.is_running = True
                self.state = RunState.FIGHTING
                self.log(f"[RunManager] 🚀 Bắt đầu Autonomous Hybrid Agent (Level 3). Tầng mục tiêu: {self.target_floor}")
            else:
                self.log("[RunManager] ⚠️ Không thể kết nối ADB tới BlueStacks. Vui lòng bật ADB trong Settings BlueStacks!")
            return

        # 1. Kích hoạt đúng cửa sổ BlueStacks (Legacy)
        self.focus_bluestacks_window()

        self.is_running = True
        self.state = RunState.IDLE
        self.current_floor = 1
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.log(f"[RunManager] Bắt đầu hệ thống Auto Bot (Legacy). Tầng mục tiêu: {self.target_floor}")

    def stop(self):
        self.is_running = False
        self.state = RunState.IDLE
        if self.use_hybrid:
            self.hybrid.stop()
        else:
            self.combat.stop()
        self.log("[RunManager] Đã dừng toàn bộ bot.")

    def pause(self):
        if self.use_hybrid:
            self.hybrid.pause()
        else:
            self.combat.pause()
        self.log("[RunManager] Tạm dừng.")

    def resume(self):
        if self.use_hybrid:
            self.hybrid.resume()
        else:
            self.combat.resume()
        self.log("[RunManager] Tiếp tục.")

    def _click_start_lobby(self, click_coords, bbox=None):
        """Click vào nút màu vàng Tiếp Tục / Bắt Đầu ở Sảnh Chờ (ưu tiên qua ActionEngine ADB)."""
        rx, ry = click_coords
        self.log(f"[RunManager] 🎯 Phát hiện nút [Bắt Đầu / Tiếp Tục] tại ({rx}, {ry}).")
        
        # 1. Ưu tiên gửi qua ActionEngine (ADB background, không chiếm chuột máy tính)
        if self.hybrid.action.is_connected or self.hybrid.action.ensure_connection():
            self.log("[RunManager] 🚀 Gửi lệnh click_start() ngầm qua ActionEngine (ADB)...")
            self.hybrid.action.click_start()
        else:
            # 2. Dự phòng: Nếu chưa bật ADB, dùng chuột trực tiếp
            if bbox:
                screen_x = bbox[0] + rx
                screen_y = bbox[1] + ry
            else:
                screen_x, screen_y = rx, ry

            try:
                if self.bs_win:
                    try:
                        self.bs_win.activate()
                    except Exception:
                        pass
                pyautogui.click(screen_x, screen_y)
            except Exception as e:
                self.log(f"[RunManager] Lỗi click chuột dự phòng: {e}")

        self.log("[RunManager] Đang tải vào màn chơi (chờ 3.5 giây)...")
        time.sleep(3.5)

        # Chuyển trạng thái sang chiến đấu và vượt hốc cửa hẹp
        self.current_floor = 1
        self.state = RunState.FIGHTING
        self.combat.set_suicide_mode(False)
        self.combat.start(enter_first=True)

    def _run_loop(self):
        last_heal_time = 0
        last_floor_check_time = 0
        last_lobby_check_time = 0

        while self.is_running:
            now = time.time()
            
            # Lấy vùng cửa sổ BlueStacks thực tế trên màn hình
            bbox = self.get_bluestacks_bbox()
            frame_bgr, _ = self.vision.capture_screen(bbox=bbox)

            # 1. KIỂM TRA MÀN HÌNH SẢNH CHỜ (LOBBY) - TỰ ĐỘNG BẤM [BẮT ĐẦU / TIẾP TỤC]
            if self.state in [RunState.IDLE, RunState.LOBBY, RunState.BATTLE_END]:
                if now - last_lobby_check_time > 1.0:
                    found_btn, click_coords = self.vision.find_lobby_start_button(frame_bgr)
                    if found_btn:
                        self.state = RunState.LOBBY
                        self.combat.pause()
                        self._click_start_lobby(click_coords, bbox=bbox)
                        last_lobby_check_time = now
                        continue
                    last_lobby_check_time = now

            # 2. KIỂM TRA MÀN HÌNH KẾT THÚC TRẬN / NHẬN RƯƠNG
            if self.vision.is_end_battle_screen(frame_bgr):
                self.state = RunState.BATTLE_END
                self.combat.pause()
                self.log("[RunManager] 🎁 Phát hiện màn hình KẾT THÚC TRẬN ĐẤU / NHẬN RƯƠNG.")
                
                time.sleep(2.0)
                # Bấm xác nhận nhận quà (phím Space hoặc click)
                self.combat.trigger_skill()
                self.total_runs_completed += 1
                self.log(f"[RunManager] ✅ Hoàn thành lượt thứ {self.total_runs_completed}!")

                if self.auto_repeat:
                    self.log("[RunManager] Đang chờ hệ thống quay trở lại Sảnh Chờ để nhận diện nút Bắt Đầu...")
                    time.sleep(3.0)
                else:
                    self.stop()
                    break
                continue

            # 3. KIỂM TRA MÀN HÌNH LÊN CẤP (CHỌN KỸ NĂNG)
            if self.vision.is_level_up_screen(frame_bgr):
                if self.state != RunState.LEVEL_UP:
                    self.state = RunState.LEVEL_UP
                    self.combat.pause()
                    self.log("[RunManager] 🌟 LÊN CẤP! Tạm dừng đánh để chọn kỹ năng...")
                    
                    time.sleep(0.5)
                    self.combat.select_perk(1)
                    time.sleep(1.0)
                    
                    self.state = RunState.FIGHTING
                    self.combat.resume()
                    continue

            # 4. KIỂM TRA SỐ TẦNG ĐỊNH KỲ
            if self.state == RunState.FIGHTING and (now - last_floor_check_time > 2.0):
                detected_floor = self.vision.detect_floor_number(frame_bgr)
                if detected_floor is not None and detected_floor >= self.current_floor:
                    if detected_floor > self.current_floor:
                        self.current_floor = detected_floor
                        self.log(f"[RunManager] 🚪 >>> TIẾN VÀO TẦNG {self.current_floor} <<<")
                        # Thoát khỏi hốc cửa hẹp của tầng mới
                        self.combat.enter_room(duration=1.2)

                    # Kiểm tra xem đã đạt tầng mục tiêu chưa
                    if self.current_floor >= self.target_floor:
                        if not self.combat.suicide_mode:
                            self.state = RunState.SUICIDE
                            self.combat.set_suicide_mode(True)
                            self.log(f"[RunManager] 💀 !!! ĐÃ ĐẠT TẦNG MỤC TIÊU ({self.target_floor}) !!!")
                            self.log("[RunManager] Chuyển sang chế độ TỰ SÁT: Đứng yên chờ quái hạ gục để nhận rương.")
                last_floor_check_time = now

            # 5. KIỂM TRA VÀ BƠM MÁU
            if self.state == RunState.FIGHTING and not self.combat.suicide_mode:
                hp = self.vision.get_hp_percentage(frame_bgr)
                # Chỉ cảnh báo máu yếu khi hp > 0 (tránh trường hợp chưa đọc được màn hình game)
                if 0.0 < hp < self.hp_heal_threshold and (now - last_heal_time > 3.0):
                    self.log(f"[RunManager] 🍗 CẢNH BÁO MÁU YẾU ({hp:.1f}% < {self.hp_heal_threshold}%) -> BƠM ĐÙI GÀ!")
                    self.combat.trigger_heal()
                    last_heal_time = now

            # Nếu đang ở IDLE quá 3 giây mà không phải ở sảnh (người dùng bấm Start khi đã ở trong trận)
            if self.state == RunState.IDLE and self.is_running:
                # Kiểm tra xem có thanh máu không
                hp_test = self.vision.get_hp_percentage(frame_bgr)
                if hp_test > 10.0:
                    self.log("[RunManager] Phát hiện đang ở trong trận đấu! Chuyển sang chiến đấu...")
                    self.state = RunState.FIGHTING
                    self.combat.start(enter_first=False)

            time.sleep(0.1)
