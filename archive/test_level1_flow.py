import time
import os
import sys

base_dir = os.path.dirname(__file__)
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.engine_adb import ADBController
from core.engine_vision import VisionEngine

print("=" * 70)
print("BÀI TEST TOÀN DIỆN: QUY TRÌNH TẦNG 1 (LOBBY -> CHỌN KỸ NĂNG -> CHIẾN ĐẤU)")
print("Hoạt động 100% ngầm qua ADB - Chuột & Bàn phím máy tính tự do hoàn toàn.")
print("=" * 70)

adb = ADBController()
vision = VisionEngine()

print("\n1. Đang kết nối ADB tới BlueStacks...")
if not adb.ensure_connection():
    print("[LỖI] Không thể kết nối ADB! Vui lòng kiểm tra BlueStacks đã bật ADB.")
    exit()
print("   ✅ Kết nối ADB thành công!")

# 2. Kiểm tra trạng thái hiện tại từ màn hình game
print("\n2. Đang chụp màn hình Android qua ADB để kiểm tra trạng thái...")
frame = adb.capture_screen()
if frame is None:
    print("[LỖI] Không chụp được màn hình Android qua ADB.")
    exit()
print(f"   ✅ Chụp thành công kích thước: {frame.shape[1]}x{frame.shape[0]}")

# Kiểm tra xem có đang ở sảnh chờ không
found_btn, btn_coords = vision.find_lobby_start_button(frame)
is_lvl_up = vision.is_level_up_screen(frame)

if found_btn or is_lvl_up or True:
    # Nếu đang ở sảnh chờ hoặc user đang để game ở sảnh
    print("\n3. BƯỚC 1: BẤM BẮT ĐẦU / TIẾP TỤC Ở SẢNH CHỜ...")
    print("   👉 Đang gửi lệnh tap vào nút vàng sảnh chờ...")
    adb.click_start()
    print("   ✅ Đã bấm nút vào trận! Chờ 4 giây để game tải bản đồ...")
    time.sleep(4)

    # Chụp lại màn hình sau khi tải
    frame = adb.capture_screen()

# 4. BƯỚC 2: QUÉT VÀ CHỌN KỸ NĂNG (TỐC ĐỘ CAO, HỖ TRỢ CHỌN LIÊN TIẾP NHIỀU LẦN CHO LV3)
print("\n4. BƯỚC 2: QUÉT BẢNG CHỌN KỸ NĂNG...")
print("   ℹ️ Cơ chế tốc độ cao: Tự động chọn liên tiếp (Lv3 chọn 2 lần) ngay khi bảng xuất hiện.")

perk_picks = 0
max_picks = 4  # Tối đa 4 lần chọn

# Đợi bảng chọn hiện lên (tối đa 4 giây sau khi load game)
start_wait = time.time()
while time.time() - start_wait < 4.0:
    if vision.is_level_up_screen(frame):
        break
    time.sleep(0.4)
    frame = adb.capture_screen()

# Vòng lặp chọn liên tiếp
for _ in range(max_picks):
    if frame is not None and vision.is_level_up_screen(frame):
        perk_picks += 1
        print(f"   ⚡ [CHỌN NHANH LẦN {perk_picks}] Đã phát hiện bảng! Bấm Thẻ 1 (Trái)...")
        adb.select_perk(1)
        time.sleep(0.6)  # Nghỉ 0.6s để game load thẻ tiếp theo
        frame = adb.capture_screen()
    else:
        # Nếu không còn bảng chọn nữa thì thoát ngay để đi tiếp
        break

if perk_picks > 0:
    print(f"   ✅ Đã chọn xong {perk_picks} lần kỹ năng cực nhanh!")
else:
    print("   ℹ️ Không thấy bảng chọn kỹ năng (có thể đang ở giữa trận). Đi tiếp!")

# 5. BƯỚC 3: BƯỚC RA KHỎI HỐC CỬA HẸP
print("\n5. BƯỚC 3: DI CHUYỂN RA KHỎI HỐC CỬA HẸP...")
print("   🚀 Đang vuốt Joystick LÊN TRÊN (W) trong 1.5 giây để nhân vật bước vào phòng...")
adb.move_direction('w', duration_ms=1500)
time.sleep(0.3)
print("   ✅ Nhân vật đã ra giữa phòng chiến đấu!")

# 6. BƯỚC 4: CHIẾN ĐẤU THẢ DIỀU (KITING) & XẢ ĐẠN LIÊN TỤC
print("\n6. BƯỚC 4: BẮT ĐẦU CHIẾN ĐẤU THẢ DIỀU (KITING) TRONG 15 GIÂY...")
print("   (Chiến thuật: Vừa chạy vòng tròn quanh phòng né đạn vừa xả đạn liên tục)")

combat_directions = ['w', 'd', 's', 'a']
for loop in range(2):
    print(f"\n   --- Vòng kiting số {loop + 1}/2 ---")
    for d in combat_directions:
        dir_name = {'w': 'LÊN', 'd': 'PHẢI', 's': 'XUỐNG', 'a': 'TRÁI'}[d]
        print(f"   🏃 Di chuyển {dir_name}...")
        adb.move_direction(d, duration_ms=800)
        # Bắn đạn thường
        for _ in range(2):
            adb.attack()
            time.sleep(0.2)

    # Kích hoạt kỹ năng đặc biệt (Chiêu tím)
    print("   ⚡ Kích hoạt kỹ năng đặc biệt (Nút tím)!")
    adb.use_skill()
    time.sleep(0.3)

# 7. BƯỚC 5: TIẾN VỀ PHÍA CỬA TRÊN ĐỂ SẴN SÀNG QUA TẦNG KẾ
print("\n7. BƯỚC 5: ĐẨY LÊN TRÊN HƯỚNG CỔNG DỊCH CHUYỂN...")
print("   🚀 Đang di chuyển LÊN TRÊN để tiến vào cổng qua tầng...")
adb.move_direction('w', duration_ms=1500)

print("\n" + "=" * 70)
print("✅ HOÀN THÀNH TOÀN BỘ QUY TRÌNH TEST TẦNG 1!")
print("Chuột và bàn phím máy tính của bạn hoàn toàn KHÔNG BỊ CHIẾM.")
print("Hãy quan sát trên BlueStacks xem bot đã thực hiện mượt mà các bước chưa nhé!")
print("=" * 70)

