"""
main.py — Structly entry point
"""
import sys
import os

# Make sure package root is on the path when running as a script
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow, apply_dark_theme


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Structly")
    app.setApplicationVersion("1.0.0")
    apply_dark_theme(app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
