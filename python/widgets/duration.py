import re

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLineEdit
from PySide6.QtCore import QRegularExpression, Signal
from PySide6.QtGui import QRegularExpressionValidator

from python.utility.settings import DEFAULT_FPS

class DurationLabel(QPushButton):
    def __init__(self, parent=None, unit_of_measure:str = ''):
        super().__init__(parent)
        self.unit = unit_of_measure

    def setText(self, text: str):
        super().setText(f"{text}{' ' if self.unit else ''}{self.unit}")

class DurationInput(QLineEdit):
    FocusLost = Signal()

    def focusOutEvent(self, focus_event):
        super().focusOutEvent(focus_event)
        # NOTE - StevenPince - Emit a signal when focus is lost,
        #                      so the input can be calculated.
        self.FocusLost.emit()


class DurationWidget(QWidget):
    DurationChanged = Signal()
    regex_str = "([0-9]+[sS]?)([0-9]+[fF]?)?"
    regex_compiled = re.compile(regex_str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fps = DEFAULT_FPS
        self.frames = 0

        self.frames_display = DurationLabel(unit_of_measure='Frames')
        self.input = DurationInput(self)

        reg_ex = QRegularExpression(self.regex_str)
        input_validator = QRegularExpressionValidator(reg_ex, self.input)
        self.input.setValidator(input_validator)
        self.input.setVisible(False)

        layout = QHBoxLayout(self)
        layout.addWidget(self.input)
        layout.addWidget(self.frames_display)

        layout.setContentsMargins(0, 0, 0, 0)

        self.input.editingFinished.connect(self.update)
        self.input.FocusLost.connect(self.update)
        self.frames_display.clicked.connect(self.allow_input)

        self.update()

    def allow_input(self):
        self.input.setVisible(True)
        self.input.setFocus()
        self.frames_display.setVisible(False)

    def update(self):
        duration_str = self.input.text().lower()

        self.frames = 0

        if 's' in duration_str:
            seconds, duration_str = duration_str.split('s')
            self.frames = int(seconds) * DEFAULT_FPS

        if 'f' in duration_str:
            self.frames += int(duration_str.split('f')[0])

        if self.frames == 0 and self.input.text():
            # NOTE - StevenPince - Accept the number that was entered.
            self.frames = int(duration_str)

        self.DurationChanged.emit()

        self.frames_display.setText(f'{self.frames}')
        self.input.setVisible(False)
        self.frames_display.setVisible(True)

