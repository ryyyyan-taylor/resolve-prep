from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

WINDOW = QColor(32, 33, 36)
BASE = QColor(24, 25, 27)
ALTERNATE = QColor(40, 41, 45)
TEXT = QColor(226, 226, 228)
DISABLED = QColor(120, 121, 125)
HIGHLIGHT = QColor(68, 120, 200)
BUTTON = QColor(48, 49, 53)


# Fusion plus an explicit palette rather than the platform colour scheme, which
# on this Wayland session resolves to a light theme regardless of preference.
def apply(app):
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, WINDOW)
    palette.setColor(QPalette.WindowText, TEXT)
    palette.setColor(QPalette.Base, BASE)
    palette.setColor(QPalette.AlternateBase, ALTERNATE)
    palette.setColor(QPalette.Text, TEXT)
    palette.setColor(QPalette.Button, BUTTON)
    palette.setColor(QPalette.ButtonText, TEXT)
    palette.setColor(QPalette.ToolTipBase, BASE)
    palette.setColor(QPalette.ToolTipText, TEXT)
    palette.setColor(QPalette.Highlight, HIGHLIGHT)
    palette.setColor(QPalette.HighlightedText, Qt.white)
    palette.setColor(QPalette.Link, HIGHLIGHT)
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, DISABLED)
    app.setPalette(palette)
    return app
