import cv2
import numpy as np
from PIL import ImageGrab
import time
import os

try:
    import pygetwindow as gw
except ImportError:
    gw = None

print("=" * 65)
print("BÀI TEST SỐ 2: KIỂM TRA THỊ GIÁC (OPENCV)")
print("Mục tiêu: Quét nhận diện Nút Vàng 'Bắt Đầu' hoặc 'Tiếp Tục'")
print("=" * 65)

base_dir = os.path.dirname(__file__)
assets_dir = os.path.join(base_dir, "assets")

# Tải cả 2 mẫu nút: Bắt Đầu & Tiếp Tục
templates = {}
for name in ["sample_btn_batdau", "sample_start_btn"]:
    p = os.path.join(assets_dir, f"{name}.png")
    if os.path.exists(p):
        img = cv2.imread(p, cv2.IMREAD_COLOR)
        if img is not None:
            templates[name] = img
            print(f"[*] Đã tải mẫu nút: {name}.png ({img.shape[1]}x{img.shape[0]})")


def get_bluestacks_bbox():
    if not gw:
        return None
    for w in gw.getAllWindows():
        title = w.title.strip()
        if "bluestacks" in title.lower() and "overlay" not in title.lower() and title != "":
            if w.width > 200 and w.height > 200:
                return (w.left, w.top, w.right, w.bottom), w.title
    return None, None


print("\nĐang quét màn hình liên tục... (Nhấn Ctrl+C để dừng)")
print("=> HÃY MỞ CỬA SỔ BLUESTACKS SẢNH CHỜ LÊN MÀN HÌNH NHÉ!\n")

try:
    while True:
        bbox, win_title = get_bluestacks_bbox()
        if bbox:
            screenshot = ImageGrab.grab(bbox=bbox)
            # print(f"-> Đang chụp trực tiếp từ cửa sổ: '{win_title}' ({bbox[2]-bbox[0]}x{bbox[3]-bbox[1]})")
        else:
            screenshot = ImageGrab.grab()

        img_np = np.array(screenshot)
        frame = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        h, w = frame.shape[:2]

        best_name = ""
        best_val = 0.0
        best_center = (0, 0)

        # 1. So khớp với các ảnh mẫu
        for name, t_img in templates.items():
            t_h, t_w = t_img.shape[:2]
            scale_x = w / 1024 if t_w < 300 else w / 1920
            scale_y = h / 473 if t_h < 80 else h / 1080
            curr_tw = max(1, int(t_w * scale_x))
            curr_th = max(1, int(t_h * scale_y))

            if curr_tw < w and curr_th < h:
                t_scaled = cv2.resize(t_img, (curr_tw, curr_th))
                res = cv2.matchTemplate(frame, t_scaled, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val > best_val:
                    best_val = max_val
                    best_name = name
                    best_center = (max_loc[0] + curr_tw // 2, max_loc[1] + curr_th // 2)

        # 2. Quét dải màu vàng nút bấm ở đáy màn hình (Dự phòng)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (18, 120, 150), (35, 255, 255))
        roi_mask = np.zeros_like(mask)
        roi_mask[int(h * 0.70):int(h * 0.98), int(w * 0.25):int(w * 0.75)] = mask[int(h * 0.70):int(h * 0.98), int(w * 0.25):int(w * 0.75)]
        contours, _ = cv2.findContours(roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        contour_found = False
        contour_center = (0, 0)
        for cnt in contours:
            bx, by, bw, bh = cv2.boundingRect(cnt)
            if bw > w * 0.12 and bh > h * 0.04:
                contour_found = True
                contour_center = (bx + bw // 2, by + bh // 2)
                break

        # Nếu có bbox, tính tọa độ thực trên màn hình
        offset_x = bbox[0] if bbox else 0
        offset_y = bbox[1] if bbox else 0

        label = "Bắt Đầu" if "batdau" in best_name else "Tiếp Tục"
        if best_val >= 0.75:
            screen_x = offset_x + best_center[0]
            screen_y = offset_y + best_center[1]
            print(f"🎯 [THÀNH CÔNG] ĐÃ NHÌN THẤY nút '{label}' tại ({screen_x}, {screen_y}) | Độ khớp: {best_val:.2f}")
        elif contour_found:
            screen_x = offset_x + contour_center[0]
            screen_y = offset_y + contour_center[1]
            print(f"✨ [THÀNH CÔNG] Nhận diện nút Vàng qua màu sắc tại ({screen_x}, {screen_y})")
        else:
            print(f"⏳ Đang tìm... (Mức độ giống cao nhất trên màn hình: {best_val:.2f})")

        time.sleep(1.0)

except KeyboardInterrupt:
    print("\n[!] Đã dừng bài test thị giác.")
