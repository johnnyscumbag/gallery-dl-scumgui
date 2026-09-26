from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "gallery-dl ScumGUI"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(980, 720)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        input_box = QGroupBox("Download")
        input_grid = QGridLayout(input_box)

        input_grid.addWidget(QLabel("URL"), 0, 0)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste a gallery-dl URL here…")
        input_grid.addWidget(self.url_edit, 0, 1, 1, 2)

        self.add_button = QPushButton("Add to Queue")
        self.add_button.clicked.connect(self.add_url)
        input_grid.addWidget(self.add_button, 0, 3)

        input_grid.addWidget(QLabel("Destination"), 1, 0)
        self.destination_edit = QLineEdit(str(Path.cwd()))
        input_grid.addWidget(self.destination_edit, 1, 1, 1, 2)

        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self.choose_destination)
        input_grid.addWidget(browse_button, 1, 3)

        input_grid.addWidget(QLabel("Profile"), 2, 0)
        self.profile_combo = QComboBox()
        self.profile_combo.addItem("Default")
        input_grid.addWidget(self.profile_combo, 2, 1)

        input_grid.addWidget(QLabel("Workers"), 2, 2)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 8)
        self.workers_spin.setValue(1)
        input_grid.addWidget(self.workers_spin, 2, 3)

        layout.addWidget(input_box)

        queue_box = QGroupBox("Queue")
        queue_layout = QVBoxLayout(queue_box)
        self.queue = QListWidget()
        queue_layout.addWidget(self.queue)

        controls = QGridLayout()
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self.remove_selected)
        controls.addWidget(remove_button, 0, 0)

        clear_button = QPushButton("Clear Queue")
        clear_button.clicked.connect(self.queue.clear)
        controls.addWidget(clear_button, 0, 1)

        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.start_download_placeholder)
        controls.addWidget(self.download_button, 0, 3)
        queue_layout.addLayout(controls)
        layout.addWidget(queue_box, 1)

        status_box = QGroupBox("Current Item")
        status_layout = QVBoxLayout(status_box)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        status_layout.addWidget(self.progress)

        self.status_label = QLabel("Ready")
        status_layout.addWidget(self.status_label)
        layout.addWidget(status_box)

        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        log_layout.addWidget(self.log)
        layout.addWidget(log_box, 1)

        self.log_message("ScumGUI started.")

    def add_url(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return
        self.queue.addItem(url)
        self.url_edit.clear()
        self.log_message(f"Added: {url}")

    def remove_selected(self) -> None:
        for item in self.queue.selectedItems():
            self.queue.takeItem(self.queue.row(item))

    def choose_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose download destination", self.destination_edit.text()
        )
        if folder:
            self.destination_edit.setText(folder)

    def start_download_placeholder(self) -> None:
        executable = shutil.which("gallery-dl")
        if executable is None:
            QMessageBox.warning(
                self,
                APP_NAME,
                "gallery-dl was not found on PATH yet. The download engine "
                "will be wired into the queue in the next development step.",
            )
            return

        self.status_label.setText(
            "gallery-dl detected. Downloader integration is the next step."
        )
        self.log_message(f"gallery-dl found at: {executable}")

    def log_message(self, message: str) -> None:
        self.log.appendPlainText(message)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
