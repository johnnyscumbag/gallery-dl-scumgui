from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
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
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "gallery-dl ScumGUI"


def app_root() -> Path:
    # Keep the bundled engine relative to ScumGUI when packaged.
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def find_gallery_dl() -> str | None:
    root = app_root()

    candidates = [
        root / "gallery-dl" / "gallery-dl.exe",
        root / "gallery-dl.exe",
    ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return shutil.which("gallery-dl")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(980, 720)

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.process_finished)
        self.current_urls: list[str] = []

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        input_box = QGroupBox("Download")
        input_grid = QGridLayout(input_box)

        input_grid.addWidget(QLabel("URL"), 0, 0)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste a gallery-dl URL here…")
        self.url_edit.returnPressed.connect(self.add_url)
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
        self.download_button.clicked.connect(self.start_download)
        controls.addWidget(self.download_button, 0, 3)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_download)
        controls.addWidget(self.cancel_button, 0, 4)

        queue_layout.addLayout(controls)
        layout.addWidget(queue_box, 1)

        status_box = QGroupBox("Current Item")
        status_layout = QVBoxLayout(status_box)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setValue(0)
        self.progress.setFormat("Working…")
        status_layout.addWidget(self.progress)

        self.status_label = QLabel("Ready")
        status_layout.addWidget(self.status_label)
        layout.addWidget(status_box)

        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        log_layout.addWidget(self.log)

        layout.addWidget(log_box, 1)

        self.log_message("ScumGUI started.")
        engine = find_gallery_dl()
        if engine:
            self.log_message(f"gallery-dl engine: {engine}")
        else:
            self.log_message("gallery-dl engine not found. Falling back to PATH when available.")

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

    def start_download(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return

        urls = [self.queue.item(i).text() for i in range(self.queue.count())]
        if not urls:
            QMessageBox.information(self, APP_NAME, "Add at least one URL to the queue.")
            return

        destination = Path(self.destination_edit.text()).expanduser()
        if not destination.is_dir():
            QMessageBox.warning(self, APP_NAME, "The selected destination folder does not exist.")
            return

        engine = find_gallery_dl()
        if not engine:
            QMessageBox.warning(
                self,
                APP_NAME,
                "gallery-dl was not found. The bundled engine will be added before the first release.",
            )
            return

        self.current_urls = urls
        self.progress.setRange(0, 0)
        self.progress.setFormat("Downloading…")
        self.status_label.setText(f"Downloading {len(urls)} queued URL(s)…")
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

        # The working directory is the selected destination. This means an existing
        # gallery-dl config using base-directory "." behaves naturally.
        self.process.setWorkingDirectory(str(destination))

        # One gallery-dl process handles the queue. This keeps ordering and output
        # simple while the queue model is being built.
        arguments = ["--verbose", *urls]
        self.log_message(f"Starting gallery-dl with {len(urls)} URL(s)…")
        self.process.start(engine, arguments)

        if not self.process.waitForStarted(3000):
            self.log_message("ERROR: Failed to start gallery-dl.")
            self.finish_download()

    def cancel_download(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return

        self.log_message("Stopping gallery-dl…")
        self.process.terminate()
        if not self.process.waitForFinished(1500):
            self.process.kill()

    def read_stdout(self) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if data:
            self.log_message(data.rstrip())

    def read_stderr(self) -> None:
        data = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        if data:
            self.log_message(data.rstrip())

    def process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self.log_message(f"gallery-dl finished with exit code {exit_code}.")
        if exit_status == QProcess.ExitStatus.CrashExit:
            self.log_message("gallery-dl terminated unexpectedly.")
        self.finish_download()

    def finish_download(self) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if self.process.exitCode() == 0 else 0)
        self.progress.setFormat("Finished")
        self.status_label.setText("Ready")
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

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
