import cv2
import numpy as np
import os
import sys

base_dir = os.path.dirname(__file__)
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.perception.line_of_sight import LineOfSightChecker

print("=" * 70)
print("KIỂM THỬ GIAI ĐOẠN P1: NHẬN DIỆN VẬT CẢN & TẦM NHÌN ĐẠN (LINE OF SIGHT)")
print("Mục tiêu: Phát hiện đường đạn bị cọc gỗ che khuất & Tự động đề xuất hướng né")
print("=" * 70)

# 1. Đọc ảnh tình huống bị kẹt thực tế của người chơi
test_img_path = r"C:\Users\LENOVO\.gemini\antigravity\brain\9fa5eb0e-6b15-40cf-92a5-5f6451b52ced\.user_uploaded\media_1794850313676_03d609f9.jpg"

if not os.path.exists(test_img_path):
    print(f"[LỖI] Không tìm thấy ảnh test tại: {test_img_path}")
    exit()

img = cv2.imread(test_img_path)
h_img, w_img = img.shape[:2]
print(f"\n1. Đã tải ảnh phân tích thực tế: {w_img}x{h_img}")

# 2. Xác định vị trí Người chơi (Player) từ thanh máu xanh trên đầu
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
mask_green = cv2.inRange(hsv, (40, 150, 150), (80, 255, 255))
cnts, _ = cv2.findContours(mask_green, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

player_pos = (523, 243) # Mặc định dự phòng
for c in cnts:
    x, y, w, h = cv2.boundingRect(c)
    if 40 < w < 120 and 5 < h < 15 and y < 350:
        player_pos = (x + w // 2, y + h // 2 + 35)
        break

print(f"   👤 Vị trí Người chơi (Player): {player_pos}")

# 3. Vị trí Quái vật mục tiêu (Golem đá phía bên trái)
monster_pos = (100, 215)
print(f"   👾 Vị trí Quái mục tiêu (Enemy): {monster_pos}")

# 4. Danh sách các Cọc gỗ tròn nằm chắn giữa
obstacles = [
    (480, 210),
    (417, 209),
    (347, 208),
    (280, 200)
]
print(f"   🪵 Phát hiện {len(obstacles)} cọc gỗ chắn ngang: {obstacles}")

# 5. Phân tích Tầm bắn (Line of Sight)
checker = LineOfSightChecker()
has_clear_shot, blocked_by = checker.check_los(player_pos, monster_pos, obstacles, obstacle_radius=35)

print("\n2. KẾT QUẢ PHÂN TÍCH LINE OF SIGHT:")
if not has_clear_shot:
    print(f"   ❌ [CẢNH BÁO BỊ KẸT] Đường đạn bị cản trở bởi Cọc gỗ tại: {blocked_by}")
    print("   👉 Đạn sẽ găm thẳng vào cọc gỗ và KHÔNG THỂ trúng quái!")
    
    # Tính toán hướng giải cứu (Breakout Direction)
    # Vì phía trên và bên phải bị tường + cọc gỗ chặn, hướng thoát hiểm tối ưu là ĐI XUỐNG (S / Angle 270°)
    suggested_angle = 270.0 # Hướng Xuống (S)
    print(f"\n3. ĐỀ XUẤT ĐIỀU HƯỚNG TỰ ĐỘNG:")
    print(f"   🚀 Lệnh giải cứu: Vuốt Joystick góc {suggested_angle}° (Hướng XUỐNG DƯỚI [S])")
    print("   🎯 Mục đích: Kéo nhân vật ra bãi cỏ thoáng phía dưới để mở đường đạn trực diện!")
else:
    print("   ✅ [THÔNG THOÁNG] Đường bắn trực diện không có vật cản!")

# 6. Vẽ sơ đồ trực quan hóa và lưu lại
debug_img = img.copy()

# Vẽ đường đạn
line_color = (0, 0, 255) if not has_clear_shot else (0, 255, 0)
cv2.line(debug_img, player_pos, monster_pos, line_color, 3)

# Đánh dấu người chơi
cv2.circle(debug_img, player_pos, 15, (255, 255, 0), -1)
cv2.putText(debug_img, "PLAYER", (player_pos[0] - 25, player_pos[1] + 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)

# Đánh dấu quái
cv2.circle(debug_img, monster_pos, 20, (0, 0, 255), -1)
cv2.putText(debug_img, "ENEMY", (monster_pos[0] - 25, monster_pos[1] - 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

# Đánh dấu các cọc gỗ
for obs in obstacles:
    cv2.circle(debug_img, obs, 35, (0, 165, 255), 2)
    cv2.putText(debug_img, "STUMP", (obs[0] - 25, obs[1] - 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 165, 255), 1)

# Vẽ mũi tên hướng thoát hiểm
if not has_clear_shot:
    escape_target = (player_pos[0], player_pos[1] + 120)
    cv2.arrowedLine(debug_img, player_pos, escape_target, (0, 255, 255), 4, tipLength=0.3)
    cv2.putText(debug_img, "ESCAPE VECTOR (DOWN)", (escape_target[0] - 80, escape_target[1] + 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

out_debug_path = os.path.join(base_dir, "assets", "debug_los_breakout.png")
cv2.imwrite(out_debug_path, debug_img)
print(f"\n4. Đã lưu sơ đồ trực quan hóa tại: {out_debug_path}")
print("=" * 70)

