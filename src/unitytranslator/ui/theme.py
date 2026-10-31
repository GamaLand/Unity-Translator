"""Shared, offline visual tokens for the translation workbench."""

from PySide6.QtGui import QColor, QPalette

COLORS = {
    "background": "#202321",
    "surface": "#282c29",
    "field": "#1c1f1d",
    "border": "#414741",
    "text": "#e7e9e3",
    "muted": "#a8b0a7",
    "accent": "#b5c8a5",
    "selected": "#3d4c3c",
    "warning": "#e2be7c",
}


def apply_theme(app):
    app.setStyle("Fusion")
    palette = QPalette()
    for role, key in (
        (QPalette.ColorRole.Window, "background"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "field"),
        (QPalette.ColorRole.AlternateBase, "surface"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "surface"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.Highlight, "selected"),
        (QPalette.ColorRole.HighlightedText, "text"),
        (QPalette.ColorRole.ToolTipBase, "surface"),
        (QPalette.ColorRole.ToolTipText, "text"),
        (QPalette.ColorRole.PlaceholderText, "muted"),
        (QPalette.ColorRole.Link, "accent"),
    ):
        palette.setColor(role, QColor(COLORS[key]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#80877f"))
    app.setPalette(palette)
    app.setStyleSheet("""
        QWidget { font-size: 13px; }
        QMainWindow, QDialog { background: #202321; }
        QLabel { background: transparent; }
        QLabel[role="muted"] { color: #a8b0a7; }
        QLabel[role="heading"] { font-size: 24px; font-weight: 600; }
        QLabel[role="section"] { font-size: 14px; font-weight: 600; color: #c8d2c0; }
        QLabel[role="brand"] { font-size: 17px; font-weight: 600; }
        QFrame#sidebar { background: #191c1a; border-right: 1px solid #373d36; }
        QFrame#workspaceHeader { border-bottom: 1px solid #373d36; }
        QFrame[role="card"] { background: #282c29; border: 1px solid #414741;
                                  border-radius: 8px; }
        QTabWidget::pane { border: 0; }
        QTabBar::tab { padding: 7px 14px; margin-right: 4px;
                      border-bottom: 2px solid transparent; }
        QTabBar::tab:selected { border-bottom-color: #b5c8a5; color: #d7e6ca; }
        QPushButton, QToolButton { background: #303630; border: 1px solid #4a5248;
                                  border-radius: 5px; padding: 7px 12px; }
        QPushButton:hover, QToolButton:hover { background: #3b4439; }
        QPushButton:pressed, QToolButton:pressed { background: #454f40; }
        QPushButton:disabled, QToolButton:disabled { background: #252925;
                                                    border-color: #343a33; }
        QPushButton[role="primary"] { background: #b5c8a5; color: #1d291b;
                                       border-color: #b5c8a5; font-weight: 600; }
        QPushButton[role="primary"]:hover { background: #c3d5b5; }
        QPushButton[role="primary"]:disabled { background: #353e31; color: #919b8a;
                                                border-color: #414b3b; }
        QPushButton[role="navigation"] { text-align: left; border: 0;
                                          background: transparent; padding: 10px 12px; }
        QPushButton[role="navigation"]:checked { background: #344031; color: #dbe8d1; }
        QPushButton[role="navigation"]:hover { background: #2b3329; }
        QPushButton[role="disclosure"] { text-align: left; background: transparent; }
        QPushButton:focus, QToolButton:focus { border: 1px solid #b5c8a5; }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QTableView {
            background: #1c1f1d; border: 1px solid #414741; border-radius: 5px;
            selection-background-color: #3d4c3c; selection-color: #f1f5ed;
        }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { padding: 6px 8px; min-height: 18px; }
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus,
        QDoubleSpinBox:focus, QTableView:focus { border-color: #b5c8a5; }
        QTextEdit { padding: 8px; }
        QTableView { gridline-color: #30372f; alternate-background-color: #242924; }
        QHeaderView::section { background: #2e352d; color: #bcc6b6; border: 0;
                              border-bottom: 1px solid #414741; padding: 8px; }
        QGroupBox { border: 1px solid #414741; border-radius: 7px;
                    margin-top: 13px; padding: 12px; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
        QProgressBar { border: 1px solid #414741; border-radius: 5px;
                       background: #1c1f1d; text-align: center; min-height: 22px; }
        QProgressBar::chunk { background: #526747; border-radius: 4px; }
        QSplitter::handle { background: #373e35; }
        QSplitter::handle:hover { background: #7f9472; }
        QMenu { background: #282e27; border: 1px solid #525d4c; padding: 5px; }
        QMenu::item { padding: 8px 22px; }
        QMenu::item:selected { background: #3d4c3c; }
        QMenu::item:disabled { color: #80877f; }
        QScrollArea { border: 0; background: transparent; }
        QScrollBar:vertical { background: #202321; width: 12px; margin: 0; }
        QScrollBar::handle:vertical { background: #505b49; min-height: 30px; border-radius: 5px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QStatusBar { color: #a8b0a7; border-top: 1px solid #373d36; }
        QToolTip { color: #e7e9e3; background: #282c29; border: 1px solid #64725b; padding: 5px; }
    """)
