import time
import os
import sys

# Đảm bảo đường dẫn import
base_dir = os.path.dirname(__file__)
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.engine_adb import ADBController

print("=" * 65)
print("TEST ĐIỀU KHIỂN CHẠY NGẦM QUA ADB (100% BACKGROUND)")
print("Đặc điểm: KHÔNG CHIẾM CHUỘT, KHÔNG CHIẾM BÀN PHÍM!")
print("Bạn có thể gõ phím hoặc làm việc trên màn hình chính thoải mái.")
print("=" * 65)

adb = ADBController()

print("\n1. Đang khởi tạo ADB daemon và kiểm tra kết nối...")

# Bước 1: Khởi tạo daemon trước
if not adb.ensure_connection():
    print("[LỖI] Lần 1 thất bại, thử lại sau 3 giây...")
    time.sleep(3)
    if not adb.ensure_connection():
        print("[LỖI] Không thể kết nối tới BlueStacks qua ADB!")
        print("Kiểm tra:")
        print("  - BlueStacks đang chạy?")
        print("  - Settings > Advanced > Android Debug Bridge (ADB) đã BẬT?")
        print("  - Đã nhấn 'Save changes' và restart BlueStacks?")
        exit()

# Bước 2: Lấy kích thước màn hình
res = adb.run_cmd(["shell", "wm", "size"])
if res and res.returncode == 0:
    print(f"✅ Kết nối thành công! {res.stdout.strip()}")
else:
    print("[LỖI] Kết nối nhưng không lấy được kích thước màn hình!")
    exit()

print("\n2. TEST HỒI MÁU (ĐÙI GÀ):")
print(f"-> Đang gửi lệnh bấm Đùi gà tại tọa độ chuẩn {adb.COORD_HEAL}...")
adb.heal()
print("   🍗 [ADB TAP] Đã bấm hồi máu! Kiểm tra số lượng đùi gà hoặc thanh máu trên BlueStacks.")
time.sleep(1.0)

print("\n3. TEST TẤN CÔNG NGẦM:")
print(f"-> Đang gửi 5 đòn bắn thường tại tọa độ {adb.COORD_ATTACK}...")
for i in range(1, 6):
    adb.attack()
    print(f"   🔥 [ADB TAP] Bắn đòn thứ {i}")
    time.sleep(0.3)

print("\n4. TEST DI CHUYỂN NGẦM:")
print("-> Đang vuốt Joystick di chuyển LÊN TRÊN trong 1.5 giây...")
adb.move_direction('w', duration_ms=1500)
print("   🚀 [ADB SWIPE] Hoàn thành di chuyển lên trên!")
time.sleep(0.5)

print("\n-> Đang vuốt Joystick di chuyển SANG PHẢI trong 1.5 giây...")
adb.move_direction('d', duration_ms=1500)
print("   🚀 [ADB SWIPE] Hoàn thành di chuyển sang phải!")

print("\n5. TEST DÙNG KỸ NĂNG:")
adb.use_skill()
print(f"   ⚡ [ADB TAP] Đã kích hoạt kỹ năng đặc biệt tại {adb.COORD_SKILL}!")

print("\n" + "=" * 65)
print("✅ XONG BÀI TEST NGẦM!")
print("Chuột và bàn phím máy tính HOÀN TOÀN TỰ DO trong suốt bài test.")
print("")
print("KẾT QUẢ CẦN KIỂM TRA trên BlueStacks:")
print("  - Nhân vật có bắn 5 phát?")
print("  - Nhân vật có di chuyển lên + sang phải?")
print("  - Kỹ năng có kích hoạt?")
print("  - Đùi gà có được bấm?")
print("")
print("Nếu TẤT CẢ đều OK → Bot ADB sẵn sàng chạy tự động!")
print("=" * 65)
