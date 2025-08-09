import io
import sys
import json

from PIL import Image, ImageDraw

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QComboBox, QFileDialog, QMessageBox, QColorDialog,
    QDialog, QSizePolicy, QLineEdit, QMenuBar, QAbstractItemView
)

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage, QAction, QPainter, QIcon

from images import FAVICON

from ctypes import windll

windll.shell32.SetCurrentProcessExplicitAppUserModelID('Ginyoa.Crappy.Storyboard.Planner')

from python.utility.colors import WHITE, BLACK
from python.utility.settings import DEFAULT_FPS, DEFAULT_WIDTH, DEFAULT_HEIGHT

from python.widgets.drawing import DrawingWidget, BigDrawingDialog
from python.widgets.duration import DurationWidget
from python.widgets.playback import PlayerWindow

ROWS_PER_PAGE = 6
COLUMNS = 4
TOTAL_PAGES = 4


def resize_image(image: Image, width: int, height: int) -> QPixmap:
    current_ratio = image.width / image.height
    target_ratio = width / height

    target_width = width if current_ratio > target_ratio else int(height * current_ratio)
    target_height = int(width / current_ratio) if current_ratio > target_ratio else height

    return image.resize((target_width, target_height), Image.LANCZOS).tobytes("raw", "RGBA")

def convert_image_to_qmixmap(image: Image, width: int, height: int) -> QPixmap:
    if image.width != width or image.height != height:
        image = resize_image(image, width, height)

    return QPixmap.fromImage(image, QImage.Format_RGBA8888)

class StoryboardTable(QTableWidget):
    def __init__(self, page_number=1, fps=DEFAULT_FPS, start_number=1, parent=None):
        super().__init__(ROWS_PER_PAGE, COLUMNS, parent)
        self.page_number = page_number
        self.fps = fps
        self.start_number = start_number
        self.duration_widgets = []
        self.uploaded_images = [None] * ROWS_PER_PAGE
        self.draw_widgets = [None] * ROWS_PER_PAGE  # Store drawing widgets if in draw mode
        self.mode = "upload"

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.setHorizontalHeaderLabels(["#", "Storyboard", "Description", "Duration"])
        self.verticalHeader().setVisible(False)

        for row in range(ROWS_PER_PAGE):
            self.setItem(row, 0, self.create_number_item(self.start_number + row))
            self._add_upload_button(row)
            self.setItem(row, 2, QTableWidgetItem(" "))
            self._add_duration_widget(row)

    def create_number_item(self, num):
        item = QTableWidgetItem(str(num))
        item.setFlags(Qt.ItemIsEnabled)
        item.setTextAlignment(Qt.AlignCenter)

        return item

    def update_geometry(self):
        total_width = self.viewport().width() or DEFAULT_WIDTH  # fallback if zero
        total_height = self.viewport().height() or 600

        margin_width = 20
        margin_height = 40

        total_width = max(0, total_width - margin_width)
        total_height = max(0, total_height - margin_height)

        row_height = total_height // ROWS_PER_PAGE
        for row in range(ROWS_PER_PAGE):
            self.setRowHeight(row, row_height)

        col1_width = int(total_width * 0.07)
        storyboard_width = int((16 / 9) * row_height)

        if storyboard_width > total_width - col1_width:
            storyboard_width = total_width - col1_width

        rest_width = total_width - (col1_width + storyboard_width)
        col3_width = int(rest_width * 0.7)
        col4_width = rest_width - col3_width

        self.setColumnWidth(0, col1_width)
        self.setColumnWidth(1, storyboard_width)
        self.setColumnWidth(2, col3_width)
        self.setColumnWidth(3, col4_width)

        # Resize drawing widgets if any
        for dw in self.draw_widgets:
            if dw:
                dw.setFixedSize(storyboard_width, row_height)

    def create_fixed_size_button(self, pixmap=None, row=None):
        btn = QPushButton()
        btn.setProperty("row", row)
        btn.setFlat(True)
        btn.setCheckable(False)  # 🔹 Make sure it's not a toggle button
        btn.setDown(False)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        if pixmap:
            btn.setIcon(pixmap)
            btn.setIconSize(pixmap.size())
            btn.setText("")
        else:
            btn.setText("Upload Image")
        btn.clicked.connect(self.handle_upload_clicked)

        return btn

    def _add_upload_button(self, row):
        self.setCellWidget(row, 1, self.create_fixed_size_button(row=row))

    def _add_duration_widget(self, row):
        dur_widget = DurationWidget()
        dur_widget.DurationChanged.connect(self.notify_parent_to_update_total)
        dur_widget.setFixedSize(self.columnWidth(3) or 80, self.rowHeight(row) or 50)

        self.setCellWidget(row, 3, dur_widget)
        self.duration_widgets.append(dur_widget)

    def notify_parent_to_update_total(self):
        parent = self.parent()
        while parent:
            if hasattr(parent, "update_totals_for_page"):
                parent.update_totals_for_page(self)
                break
            parent = parent.parent()

    def update_page_total_duration(self):
        total_seconds = 0
        total_frames = 0
        for dur_widget in self.duration_widgets:
            f = dur_widget.frames
            total_frames += f

        extra_seconds = total_frames // self.fps
        total_seconds += extra_seconds
        total_frames = total_frames % self.fps
        return total_seconds, total_frames

    def handle_upload_clicked(self):
        button = self.sender()

        if not button:
            return

        button.setDown(False)  # 🔹 reset visual press

        row = button.property("row")
        if row is None:
            return

        if self.mode != "upload":
            # in draw mode, do nothing on upload button clicks
            return

        file_path, _ = QFileDialog.getOpenFileName(self,
                                                   "Select Storyboard Image",
                                                   "",
                                                   "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not file_path:
            return

        pil_img = Image.open(file_path).convert("RGBA")
        self.uploaded_images[row] = pil_img

        cell_width = self.columnWidth(1) or 150
        cell_height = self.rowHeight(row) or 50
        qt_pixmap = resize_image_to_qmixmap(pil_img, cell_width, cell_height)

        img_btn = self.create_fixed_size_button(pixmap=qt_pixmap, row=row)
        img_btn.setFixedSize(cell_width, cell_height)
        img_btn.setToolTip(file_path)
        self.setCellWidget(row, 1, img_btn)

        # Clear draw widget if any
        if self.draw_widgets[row]:
            self.draw_widgets[row].deleteLater()
            self.draw_widgets[row] = None

    def switch_to_draw_mode(self):
        self.mode = "draw"
        # Replace storyboard column widgets with DrawingWidgets or blank if none
        for row in range(ROWS_PER_PAGE):
            if self.draw_widgets[row] is None:
                dw = DrawingWidget(self.columnWidth(1), self.rowHeight(row))
                self.draw_widgets[row] = dw
            else:
                dw = self.draw_widgets[row]
                dw.setFixedSize(self.columnWidth(1), self.rowHeight(row))
            self.setCellWidget(row, 1, self.draw_widgets[row])
            self.uploaded_images[row] = None  # Clear uploaded images in draw mode

    def switch_to_upload_mode(self):
        self.mode = "upload"
        # Replace storyboard column widgets with upload buttons or uploaded image buttons
        for row in range(ROWS_PER_PAGE):
            if self.draw_widgets[row]:
                self.draw_widgets[row].deleteLater()
                self.draw_widgets[row] = None

            if self.uploaded_images[row]:
                pil_img = self.uploaded_images[row]
                cell_width = self.columnWidth(1) or 150
                cell_height = self.rowHeight(row) or 50
                qt_pixmap = resize_image_to_qmixmap(pil_img, cell_width, cell_height)
                img_btn = self.create_fixed_size_button(pixmap=qt_pixmap, row=row)
                img_btn.setFixedSize(cell_width, cell_height)
                self.setCellWidget(row, 1, img_btn)
            else:
                self._add_upload_button(row)

    def mousePressEvent(self, event):
        if self.mode != "draw":
            super().mousePressEvent(event)
            return

        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        index = self.indexAt(pos)
        if not index.isValid():
            super().mousePressEvent(event)
            return

        row = index.row()
        col = index.column()
        if col == 1 and 0 <= row < ROWS_PER_PAGE:
            # Load full-res image from uploaded_images, fallback to blank canvas
            current_img = self.uploaded_images[row]
            if current_img is None:
                current_img = Image.new("RGBA", (DEFAULT_WIDTH, DEFAULT_HEIGHT), WHITE)

            dlg = BigDrawingDialog(
                pil_image=current_img,
                brush_color=self.draw_widgets[row].brush_color if self.draw_widgets[row] else BLACK,
                brush_size=self.draw_widgets[row].brush_size if self.draw_widgets[row] else 5,
                eraser_mode=self.draw_widgets[row].eraser_mode if self.draw_widgets[row] else False,
                parent=self
            )
            if dlg.exec() == QDialog.Accepted:
                new_img = dlg.get_image()

                # Store full-res image for playback/export
                self.uploaded_images[row] = new_img

                # Create thumbnail sized to cell
                thumb_width = self.columnWidth(1)
                thumb_height = self.rowHeight(row)
                thumbnail_img = new_img.resize((thumb_width, thumb_height), Image.LANCZOS)

                # Update or create the draw widget thumbnail
                if self.draw_widgets[row]:
                    self.draw_widgets[row].image = thumbnail_img
                    self.draw_widgets[row].draw = ImageDraw.Draw(self.draw_widgets[row].image)
                    self.draw_widgets[row].update_pixmap()
                else:
                    dw = DrawingWidget(thumb_width, thumb_height)
                    dw.image = thumbnail_img
                    dw.draw = ImageDraw.Draw(dw.image)
                    dw.update_pixmap()
                    self.draw_widgets[row] = dw
                    self.setCellWidget(row, 1, dw)

                # Update draw widget image resized to widget size for thumbnail
                if self.draw_widgets[row]:
                    self.draw_widgets[row].image = new_img.resize(
                        (self.draw_widgets[row].width(), self.draw_widgets[row].height()),
                        Image.LANCZOS
                    )
                    self.draw_widgets[row].draw = ImageDraw.Draw(self.draw_widgets[row].image)
                    self.draw_widgets[row].update_pixmap()
                    # Store full res big image in uploaded_images for player
                    self.uploaded_images[row] = new_img
                else:
                    # Justincase
                    dw = DrawingWidget(self.columnWidth(1), self.rowHeight(row))
                    dw.image = new_img.resize(
                        (dw.width(), dw.height()), Image.LANCZOS)
                    dw.draw = ImageDraw.Draw(dw.image)
                    dw.update_pixmap()
                    self.draw_widgets[row] = dw
                    self.setCellWidget(row, 1, dw)
                    self.uploaded_images[row] = new_img
        else:
            super().mousePressEvent(event)

    def resizeEvent(self, event):
        total_width = self.viewport().width()
        total_height = self.viewport().height()

        margin_width = 20
        margin_height = 40

        total_width = max(0, total_width - margin_width)
        total_height = max(0, total_height - margin_height)

        row_height = total_height // ROWS_PER_PAGE
        for row in range(ROWS_PER_PAGE):
            self.setRowHeight(row, row_height)

        col1_width = int(total_width * 0.07)
        storyboard_width = int((16 / 9) * row_height)

        if storyboard_width > total_width - col1_width:
            storyboard_width = total_width - col1_width

        rest_width = total_width - (col1_width + storyboard_width)
        col3_width = int(rest_width * 0.7)
        col4_width = rest_width - col3_width

        self.setColumnWidth(0, col1_width)
        self.setColumnWidth(1, storyboard_width)
        self.setColumnWidth(2, col3_width)
        self.setColumnWidth(3, col4_width)

        # Resize drawing widgets if any
        for dw in self.draw_widgets:
            if dw:
                dw.setFixedSize(storyboard_width, row_height)

        super().resizeEvent(event)

class StoryboardPlanner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ginyoa\'s Crappy Storyboard Planner")
        self.setWindowIcon(QIcon(FAVICON))

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        # File menu bar
        menubar = QMenuBar()
        self.setMenuBar(menubar)
        file_menu = menubar.addMenu("File")

        save_action = QAction("Save Project", self)
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        load_action = QAction("Load Project", self)
        load_action.triggered.connect(self.load_project)
        file_menu.addAction(load_action)

        export_video_action = QAction("i wouldve made export mp4 but idk how", self)
        file_menu.addAction(export_video_action)

        export_spread_action = QAction("Export Spread (JPG/PNG)", self)
        export_spread_action.triggered.connect(self.export_spread)
        file_menu.addAction(export_spread_action)

        top_bar = QHBoxLayout()
        self.main_layout.addLayout(top_bar)


        # Title box
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Title: Enter storyboard title here...")
        top_bar.addWidget(self.title_edit)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Upload", "Draw"])
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        top_bar.addWidget(QLabel("Modes:"))
        top_bar.addWidget(self.mode_combo)
        top_bar.addStretch()

        top_bar.addWidget(QLabel("@ginyoagoldie 2025"))

        self.spread_layout = QHBoxLayout()
        self.spread_layout.setContentsMargins(0, 0, 0, 0)
        self.spread_layout.setSpacing(10)
        self.main_layout.addLayout(self.spread_layout)

        self.pagination_layout = QHBoxLayout()
        self.pagination_layout.setContentsMargins(0, 0, 0, 0)
        self.pagination_layout.setSpacing(10)
        self.main_layout.addLayout(self.pagination_layout)

        self.prev_btn = QPushButton("Previous")
        self.prev_btn.clicked.connect(self.go_previous)
        self.pagination_layout.addWidget(self.prev_btn)

        self.page_label = QLabel()
        self.page_label.setAlignment(Qt.AlignCenter)
        self.pagination_layout.addWidget(self.page_label, 1)

        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.go_next)
        self.pagination_layout.addWidget(self.next_btn)

        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.play_storyboard)
        self.pagination_layout.addWidget(self.play_btn)

        self.pages = []
        self.page_containers = []
        self.total_labels = []

        for page in self.pages:
           page.update_geometry()

        for i in range(TOTAL_PAGES):
            start_num = i * ROWS_PER_PAGE + 1
            page = StoryboardTable(page_number=i + 1, fps=DEFAULT_FPS, start_number=start_num)
            total_label = QLabel("Total Duration: 0 s + 0 f")
            total_label.setAlignment(Qt.AlignRight)
            total_label.setStyleSheet("font-weight: bold; padding-right: 5px;")

            container = QWidget()
            vlayout = QVBoxLayout(container)
            vlayout.setContentsMargins(0, 0, 0, 0)
            vlayout.setSpacing(2)
            vlayout.addWidget(page)
            vlayout.addWidget(total_label)

            self.pages.append(page)
            self.total_labels.append(total_label)
            self.page_containers.append(container)

        self.current_spread_index = 0
        self.update_view()
        self.resize(1200, 700)

        # Set default mode for all pages
        self.on_mode_changed(self.mode_combo.currentIndex())


    def on_mode_changed(self, index):
        mode_text = self.mode_combo.currentText()
        if "Draw" in mode_text:
            for page in self.pages:
                page.switch_to_draw_mode()
        else:
            for page in self.pages:
                page.switch_to_upload_mode()
        self.update_view()

    def open_color_picker(self):
        color = QColorDialog.getColor()
        if not color.isValid():
            return

        rgba = (color.red(), color.green(), color.blue(), 255)
        self.current_brush_color = rgba
        # Update all drawing widgets brush color
        for page in self.pages:
            for dw in page.draw_widgets:
                if dw:
                    dw.set_brush_color(rgba)

    def brush_size_changed(self, value):
        self.current_brush_size = value
        for page in self.pages:
            for dw in page.draw_widgets:
                if dw:
                    dw.brush_size = value

    def eraser_toggled(self, checked):
        self.eraser_mode = checked
        for page in self.pages:
            for dw in page.draw_widgets:
                if dw:
                    dw.set_eraser_mode(checked)

    def update_view(self):
        for i in reversed(range(self.spread_layout.count())):
            item = self.spread_layout.takeAt(i)
            widget = item.widget()
            if widget:
                widget.hide()

        left_idx = self.current_spread_index * 2
        right_idx = left_idx + 1

        def show_page(idx):
            if idx < 0 or idx >= len(self.page_containers):
                return
            container = self.page_containers[idx]
            s, f = self.pages[idx].update_page_total_duration()
            self.total_labels[idx].setText(f"Total Duration: {s} s + {f} f")
            container.show()
            self.spread_layout.addWidget(container, 1)

        show_page(left_idx)
        show_page(right_idx)

        total_spreads = (len(self.pages) + 1) // 2
        self.page_label.setText(f"Spread {self.current_spread_index + 1} / {total_spreads}")

        self.prev_btn.setEnabled(self.current_spread_index > 0)
        self.next_btn.setEnabled(self.current_spread_index < total_spreads - 1)

    def update_totals_for_page(self, page):
        try:
            idx = self.pages.index(page)
        except ValueError:
            return
        s, f = page.update_page_total_duration()
        self.total_labels[idx].setText(f"Total Duration: {s} s + {f} f")

    def go_previous(self):
        if self.current_spread_index > 0:
            self.current_spread_index -= 1
            self.update_view()

    def go_next(self):
        total_spreads = (len(self.pages) + 1) // 2
        if self.current_spread_index < total_spreads - 1:
            self.current_spread_index += 1
            self.update_view()

    def play_storyboard(self):
        frames = []
        durations = []
        numbers = []
        descriptions = []

        for page in self.pages:
            for i in range(ROWS_PER_PAGE):
                f = page.duration_widgets[i].frames

                # Force a minimum duration if the user hasn't set one
                if f == 0:
                    continue 

                img = page.uploaded_images[i]
                if img is None:
                    img = Image.new("RGBA", (DEFAULT_WIDTH, DEFAULT_HEIGHT), WHITE)

                frames.append(img)
                durations.append((f))
                storyboard_number = page.start_number + i
                numbers.append(storyboard_number)

                # Always add description, even if it's empty
                desc_item = page.item(i, 2)
                descriptions.append(desc_item.text() if desc_item else "")

        if not frames:
            return

        self.player = PlayerWindow(frames, durations, numbers, descriptions, fps=DEFAULT_FPS)
        self.player.show()

    def save_project(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "Storyboard Project (*.json)")
        if not filename:
            return
        if not filename.endswith(".json"):
            filename += ".json"

        data = {
            "title": self.title_edit.text(),
            "pages": []
        }

        for page in self.pages:
            page_data = {"start_number": page.start_number, "mode": page.mode, "rows": []}
            for row in range(ROWS_PER_PAGE):
                s, f = page.duration_widgets[row].frames
                description = page.item(row, 2).text() if page.item(row, 2) else ""
                img_data = None
                if page.uploaded_images[row]:
                    with io.BytesIO() as output:
                        page.uploaded_images[row].save(output, format="PNG")
                        img_bytes = output.getvalue()
                    img_data = img_bytes.hex()
                row_data = {
                    "duration": (s, f),
                    "description": description,
                    "image_data": img_data,
                    "mode": page.mode,
                }
                page_data["rows"].append(row_data)
            data["pages"].append(page_data)

        try:
            with open(filename, "w") as f:
                json.dump(data, f)
            QMessageBox.information(self, "Save Project", "Project saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Save Project", f"Failed to save project:\n{str(e)}")



    def load_project(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "Storyboard Project (*.json)")
        if not filename:
            return

        try:
            with open(filename, "r") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Load Project", f"Failed to load project:\n{str(e)}")
            return

        self.title_edit.setText(data.get("title", ""))

        pages_data = data.get("pages", [])
        for i, page_data in enumerate(pages_data):
            if i >= len(self.pages):
                break
            page = self.pages[i]
            page.start_number = page_data.get("start_number", page.start_number)
            mode = page_data.get("mode", "upload")
            if "draw" in mode:
                page.switch_to_draw_mode()
            else:
                page.switch_to_upload_mode()
            rows = page_data.get("rows", [])
            for row_idx, row_data in enumerate(rows):
                if row_idx >= ROWS_PER_PAGE:
                    break
                s, f = row_data.get("duration", (0, 0))
                page.duration_widgets[row_idx].seconds_edit.setText(str(s))
                page.duration_widgets[row_idx].frames_edit.setText(str(f))
                description = row_data.get("description", "")
                if page.item(row_idx, 2):
                    page.item(row_idx, 2).setText(description)
                else:
                    page.setItem(row_idx, 2, QTableWidgetItem(description))

                img_data_hex = row_data.get("image_data")
                if img_data_hex:
                    img_bytes = bytes.fromhex(img_data_hex)
                    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
                    page.uploaded_images[row_idx] = img
                    if page.mode == "upload":
                        cell_width = page.columnWidth(1) or 150
                        cell_height = page.rowHeight(row_idx) or 50
                        qt_pixmap = resize_image_to_qmixmap(img, cell_width, cell_height)
                        btn = page.create_fixed_size_button(pixmap=qt_pixmap, row=row_idx)
                        btn.setFixedSize(cell_width, cell_height)
                        page.setCellWidget(row_idx, 1, btn)
                    elif page.mode == "draw":
                        dw = DrawingWidget(page.columnWidth(1), page.rowHeight(row_idx))
                        dw.image = img.resize((dw.width(), dw.height()), Image.LANCZOS)
                        dw.draw = ImageDraw.Draw(dw.image)
                        dw.update_pixmap()
                        page.draw_widgets[row_idx] = dw
                        page.setCellWidget(row_idx, 1, dw)
                else:
                    page.uploaded_images[row_idx] = None
                    if page.mode == "upload":
                        page._add_upload_button(row_idx)
                    else:
                        if page.draw_widgets[row_idx] is None:
                            dw = DrawingWidget(page.columnWidth(1), page.rowHeight(row_idx))
                            page.draw_widgets[row_idx] = dw
                            page.setCellWidget(row_idx, 1, dw)

        self.update_view()
        QMessageBox.information(self, "Load Project", "Project loaded successfully.")


    def render_frame_for_export(self, index):
        from PIL import Image, ImageDraw, ImageFont

        pil_image = self.frames[index]
        target_w, target_h = 1920, 1080
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

        # Storyboard number
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

        # Description bottom-right
        description = getattr(self, "descriptions", [""] * len(self.frames))[index]
        if description:
            desc_font_size = max(18, target_h // 30)
            try:
                desc_font = ImageFont.truetype("arial.ttf", desc_font_size)
            except IOError:
                desc_font = ImageFont.load_default()
            desc_w, desc_h = draw.textbbox((0, 0), description, font=desc_font)[2:]
            desc_pos = (target_w - desc_w - 15, target_h - desc_h - 15)
            for offset in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                pos = (desc_pos[0] + offset[0], desc_pos[1] + offset[1])
                draw.text(pos, description, font=desc_font, fill=shadow_color)
            draw.text(desc_pos, description, font=desc_font, fill=text_color)

        return bg

    def export_spread(self):
        left_idx = self.current_spread_index * 2
        right_idx = left_idx + 1

        containers_to_export = []
        if left_idx < len(self.page_containers):
            containers_to_export.append(self.page_containers[left_idx])
        if right_idx < len(self.page_containers):
            containers_to_export.append(self.page_containers[right_idx])

        if not containers_to_export:
            QMessageBox.warning(self, "Export Spread", "No spread to export.")
            return

        filename, filter_ = QFileDialog.getSaveFileName(self, "Export Spread as Image", "", "PNG Image (*.png);;JPEG Image (*.jpg)")
        if not filename:
            return

        # Export both pages in spread horizontally combined
        pixmaps = [container.grab() for container in containers_to_export]
        total_width = sum(p.width() for p in pixmaps)
        max_height = max(p.height() for p in pixmaps)

        result_img = QPixmap(total_width, max_height)
        result_img.fill(Qt.transparent)
        painter = QPainter(result_img)

        x_offset = 0
        for p in pixmaps:
            painter.drawPixmap(x_offset, 0, p)
            x_offset += p.width()
        painter.end()

        if filename.lower().endswith(".jpg") or filename.lower().endswith(".jpeg"):
            result_img.save(filename, "JPEG")
        else:
            result_img.save(filename, "PNG")

        QMessageBox.information(self, "Export Spread", f"Spread exported successfully to:\n{filename}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('fusion')
    window = StoryboardPlanner()
    window.show()
    sys.exit(app.exec())
