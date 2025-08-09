from PIL import Image, ImageDraw

from PySide6.QtWidgets import QWidget, QLabel, QCheckBox, QSlider, QVBoxLayout, QHBoxLayout, QPushButton, QColorDialog, QDialog, QToolButton
from PySide6.QtGui import QPixmap, QImage, Qt


from python.utility.colors import WHITE, BLACK
from python.utility.settings import DEFAULT_WIDTH, DEFAULT_HEIGHT

class ThumbnailToolButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

class BaseThumbnailWidget(QWidget):

# If Empty - display a draw and an upload button.
# Once filled, display those buttons on hover only.
# Allow to draw over an uploaded image.

    def __init__(self, parent=None):
        super().__init__(parent)
        self.upload_button = ThumbnailToolButton()
        self.edit_button = ThumbnailToolButton()


class DrawingWidget(QWidget):
    def __init__(self, width, height, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.image = Image.new("RGBA", (width, height), WHITE)
        self.draw = ImageDraw.Draw(self.image)
        self.brush_color = BLACK
        self.brush_size = 2
        self.eraser_mode = False
        self.last_pos = None

        self.label = QLabel(self)
        self.label.setFixedSize(width, height)
        self.label.move(0,0)

        self.update_pixmap()

        self.label.mousePressEvent = self.mousePressEvent
        self.label.mouseMoveEvent = self.mouseMoveEvent
        self.label.mouseReleaseEvent = self.mouseReleaseEvent

    @property
    def fill_color(self):
        return (255, 255, 255, 0) if self.eraser_mode else self.brush_color

    def update_pixmap(self):
        self.label.setPixmap(QPixmap.fromImage(QImage(self.image.tobytes("raw", "RGBA"),
                                       self.image.width,
                                       self.image.height, QImage.Format_RGBA8888)))

    def mouseMoveEvent(self, event):
        if self.last_pos:
            pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            self.draw_line(self.last_pos, pos)
            self.last_pos = pos

    def mouseReleaseEvent(self, event):
        self.last_pos = None

    # def draw_point(self, pos):
    #     self.draw.ellipse(xy=[pos.x() - self.brush_size,
    #                           pos.y() - self.brush_size,
    #                           pos.x() + self.brush_size,
    #                           pos.y() + self.brush_size],
    #                       fill=self.fill_color)
    #
    #     self.update_pixmap()

    def draw_line(self, start, end):
        self.draw.line([start.x(), start.y(), end.x(), end.y()],
                       fill=self.fill_color,
                       width=self.brush_size * 2)

        self.update_pixmap()


class BigDrawingDialog(QDialog):
    def __init__(self, pil_image=None, brush_color=BLACK, brush_size=5, eraser_mode=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Storyboard Canvas")
        self.canvas_width = DEFAULT_WIDTH
        self.canvas_height = DEFAULT_HEIGHT
        self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        layout = QVBoxLayout(self)

        if pil_image:
            self.image = pil_image.resize((self.canvas_width, self.canvas_height), Image.LANCZOS).copy()
        else:
            self.image = Image.new("RGBA", (self.canvas_width, self.canvas_height), WHITE)

        self.draw = ImageDraw.Draw(self.image)

        self.label = QLabel()
        self.label.setFixedSize(self.canvas_width, self.canvas_height)
        self.label.setMouseTracking(True)
        layout.addWidget(self.label)

        toolbar = QHBoxLayout()

        self.color_btn = QPushButton("Brush Color")
        self.color_btn.clicked.connect(self.open_color_picker)
        toolbar.addWidget(self.color_btn)

        self.brush_slider = QSlider(Qt.Horizontal)
        self.brush_slider.setMinimum(1)
        self.brush_slider.setMaximum(30)
        self.brush_slider.setValue(brush_size)
        self.brush_slider.valueChanged.connect(self.update_brush_size)
        toolbar.addWidget(QLabel("Brush Size"))
        toolbar.addWidget(self.brush_slider)

        self.eraser_checkbox = QCheckBox("Eraser")
        self.eraser_checkbox.setChecked(eraser_mode)
        self.eraser_checkbox.toggled.connect(self.eraser_toggled)
        toolbar.addWidget(self.eraser_checkbox)

        layout.addLayout(toolbar)

        btn_layout = QHBoxLayout()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Confirm")
        self.save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.save_btn)


        layout.addLayout(btn_layout)

        self.brush_color = brush_color
        self.brush_size = brush_size
        self.eraser_mode = eraser_mode

        self.last_pos = None

        self.update_pixmap()

        self.label.mousePressEvent = self.mousePressEvent
        self.label.mouseMoveEvent = self.mouseMoveEvent
        self.label.mouseReleaseEvent = self.mouseReleaseEvent

    def open_color_picker(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.brush_color = (color.red(), color.green(), color.blue(), 255)

    def update_brush_size(self, val):
        self.brush_size = val

    def eraser_toggled(self, checked):
        self.eraser_mode = checked

    def update_pixmap(self):
        self.label.setPixmap(QPixmap.fromImage(QImage(self.image.tobytes("raw", "RGBA"),
                                       self.image.width,
                                       self.image.height, QImage.Format_RGBA8888)))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            self.last_pos = pos
            self.draw_point(pos)

    def mouseMoveEvent(self, event):
        if self.last_pos:
            pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            self.draw_line(self.last_pos, pos)
            self.last_pos = pos

    def mouseReleaseEvent(self, event):
        self.last_pos = None

    def draw_point(self, pos):
        self.draw.ellipse(xy=[pos.x() - self.brush_size,
                           pos.y() - self.brush_size,
                           pos.x() + self.brush_size,
                           pos.y() + self.brush_size],
                          fill=WHITE if self.eraser_mode else self.brush_color)

        self.update_pixmap()

    def draw_line(self, start, end):
        self.draw.line([start.x(), start.y(), end.x(), end.y()],
                       fill=WHITE if self.eraser_mode else self.brush_color,
                       width=self.brush_size * 2)

        self.update_pixmap()

    def get_image(self):
        return self.image.copy()
