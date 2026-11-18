import os
import re
import json
import shutil
import numpy as np
from PIL import Image, ImageGrab

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import pytesseract
except ImportError:
    pytesseract = None


class VisionEngine:
    """
    VisionEngine chịu trách nhiệm:
    - Chụp màn hình BlueStacks / toàn màn hình
    - Đọc % thanh máu (HP bar) bằng kỹ thuật dải màu HSV và đo độ dài thanh đỏ
    - Nhận diện màn hình Lên Cấp (Level Up) & 3 kỹ năng lựa chọn qua Template Matching
    - Nhận diện số Tầng hiện tại qua OCR (pytesseract)
    - Nhận diện màn hình Kết thúc trận / Nhận rương
    - Nhận diện màn hình Sảnh Chờ (Lobby) & vị trí Nút Bắt Đầu / Tiếp Tục màu vàng
    """

    def __init__(self, config_path=None, assets_dir=None):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        self.config_path = config_path or os.path.join(base_dir, "config", "settings.json")
        self.assets_dir = assets_dir or os.path.join(base_dir, "assets")
        self.settings = self._load_settings()

        # Cấu hình đường dẫn tesseract nếu có
        tesseract_exe = self.settings.get("ocr_tesseract_path", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        self.ocr_available = False
        if pytesseract:
            if os.path.exists(tesseract_exe):
                pytesseract.pytesseract.tesseract_cmd = tesseract_exe
                self.ocr_available = True
            elif shutil.which(tesseract_exe):
                pytesseract.pytesseract.tesseract_cmd = shutil.which(tesseract_exe)
                self.ocr_available = True
            if not self.ocr_available:
                print("[VisionEngine] Không tìm thấy Tesseract OCR; không đọc được số tầng và bộ đếm mảnh xanh.")

        # Cache ảnh mẫu
        self.templates = {}
        self._load_templates()

        # Tọa độ chuẩn trên độ phân giải 1920x1080 (tự động co giãn theo tỉ lệ màn hình thực tế)
        # HP bar: x: 140 -> 350, y: 135 -> 170
        # Floor text: x: 275 -> 580, y: 60 -> 110
        self.ref_width = 1920
        self.ref_height = 1080

    def _load_settings(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[VisionEngine] Lỗi đọc settings: {e}")
        return {}

    def _load_templates(self):
        if not cv2 or not os.path.exists(self.assets_dir):
            return
        for file in os.listdir(self.assets_dir):
            if file.lower().endswith((".png", ".jpg", ".jpeg")):
                name = os.path.splitext(file)[0]
                img_path = os.path.join(self.assets_dir, file)
                img = cv2.imread(img_path, cv2.IMREAD_COLOR)
                if img is not None:
                    self.templates[name] = img
        print(f"[VisionEngine] Đã tải {len(self.templates)} ảnh mẫu từ thư mục assets.")

    def capture_screen(self, bbox=None):
        """
        Chụp màn hình (hoặc vùng bbox = (left, top, right, bottom)).
        Trả về ảnh numpy BGR (cho OpenCV) và PIL Image.
        """
        screenshot = ImageGrab.grab(bbox=bbox)
        frame_rgb = np.array(screenshot)
        if cv2 is not None:
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        else:
            frame_bgr = frame_rgb
        return frame_bgr, screenshot

    def match_template(self, image, template_name, threshold=0.75):
        """
        Tìm ảnh mẫu template_name trong image bằng cv2.matchTemplate.
        Trả về (found: bool, max_val: float, (max_x, max_y))
        """
        if cv2 is None or template_name not in self.templates:
            return False, 0.0, (0, 0)

        template = self.templates[template_name]
        
        # Co giãn template nếu kích thước ảnh tương đương toàn màn hình (không co giãn trên ROI nhỏ)
        h_img, w_img = image.shape[:2]
        if w_img >= 1200 and (w_img != self.ref_width or h_img != self.ref_height):
            scale_x = w_img / self.ref_width
            scale_y = h_img / self.ref_height
            new_w = max(1, int(template.shape[1] * scale_x))
            new_h = max(1, int(template.shape[0] * scale_y))
            template_scaled = cv2.resize(template, (new_w, new_h))
        else:
            template_scaled = template

        if template_scaled.shape[0] > image.shape[0] or template_scaled.shape[1] > image.shape[1]:
            return False, 0.0, (0, 0)

        res = cv2.matchTemplate(image, template_scaled, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val >= threshold:
            return True, max_val, max_loc
        return False, max_val, max_loc

    def find_lobby_start_button(self, image):
        """
        Tìm nút vàng 'Bắt Đầu' hoặc 'Tiếp Tục' ở sảnh chờ để tự động vào trận.
        Hỗ trợ cả 2 trạng thái:
        - 'Bắt Đầu' (khi bắt đầu lượt mới từ tầng 1)
        - 'Tiếp Tục' (khi tiếp tục ván đấu dang dở)
        Trả về: (found: bool, (click_x, click_y))
        """
        if cv2 is None:
            return False, None

        h, w = image.shape[:2]

        # Lớp 1: Template Matching với cả 2 mẫu nút: sample_btn_batdau và sample_start_btn
        for tmpl_name in ["sample_btn_batdau", "sample_start_btn", "sample_btn_batdau_1080"]:
            if tmpl_name in self.templates:
                template = self.templates[tmpl_name]
                # Co dãn template về tỉ lệ kích thước ảnh chụp
                scale_x = w / 1024 if template.shape[1] < 300 else w / self.ref_width
                scale_y = h / 473 if template.shape[0] < 80 else h / self.ref_height
                t_w = max(1, int(template.shape[1] * scale_x))
                t_h = max(1, int(template.shape[0] * scale_y))
                if t_w < w and t_h < h:
                    t_scaled = cv2.resize(template, (t_w, t_h))
                    res = cv2.matchTemplate(image, t_scaled, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    if max_val >= 0.75:
                        click_x = max_loc[0] + t_w // 2
                        click_y = max_loc[1] + t_h // 2
                        return True, (click_x, click_y)

        # Lớp 2: Quét dải màu vàng nút bấm ở khu vực đáy màn hình (y: 75% -> 98%, x: 30% -> 70%)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (18, 120, 150), (35, 255, 255))
        roi_mask = np.zeros_like(mask)
        roi_mask[int(h * 0.75):int(h * 0.98), int(w * 0.30):int(w * 0.70)] = mask[int(h * 0.75):int(h * 0.98), int(w * 0.30):int(w * 0.70)]

        contours, _ = cv2.findContours(roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            # Nút bấm là hình chữ nhật rộng nằm ngang
            if bw > w * 0.15 and bh > h * 0.05:
                click_x = x + bw // 2
                click_y = y + bh // 2
                return True, (click_x, click_y)

        return False, None

    def get_hp_percentage(self, image):
        """
        Đo % máu thực tế bằng cách kiểm tra chiều dài phần màu hồng/đỏ của thanh HP.
        Chuẩn tọa độ trên 1920x1080: x: 140 -> 350, y: 135 -> 170.
        """
        if cv2 is None:
            return 100.0

        h, w = image.shape[:2]
        x1 = int(w * (140 / self.ref_width))
        x2 = int(w * (350 / self.ref_width))
        y1 = int(h * (135 / self.ref_height))
        y2 = int(h * (170 / self.ref_height))

        hp_crop = image[y1:y2, x1:x2]
        if hp_crop.size == 0:
            return 100.0

        # Lọc màu đỏ / hồng tím (dải máu) trong không gian HSV
        hsv = cv2.cvtColor(hp_crop, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(hsv, np.array([150, 80, 80]), np.array([180, 255, 255]))
        mask2 = cv2.inRange(hsv, np.array([0, 80, 80]), np.array([15, 255, 255]))
        mask = mask1 | mask2

        # Kiểm tra các cột có chứa điểm ảnh màu máu
        col_has_red = np.any(mask > 0, axis=0)
        filled_width = np.sum(col_has_red)
        total_width = hp_crop.shape[1]

        if total_width == 0:
            return 100.0

        percent = (filled_width / total_width) * 100.0
        return min(100.0, max(0.0, percent))

    def detect_floor_number(self, image):
        """
        Đọc số tầng hiện tại từ góc trên trái ("Đảo Nấm Tầng [X]").
        Chuẩn tọa độ 1920x1080: x: 275 -> 580, y: 60 -> 110.
        """
        h, w = image.shape[:2]
        x1 = int(w * (275 / self.ref_width))
        x2 = int(w * (580 / self.ref_width))
        y1 = int(h * (60 / self.ref_height))
        y2 = int(h * (110 / self.ref_height))

        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        # 1. Nếu có tesseract OCR
        if pytesseract is not None and getattr(self, "ocr_available", True):
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if cv2 else crop
            if cv2:
                _, thresh = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY)
            else:
                thresh = gray
            try:
                text = pytesseract.image_to_string(thresh, config="--psm 6")
                match = re.search(r'(?:Tầng|Tang|Floor|F)?\s*[:\.]?\s*(\d+)', text, re.IGNORECASE)
                if match:
                    floor = int(match.group(1))
                    if 1 <= floor <= 150:
                        return floor
            except Exception:
                pass

        return None

    def detect_shard_count(self, image, is_lobby=False):
        """Read the persistent blue-shard counter in the upper-right HUD."""
        if (pytesseract is None or not getattr(self, "ocr_available", True)
                or image is None or image.size == 0):
            return None
        h, w = image.shape[:2]
        # The game HUD places the in-run counter at the upper right. In the
        # lobby, the currency row is centered farther left; keep the two ROIs
        # separate so the OCR cannot read the green-gem total as blue shards.
        if is_lobby:
            x1, x2 = 0.715, 0.78
            threshold, page_mode = 145, 8
        else:
            x1, x2 = 0.885, 0.995
            # In the battle HUD the white digits have a thick dark outline;
            # a higher threshold and single-line OCR preserve strokes like 1.
            threshold, page_mode = 190, 7
        roi = image[:int(h * 0.10), int(w * x1):int(w * x2)]
        if roi.size == 0:
            return None
        try:
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if cv2 is not None else roi
            enlarged = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC) if cv2 is not None else gray
            _, binary = cv2.threshold(enlarged, threshold, 255, cv2.THRESH_BINARY) if cv2 is not None else (None, enlarged)
            text = pytesseract.image_to_string(
                binary, config=f"--psm {page_mode} -c tessedit_char_whitelist=0123456789"
            )
            digits = re.sub(r"\D", "", text)
            return int(digits) if digits else None
        except Exception:
            return None

    def is_level_up_screen(self, image):
        """
        Kiểm tra màn hình lên cấp (dải băng 'Lần này mạo hiểm tăng đến' hoặc 3 thẻ kỹ năng).
        Độ chính xác mẫu đạt 1.000 với threshold 0.70.
        """
        found, val, _ = self.match_template(image, "sample_level_up", threshold=0.70)
        if found:
            return True
            
        # Dự phòng: Kiểm tra sự xuất hiện của các viền tròn trắng của 3 thẻ chọn kỹ năng
        # Vùng y: 600..800, x: 650..1250
        if cv2 is not None and image is not None:
            h, w = image.shape[:2]
            roi = image[int(h * 0.55):int(h * 0.78), int(w * 0.35):int(w * 0.65)]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            white_pixels = np.sum(gray > 220)
            # Khi 3 thẻ kỹ năng hiện ra, tổng số điểm ảnh trắng của viền tròn > 2000
            if white_pixels > 1800:
                return True

        return False

    def is_end_battle_screen(self, image):
        """
        Kiểm tra màn hình kết thúc trận (Chiến đấu kết thúc / Nút Kết Thúc).
        Chỉ kiểm tra nút kết thúc ở vùng góc phải dưới màn hình (ROI),
        tránh nhận diện nhầm thanh máu/thông tin ở góc trên hoặc sảnh chờ.
        """
        if cv2 is None or image is None or image.size == 0:
            return False

        h, w = image.shape[:2]

        # The banner is the strongest signal and avoids mistaking other yellow
        # buttons (settings, shop, continue) for the battle-end screen.
        roi_top_center = image[int(h * 0.10):int(h * 0.60), int(w * 0.20):int(w * 0.80)]
        found_end, _, _ = self.match_template(roi_top_center, "sample_end_battle", threshold=0.75)
        if found_end:
            return True

        # Fall back to a template match only when it lands in the end button's
        # expected lower-right location. Color contours alone are not enough.
        x0, y0 = int(w * 0.64), int(h * 0.76)
        button_roi = image[y0:, x0:int(w * 0.99)]
        for name in ("sample_btn_ketthuc", "sample_btn_ketthuc_user"):
            found, _, loc = self.match_template(button_roi, name, threshold=0.72)
            if found:
                template = self.templates.get(name)
                tw, th = template.shape[1], template.shape[0]
                cx, cy = x0 + loc[0] + tw // 2, y0 + loc[1] + th // 2
                if 0.68 * w <= cx <= 0.98 * w and 0.78 * h <= cy <= 0.99 * h:
                    return True

        return False

    def find_end_battle_button(self, image):
        """
        Tìm tọa độ chính xác của nút Kết Thúc màu vàng ở góc phải dưới.
        Trả về (found: bool, (x, y))
        """
        if cv2 is None or image is None or image.size == 0:
            return False, (1390, 1000)

        h, w = image.shape[:2]
        roi_y0 = int(h * 0.76)
        roi_x0 = int(w * 0.64)
        roi_x1 = int(w * 0.99)
        roi = image[roi_y0:, roi_x0:roi_x1]

        # 1. Template matching với sample_btn_ketthuc trong ROI góc phải dưới
        for tpl_name in ["sample_btn_ketthuc", "sample_btn_ketthuc_user"]:
            found, val, loc = self.match_template(roi, tpl_name, threshold=0.66)
            if found:
                tpl = self.templates.get(tpl_name)
                tw = tpl.shape[1] if tpl is not None else 140
                th = tpl.shape[0] if tpl is not None else 70
                center = (roi_x0 + loc[0] + tw // 2, roi_y0 + loc[1] + th // 2)
                if 0.68 * w <= center[0] <= 0.98 * w and 0.78 * h <= center[1] <= 0.99 * h:
                    return True, center

        # 2. Phát hiện theo hình khối nút vàng hình chữ nhật bo tròn ở góc phải dưới
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask_yellow = cv2.inRange(hsv, (15, 140, 140), (35, 255, 255))
        cnts, _ = cv2.findContours(mask_yellow, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for c in cnts:
            bx, by, bw, bh = cv2.boundingRect(c)
            # Nút Kết Thúc là hình chữ nhật ngang (aspect ratio >= 1.6)
            if bh > 0 and (bw / float(bh)) >= 1.6:
                if bw > int(80 * w / 1920) and bh > int(30 * h / 1080):
                    cx = roi_x0 + bx + bw // 2
                    cy = roi_y0 + by + bh // 2
                    dist = ((cx / w - 0.80) ** 2 + (cy / h - 0.92) ** 2) ** 0.5
                    if 0.68 * w <= cx <= 0.98 * w and 0.78 * h <= cy <= 0.99 * h:
                        candidates.append((dist, cx, cy))

        if candidates:
            _, cx, cy = min(candidates)
            return True, (cx, cy)

        default_x = int(w * (1390 / self.ref_width))
        default_y = int(h * (1000 / self.ref_height))
        return False, (default_x, default_y)

    def find_portal(self, image, player_pos=None, previous_portal=None):
        """
        Tìm cổng dịch chuyển màu vàng rực rỡ ở tường đối diện khi đã dọn sạch quái.
        Hỗ trợ toàn bộ bề ngang màn hình (xử lý khi camera trôi dạt theo nhân vật).
        Trả về (found: bool, (portal_x, portal_y))
        """
        if cv2 is None or image is None or image.size == 0:
            return False, None

        h, w = image.shape[:2]
        roi = image[:int(h * 0.65), :]

        # Prefer a previously tracked portal when more than one bright match is
        # present; choosing only the global maximum can jump between effects.
        template_candidates = []
        for tpl_name in ["sample_portal_actual", "sample_portal"]:
            if tpl_name in self.templates and self.templates[tpl_name] is not None:
                tpl = self.templates[tpl_name]
                if tpl.shape[0] <= roi.shape[0] and tpl.shape[1] <= roi.shape[1]:
                    res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
                    _, max_v, _, max_l = cv2.minMaxLoc(res)
                    if max_v >= 0.72:
                        cx = max_l[0] + tpl.shape[1] // 2
                        cy = max_l[1] + tpl.shape[0] // 2
                        far_from_player = player_pos is None or np.hypot(
                            cx - player_pos[0], cy - player_pos[1]
                        ) >= 150
                        if far_from_player:
                            template_candidates.append((float(max_v), cx, cy))

        if template_candidates:
            if previous_portal is not None:
                px, py = previous_portal
                nearest = min(template_candidates,
                              key=lambda c: (c[1] - px) ** 2 + (c[2] - py) ** 2)
                if (nearest[1] - px) ** 2 + (nearest[2] - py) ** 2 <= 260 ** 2:
                    return True, (nearest[1], nearest[2])
            _, cx, cy = max(template_candidates, key=lambda c: c[0])
            return True, (cx, cy)

        # 2. Lớp dự phòng: Bắt buộc có cả quầng sáng VÀNG và lõi CYAN
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask_gold = cv2.inRange(hsv, (18, 140, 190), (35, 255, 255))
        # Portal core in the captured game is pale cyan (low saturation), not
        # the saturated cyan used by the mana HUD.
        mask_cyan = cv2.inRange(hsv, (75, 20, 210), (105, 180, 255))

        # Do not blanket-mask the upper-left: the portal can appear behind the
        # floor label/HUD at different camera positions. HUD bars alone fail
        # the large gold-rim + pale-cyan-core shape checks below.
        mask_gold[:int(h * 0.15), int(w * 0.75):] = 0
        mask_cyan[:int(h * 0.15), int(w * 0.75):] = 0

        # Cổng mở thật sự phải có cả ánh vàng bao quanh và lõi phát sáng
        if cv2.countNonZero(mask_gold) > 100 and cv2.countNonZero(mask_cyan) > 50:
            mask_combined = cv2.bitwise_or(mask_gold, mask_cyan)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            mask_combined = cv2.morphologyEx(mask_combined, cv2.MORPH_CLOSE, kernel)
            cnts, _ = cv2.findContours(mask_combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            scale = w / 1920.0
            min_area = int(500 * (scale ** 2))
            candidates = []
            for c in cnts:
                area = cv2.contourArea(c)
                if area > min_area:
                    bx, by, bw, bh = cv2.boundingRect(c)
                    aspect = bw / float(max(1, bh))
                    # A portal is a tall, bright doorway-sized object. Reject
                    # small gold/cyan ability effects around the player.
                    min_w = int(60 * scale)
                    min_h = int(80 * scale)
                    cx, cy = bx + bw // 2, by + bh // 2
                    far_from_player = (
                        player_pos is None or np.hypot(cx - player_pos[0], cy - player_pos[1]) >= 150
                    )
                    if (bw >= min_w and bh >= min_h and 0.45 <= aspect <= 1.25
                            and 0.04 * h <= cy <= 0.64 * h and far_from_player):
                        shape_score = area / (1.0 + abs(aspect - 0.78))
                        candidates.append((shape_score, cx, cy))

            if candidates:
                if previous_portal is not None:
                    px, py = previous_portal
                    nearest = min(candidates,
                                  key=lambda c: (c[1] - px) ** 2 + (c[2] - py) ** 2)
                    if (nearest[1] - px) ** 2 + (nearest[2] - py) ** 2 <= 260 ** 2:
                        return True, (nearest[1], nearest[2])
                _, cx, cy = max(candidates, key=lambda c: c[0])
                return True, (cx, cy)

        return False, None
