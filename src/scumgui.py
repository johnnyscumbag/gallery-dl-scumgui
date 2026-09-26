from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QColor, QIcon
from progress import parse_progress

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "ScumGUI"


class QueueItem:
    WAITING = "Waiting"
    DOWNLOADING = "Downloading"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"

    def __init__(self, url: str) -> None:
        self.url = url
        self.status = self.WAITING
        self.list_item: QListWidgetItem | None = None


def app_root() -> Path:
    return (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[1]
    )


def resource_path(relative_path: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(
            getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)
        ) / relative_path
    return app_root() / relative_path


def find_gallery_dl() -> str | None:
    root = app_root()

    for candidate in (
        root / "gallery-dl" / "gallery-dl.exe",
        root / "gallery-dl.exe",
    ):
        if candidate.is_file():
            return str(candidate)

    return shutil.which("gallery-dl")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(resource_path("assets/scumgui.ico"))))
        self.resize(980, 720)

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.process_finished)

        self.queue_items: list[QueueItem] = []
        self.current_index = -1
        self.cancelling = False

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
        self.queue.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        queue_layout.addWidget(self.queue)

        controls = QGridLayout()

        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self.remove_selected)
        controls.addWidget(remove_button, 0, 0)

        clear_button = QPushButton("Clear Finished")
        clear_button.clicked.connect(self.clear_finished)
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
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Idle")
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
            self.log_message("gallery-dl engine not found; PATH fallback unavailable.")

    def add_url(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return

        item = QueueItem(url)
        self.queue_items.append(item)

        list_item = QListWidgetItem()
        item.list_item = list_item
        self.queue.addItem(list_item)
        self.refresh_queue_item(item)

        self.url_edit.clear()
        self.log_message(f"Added: {url}")

    def refresh_queue_item(self, item: QueueItem) -> None:
        if item.list_item is None:
            return

        item.list_item.setText(f"[{item.status}]  {item.url}")

        if item.status == QueueItem.COMPLETED:
            item.list_item.setForeground(QColor("green"))
        elif item.status == QueueItem.FAILED:
            item.list_item.setForeground(QColor("red"))
        elif item.status == QueueItem.CANCELLED:
            item.list_item.setForeground(QColor("gray"))
        else:
            item.list_item.setForeground(self.palette().text().color())

    def remove_selected(self) -> None:
        selected = set(self.queue.selectedItems())
        if not selected:
            return

        if self.process.state() != QProcess.ProcessState.NotRunning:
            return

        self.queue_items = [item for item in self.queue_items if item.list_item not in selected]
        for list_item in selected:
            self.queue.takeItem(self.queue.row(list_item))

    def clear_finished(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return

        finished = {
            QueueItem.COMPLETED,
            QueueItem.FAILED,
            QueueItem.CANCELLED,
        }
        for item in list(self.queue_items):
            if item.status in finished:
                if item.list_item is not None:
                    self.queue.takeItem(self.queue.row(item.list_item))
                self.queue_items.remove(item)

    def choose_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose download destination", self.destination_edit.text()
        )
        if folder:
            self.destination_edit.setText(folder)

    def start_download(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
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

        next_index = self.next_waiting_index()
        if next_index < 0:
            QMessageBox.information(self, APP_NAME, "There are no waiting URLs in the queue.")
            return

        self.current_index = next_index
        item = self.queue_items[self.current_index]
        item.status = QueueItem.DOWNLOADING
        self.refresh_queue_item(item)

        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Downloading…")
        self.status_label.setText(f"Downloading: {item.url}")
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancelling = False

        self.process.setWorkingDirectory(str(destination))
        self.log_message(f"Starting: {item.url}")
        self.process.start(engine, ["-o", "output.mode=terminal", "-o", "output.ansi=false", item.url])

        if not self.process.waitForStarted(3000):
            item.status = QueueItem.FAILED
            self.refresh_queue_item(item)
            self.log_message("ERROR: Failed to start gallery-dl.")
            self.start_next_or_finish()

    def next_waiting_index(self) -> int:
        for index, item in enumerate(self.queue_items):
            if item.status == QueueItem.WAITING:
                return index
        return -1

    def cancel_download(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return

        self.cancelling = True
        self.log_message("Stopping gallery-dl…")
        self.process.terminate()

        if not self.process.waitForFinished(1500):
            self.process.kill()

    def read_stdout(self) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if data:
            self.consume_output(data)

    def read_stderr(self) -> None:
        data = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        if data:
            self.consume_output(data)

    def consume_output(self, data: str) -> None:
        for line in data.replace("\r", "\n").splitlines():
            if not line:
                continue
            progress = parse_progress(line)
            if progress is not None:
                self.progress.setValue(progress.percent)
                self.progress.setFormat(
                    str(progress.percent) + "%  " + progress.downloaded + "  " + progress.speed
                )
            else:
                self.log_message(line)

    def process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self.current_index < 0:
            return

        item = self.queue_items[self.current_index]

        if self.cancelling:
            item.status = QueueItem.CANCELLED
        elif exit_status == QProcess.ExitStatus.CrashExit or exit_code != 0:
            item.status = QueueItem.FAILED
        else:
            item.status = QueueItem.COMPLETED

        self.refresh_queue_item(item)
        self.log_message(
            f"Finished: {item.url} — {item.status} (exit code {exit_code})"
        )

        self.start_next_or_finish()

    def start_next_or_finish(self) -> None:
        self.current_index = -1
        self.cancelling = False

        next_index = self.next_waiting_index()
        if next_index >= 0:
            self.download_button.setEnabled(True)
            self.start_download()
            return

        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Complete")
        self.status_label.setText("Queue finished")
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def log_message(self, message: str) -> None:
        self.log.appendPlainText(message)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("windows11")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
