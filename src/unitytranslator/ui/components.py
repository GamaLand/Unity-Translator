"""Reusable presentation components; no project state or translation policy."""

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import QAction, QPalette
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class WrappingButton(QPushButton):
    """Keep complete localized action labels usable without horizontal form scroll."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        bounds = self.fontMetrics().boundingRect(
            QRect(0, 0, max(40, width - 32), 10000),
            Qt.TextFlag.TextWordWrap, self.text(),
        )
        return max(34, bounds.height() + 16)

    def minimumSizeHint(self):
        return QSize(90, 34)

    def sizeHint(self):
        width = min(420, max(120, self.fontMetrics().horizontalAdvance(self.text()) + 32))
        return QSize(width, self.heightForWidth(width))

    def paintEvent(self, event):
        if not self.icon().isNull():
            return super().paintEvent(event)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        painter = QStylePainter(self)
        painter.drawControl(QStyle.ControlElement.CE_PushButton, option)
        self.style().drawItemText(
            painter, self.rect().adjusted(12, 6, -12, -6),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            option.palette, self.isEnabled(), self.text(), QPalette.ColorRole.ButtonText,
        )


def label(text, role="muted"):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setProperty("role", role)
    return widget


class Section(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setProperty("role", "card")
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(18, 16, 18, 16)
        self.content.setSpacing(12)
        self.content.addWidget(label(title, "section"))


class Disclosure(QWidget):
    """A keyboard-operable, explicitly labelled secondary panel."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.toggle = QPushButton("+ " + title)
        self.toggle.setProperty("role", "disclosure")
        self.toggle.setCheckable(True)
        self.toggle.setAccessibleName(title)
        self.body = QWidget()
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)
        self.body.hide()
        self.toggle.toggled.connect(self.body.setVisible)
        self.toggle.toggled.connect(
            lambda checked: self.toggle.setText(("− " if checked else "+ ") + title)
        )


class ReviewTable(QTableView):
    """Prioritize source/translation at narrow widths; metadata stays in tooltips."""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.model() is None:
            return
        width = self.viewport().width()
        compact = width < 850
        for column in (0, 3):
            self.setColumnHidden(column, compact)
        weights = {1: 3, 2: 3, 4: 2, 5: 2}
        if not compact:
            weights.update({0: 2, 3: 1})
        for column, weight in weights.items():
            self.setColumnWidth(column, max(60, int((width - 4) * weight / sum(weights.values()))))


class ReviewNotice(QLabel):
    """Keep check warnings visible; expose the complete details in the inspector."""

    def __init__(self, text, details):
        super().__init__()
        self.details = details
        self.setMaximumHeight(46)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setText(text)

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)
        self.details.setText(text)


class ActionMenu(QPushButton):
    """Present existing controls as actions without duplicating their state guards."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.actions_menu = QMenu(self)
        self.setMenu(self.actions_menu)
        self.controls = {}

    def add_control(self, control):
        control.setParent(self)
        control.hide()
        action = QAction(control.text(), self)
        action.triggered.connect(control.click)
        self.actions_menu.addAction(action)
        self.controls[control] = action
        control.installEventFilter(self)
        self.sync(control)
        return action

    def sync(self, control):
        action = self.controls[control]
        action.setEnabled(control.isEnabled())
        action.setToolTip(control.toolTip())
        action.setText(control.text())
        action.setIcon(control.icon())

    def eventFilter(self, watched, event):
        if watched in self.controls and event.type() in (
            QEvent.Type.EnabledChange, QEvent.Type.ToolTipChange,
            QEvent.Type.StyleChange, QEvent.Type.DynamicPropertyChange,
        ):
            self.sync(watched)
        return super().eventFilter(watched, event)


class ElidingButton(QPushButton):
    """Keep the next-step shortcut compact without losing its accessible label."""

    def setText(self, text):
        self.full_text = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        super().setText(self.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, max(80, self.width() - 32),
        ))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setText(getattr(self, "full_text", super().text()))


class WorkflowTabs(QTabWidget):
    """Keep stable page indices/contracts while exposing a sidebar navigation."""

    def __init__(self, groups, parent=None):
        super().__init__(parent)
        self.tabBar().hide()
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(202)
        self.navigation = QVBoxLayout(self.sidebar)
        self.navigation.setContentsMargins(14, 24, 14, 16)
        self.navigation.setSpacing(5)
        self.navigation.addWidget(label("UnityTranslator", "brand"))
        self.navigation.addSpacing(22)
        self.groups = groups
        self.buttons = []
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.currentChanged.connect(self.activate)

    def addTab(self, widget, text):
        index = self.count()
        if index in self.groups:
            if index:
                self.navigation.addSpacing(18)
            self.navigation.addWidget(label(self.groups[index]))
        button = QPushButton(text.split(" · ", 1)[-1])
        button.setProperty("role", "navigation")
        button.setCheckable(True)
        button.setAccessibleName(text)
        button.setToolTip(text)
        button.clicked.connect(lambda checked=False, i=index: self.setCurrentIndex(i))
        self.buttons.append(button)
        self.button_group.addButton(button, index)
        self.navigation.addWidget(button)
        result = super().addTab(widget, text)
        self.activate(self.currentIndex())
        return result

    def setTabEnabled(self, index, enabled):
        super().setTabEnabled(index, enabled)
        self.buttons[index].setEnabled(enabled)

    def activate(self, index):
        for page, button in enumerate(self.buttons):
            button.setChecked(page == index)

    def finish(self, footer):
        self.navigation.addStretch()
        self.navigation.addWidget(label(footer))


def scroll_page(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(widget)
    return area


def editor_panel(title, editor):
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(label(title, "section"))
    editor.setAccessibleName(title)
    layout.addWidget(editor, 1)
    return panel

