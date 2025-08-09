from PIL import Image, ImageDraw, ImageFont

from PySide6.QtWidgets import QVBoxLayout, QLabel, QDialog
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QImage

from python.utility.colors import BLACK, WHITE
from python.utility.settings import DEFAULT_FPS

class PlayerWindow(QDialog):
    def __init__(self, frames, durations, numbers, descriptions, fps=DEFAULT_FPS, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Storyboard Playback")
        self.fps = fps
        self.frames = frames
        self.numbers = numbers
        self.durations = durations
        self.descriptions = descriptions
        self.current_index = 0
        self.elapsed_ms = 0

        self.resize(960, 540)

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

        self.current_image = None

        self.start_playback()

    def start_playback(self):
        self.current_index = 0
        self.elapsed_ms = 0
        self.show_frame(self.current_index)
        self.timer.start(40)

    def update_frame(self):
        if self.current_index >= len(self.frames):
            self.timer.stop()
            return

        f = self.durations[self.current_index]
        total_ms = int((f / self.fps) * 1000)

        if total_ms <= 0:
            self.current_index += 1
            self.elapsed_ms = 0
            if self.current_index < len(self.frames):
                self.show_frame(self.current_index)
            return

        self.elapsed_ms += 40

        if self.elapsed_ms >= total_ms:
            self.current_index += 1
            self.elapsed_ms = 0
            if self.current_index < len(self.frames):
                self.show_frame(self.current_index)
            else:
                self.timer.stop()
                return

        self.update_timecode_display()

    def show_frame(self, index):
        pil_image = self.frames[index]
        target_w, target_h = self.width(), self.height()
        target_ratio = 16 / 9
        new_h = target_h
        new_w = int(new_h * target_ratio)
        if new_w > target_w:
            new_w = target_w
            new_h = int(new_w / target_ratio)

        img_resized = pil_image.resize((new_w, new_h), Image.LANCZOS).convert("RGBA")

        self.current_image = img_resized
        self.elapsed_ms = 0
        self.update_timecode_display(force=True)

        bg = Image.new("RGBA", (target_w, target_h), BLACK)

        if pil_image:
            img_ratio = pil_image.width / pil_image.height
            if img_ratio > target_ratio:
                new_w = target_w
                new_h = int(target_w / img_ratio)
            else:
                new_h = target_h
                new_w = int(target_h * img_ratio)

            resized_img = pil_image.resize((new_w, new_h), Image.LANCZOS)
            x_offset = (target_w - new_w) // 2
            y_offset = (target_h - new_h) // 2
            bg.paste(resized_img, (x_offset, y_offset))
        else:
            # blank black frame
            pass

        # Draw storyboard number on top-left
        draw = ImageDraw.Draw(bg)
        font_size = max(10, target_h // 20)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        text = f"Cut no. {self.numbers[index]}"
        margin = 10
        text_pos = (margin, margin)
        shadow_color = BLACK
        text_color = WHITE

        for offset in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            pos = (text_pos[0] + offset[0], text_pos[1] + offset[1])
            draw.text(pos, text, font=font, fill=shadow_color)

        draw.text(text_pos, text, font=font, fill=text_color)

        self.current_image = bg
        self.elapsed_ms = 0  # reset timecode count on new frame
        self.update_timecode_display(force=True)


    def update_timecode_display(self, force=False):
        if not self.current_image:
            return

        img = self.current_image.copy()
        draw = ImageDraw.Draw(img)

        font_size = max(24, img.height // 20)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        f = self.durations[self.current_index]
        total_ms = int((f / self.fps) * 1000)
        elapsed_ms = min(self.elapsed_ms, total_ms)
        elapsed_sec = elapsed_ms // 1000
        elapsed_frame = int((elapsed_ms % 1000) / (1000 / self.fps))

        timecode_text = f"{elapsed_sec:02d}s + {elapsed_frame:02d}f"
        margin = img.height // 30
        x = margin
        y = img.height - margin - font_size

        shadow_color = BLACK
        text_color = WHITE

        for offset in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
            draw.text((x + offset[0], y + offset[1]), timecode_text, font=font, fill=shadow_color)
        draw.text((x, y), timecode_text, font=font, fill=text_color)

        # Draw description bottom-left aligned left
        description = self.descriptions[self.current_index]
        if description:
            desc_font_size = max(18, img.height // 30)
            try:
                desc_font = ImageFont.truetype("arial.ttf", desc_font_size)
            except IOError:
                desc_font = ImageFont.load_default()

            desc_margin = 15
            # Get bounding box: (left, top, right, bottom)
            bbox = desc_font.getbbox(description)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            desc_pos = (img.width - desc_margin - text_width, img.height - desc_margin - text_height)

            # Draw shadow for readability
            for offset in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                pos = (desc_pos[0] + offset[0], desc_pos[1] + offset[1])
                draw.text(pos, description, font=desc_font, fill=shadow_color)

            # Draw main text
            draw.text(desc_pos, description, font=desc_font, fill=text_color)
            data = img.tobytes("raw", "RGBA")
            qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimg)
            self.label.setPixmap(pixmap.scaled(self.label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def render_frame_for_export(self, index):
        pil_image = self.frames[index]
        target_w, target_h = 1920, 1080  # fixed export size
        target_ratio = 16 / 9

        bg = Image.new("RGBA", (target_w, target_h), BLACK)

        if pil_image:
            img_ratio = pil_image.width / pil_image.height
            if img_ratio > target_ratio:
                new_w = target_w
                new_h = int(target_w / img_ratio)
            else:
                new_h = target_h
                new_w = int(target_h * img_ratio)
            resized_img = pil_image.resize((new_w, new_h), Image.LANCZOS)
            x_offset = (target_w - new_w) // 2
            y_offset = (target_h - new_h) // 2
            bg.paste(resized_img, (x_offset, y_offset))

        draw = ImageDraw.Draw(bg)

        # Draw storyboard number
        font_size = max(24, target_h // 20)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        text = f"#{self.numbers[index]}"
        margin = 10
        text_pos = (margin, margin)
        shadow_color = BLACK
        text_color = WHITE

        for offset in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            pos = (text_pos[0] + offset[0], text_pos[1] + offset[1])
            draw.text(pos, text, font=font, fill=shadow_color)
        draw.text(text_pos, text, font=font, fill=text_color)

        # Draw description bottom-right
        description = self.descriptions[index] if hasattr(self, "descriptions") else ""
        if description:
            desc_font_size = max(18, target_h // 30)
            try:
                desc_font = ImageFont.truetype("arial.ttf", desc_font_size)
            except IOError:
                desc_font = ImageFont.load_default()
            desc_w, desc_h = draw.textsize(description, font=desc_font)
            desc_pos = (target_w - desc_w - 15, target_h - desc_h - 15)
            for offset in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                pos = (desc_pos[0] + offset[0], desc_pos[1] + offset[1])
                draw.text(pos, description, font=desc_font, fill=shadow_color)
            draw.text(desc_pos, description, font=desc_font, fill=text_color)

        return bg
