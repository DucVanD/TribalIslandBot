import time
import os
import sys

base_dir = os.path.dirname(__file__)
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.engine_adb import ADBController
from core.engine_vision import VisionEngine

print("=" * 70)
print("BOT TỰ ĐỘNG CHIẾN ĐẤU LIÊN TỤC (CONTINUOUS BATTLE ENGINE)")
print("Hỗ trợ: Tự vào trận từ sảnh -> Chọn kỹ năng nếu có -> Chạy kiting & xả đạn liên tục")
print("Nhấn phím Ctrl + C trong cửa sổ cmd bất kỳ lúc nào để DỪNG BOT.")
print("=" * 70)

adb = ADBController()
vision = VisionEngine()

# 1. Khởi động kết nối
if not adb.ensure_connection():
    print("[LỖI] Không thể kết nối ADB tới BlueStacks!")
    exit()
print("✅ Đã kết nối BlueStacks thành công!")

# 2. Kiểm tra màn hình hiện tại
frame = adb.capture_screen()
if frame is None:
    print("[LỖI] Không chụp được màn hình Android.")
    exit()

# Kiểm tra sảnh chờ: nếu thấy nút vàng thì bấm vào trận
found_btn, btn_coords = vision.find_lobby_start_button(frame)
# Hoặc nếu đang ở sảnh (có chữ Tiếp Tục / Bắt Đầu)
if found_btn or True:
    print("\n👉 Đang bấm nút [TIẾP TỤC / BẮT ĐẦU] để vào trận...")
    adb.click_start()
    print("⏳ Đang tải bản đồ (chờ 4 giây)...")
    time.sleep(4.0)
    frame = adb.capture_screen()

# 3. Kiểm tra bảng chọn kỹ năng (nếu có - ví dụ Tầng 1 hoặc lên cấp)
print("\n🔍 Đang quét bảng chọn kỹ năng khởi đầu...")
for _ in range(4):
    if frame is not None and vision.is_level_up_screen(frame):
        print("   🎯 Đã thấy bảng kỹ năng! Đang chọn Thẻ 1...")
        adb.select_perk(1)
        time.sleep(0.6)
        frame = adb.capture_screen()
    else:
        break

# 4. Bước ra khỏi hốc cửa hẹp
print("\n🚀 Đang bước ra khỏi hốc cửa hẹp: Di chuyển LÊN TRÊN (W) 1.5 giây...")
adb.move_direction('w', duration_ms=1500)
time.sleep(0.3)

# 5. VÒNG LẶP CHIẾN ĐẤU THẢ DIỀU CAO CẤP (VỪA ĐI VỪA ĐÁNH, SPACE CHỈ DÙNG ĐỂ NÉ THOÁT HIỂM)
print("\n⚔️ BẮT ĐẦU CHIẾN ĐẤU THẢ DIỀU (VỪA ĐI VỪA ĐÁNH):")
print("   - Nhịp cơ động: Vừa lướt liên tục quanh phòng vừa xả đạn (quái không đuổi kịp).")
print("   - Kỹ năng tím (Space): TIẾT KIỆM - Chỉ dùng khi khẩn cấp (máu tụt hoặc cần né đòn).")
print("   - Tự động bơm Đùi gà ngay khi HP < 50%.")
print("   - Tự chọn kỹ năng khi lên cấp & Tự bấm Kết Thúc khi hết trận.\n")

# Vòng chạy elip chu vi lớn quanh phòng
pro_kiting_angles = [45.0, 140.0, 225.0, 320.0]
kiting_names = ["LÊN - PHẢI", "TRÁI - TRÊN", "XUỐNG - TRÁI", "PHẢI - DƯỚI"]

round_count = 0
last_vision_check = time.time()
last_heal_time = time.time()
last_escape_skill_time = time.time()
prev_hp = 100.0

try:
    while True:
        round_count += 1
        print(f"--- [VÒNG VỪA ĐI VỪA ĐÁNH #{round_count}] ---")

        # 4 góc lướt quanh phòng: Lướt liên tục và xả đạn theo nhịp
        for angle, name in zip(pro_kiting_angles, kiting_names):
            # Nhịp 1: Lướt nhanh 450ms -> Bắn ngay 1 phát
            adb.move_angle(angle, distance_ratio=1.0, duration_ms=450)
            adb.attack()
            time.sleep(0.04)

            # Nhịp 2: Tiếp tục lướt cùng hướng 450ms -> Bắn tiếp 1 phát
            adb.move_angle(angle, distance_ratio=1.0, duration_ms=450)
            adb.attack()
            time.sleep(0.04)

        # Cứ mỗi 2 vòng, nhích nhẹ lên phía trên (hướng cổng qua tầng)
        if round_count % 2 == 0:
            print("   🚪 Hướng lên phía trên cổng qua tầng...")
            adb.move_angle(90.0, distance_ratio=0.8, duration_ms=600)
            adb.attack()

        # Định kỳ mỗi 1.8 giây: Quét mắt kiểm tra HP, Né khẩn cấp, Lên cấp hoặc Hết trận
        if time.time() - last_vision_check > 1.8:
            last_vision_check = time.time()
            chk_frame = adb.capture_screen()
            if chk_frame is not None:
                # 1. Kiểm tra màn hình kết thúc trận (Chiến đấu kết thúc)
                if vision.is_end_battle_screen(chk_frame):
                    print("\n" + "=" * 70)
                    print("🏆 [CHIẾN ĐẤU KẾT THÚC] Phát hiện bảng kết quả & Chiến lợi phẩm!")
                    print("👉 Đang bấm nút vàng [KẾT THÚC] để nhận thưởng và quay về sảnh...")
                    adb.click_end_battle()
                    time.sleep(2.5)
                    print("✅ Đã nhận thưởng và trở về Sảnh chờ an toàn!")
                    print("=" * 70)
                    break

                # 2. Kiểm tra CỔNG DỊCH CHUYỂN QUA TẦNG (Khi quái đã chết hết)
                has_portal, p_pos = vision.find_portal(chk_frame)
                if has_portal:
                    print(f"\n🌀 [CỔNG DỊCH CHUYỂN ĐÃ MỞ {p_pos}] -> Quái đã dọn sạch!")
                    print("🚀 Đang tự động định vị và TIẾN THẲNG VÀO CỔNG QUA TẦNG...")
                    # Bước 1: Kéo từ góc phải về chính giữa phòng (hướng Lên - Trái 130 độ)
                    adb.move_angle(130.0, distance_ratio=1.0, duration_ms=1000)
                    time.sleep(0.1)
                    # Bước 2: Lao thẳng lên cửa vòm đá chứa cổng (hướng Lên 90 độ)
                    adb.move_angle(90.0, distance_ratio=1.0, duration_ms=1400)
                    time.sleep(0.5)
                    print("✨ Đã tiến vào cổng sang tầng tiếp theo!")
                    continue

                # 3. Đọc thanh máu HP
                current_hp = vision.get_hp_percentage(chk_frame)

                # CHIÊU TÍM (SPACE): CHỈ DÙNG ĐỂ NÉ THOÁT HIỂM KHI GẶP NGUY HIỂM!
                # Nếu máu bị sụt đột ngột (dính đòn) HOẶC máu dưới 65% -> Dùng chiêu tím lướt né ngay
                if (current_hp < 65.0 or current_hp < (prev_hp - 10.0)) and (time.time() - last_escape_skill_time > 4.0):
                    print(f"   ⚡ [NÉ KHẨN CẤP] Máu giảm ({current_hp:.1f}%) -> KÍCH HOẠT CHIÊU TÍM ĐỂ NÉ ĐÒN!")
                    adb.use_skill()
                    last_escape_skill_time = time.time()

                # Tự động bơm Đùi gà khi máu < 45%
                if current_hp < 45.0 and (time.time() - last_heal_time > 3.0):
                    print(f"   🍗 [BƠM MÁU KHẨN CẤP] HP còn {current_hp:.1f}% -> BƠM ĐÙI GÀ!")
                    adb.heal()
                    last_heal_time = time.time()
                    time.sleep(0.2)

                prev_hp = current_hp

                # 3. Kiểm tra lên cấp giữa trận
                if vision.is_level_up_screen(chk_frame):
                    print("   🌟 [LÊN CẤP GIỮA TRẬN] Đang chọn kỹ năng (Thẻ 1)...")
                    adb.select_perk(1)
                    time.sleep(0.6)

except KeyboardInterrupt:
    print("\n" + "=" * 70)
    print("🛑 ĐÃ DỪNG BOT THEO YÊU CẦU CỦA BẠN (Ctrl + C).")
    print("=" * 70)

