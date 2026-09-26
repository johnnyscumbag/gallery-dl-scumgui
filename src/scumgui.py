from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import QProcess, QSettings, Qt
from PySide6.QtGui import QColor, QIcon
from progress import parse_progress

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "ScumGUI"


class QueueItem:
    WAITING = "Waiting"
    DOWNLOADING = "Downloading"
    COMPLETED = "Completed"
    COMPLETED_WITH_ERRORS = "Completed with errors"
    FAILED = "Failed"
    CANCELLED = "Cancelled"

    def __init__(self, url: str, destination: str) -> None:
        self.url = url
        self.destination = destination
        self.status = self.WAITING
        self.list_item: QListWidgetItem | None = None
        self.downloaded = 0
        self.skipped = 0
        self.errors = 0
        self.current_file = ""
        # Holds the most recent file-level failure reason until gallery-dl's
        # --Print error event gives us the corresponding filename.
        self.pending_error_reason = ""
        self.started_at = 0.0


def app_root() -> Path:
    return (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[1]
    )


def resource_path(relative_path: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent / relative_path
    return app_root() / relative_path


def find_gallery_dl() -> str | None:
    root = app_root()

    for candidate in (
        root / "Resources" / "gallery-dl.exe",
        resource_path("gallery-dl/gallery-dl.exe"),
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

        settings_path = app_root() / "ScumGUI.ini"
        settings_exists = settings_path.is_file()
        self.settings = QSettings(
            str(settings_path),
            QSettings.Format.IniFormat,
        )

        if not settings_exists:
            self.settings.setValue("base_folder", "M:\\Blah")
            self.settings.sync()

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
        base_folder = str(self.settings.value("base_folder", "M:\\Blah"))
        self.destination_edit = QLineEdit(base_folder)
        input_grid.addWidget(self.destination_edit, 1, 1, 1, 3)

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

        self.queue_progress = QProgressBar()
        self.queue_progress.setRange(0, 1)
        self.queue_progress.setValue(0)
        self.queue_progress.setFormat("Queue: 0 / 0")
        queue_layout.addWidget(self.queue_progress)

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

        self.cancel_button = QPushButton("Cancel Current")
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

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
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

        destination_text = self.destination_edit.text().strip()
        if not destination_text:
            QMessageBox.warning(
                self,
                APP_NAME,
                "Enter a destination folder before adding the URL.",
            )
            return

        base_folder = Path(
            self.settings.value("base_folder", "M:\\Blah")
        ).expanduser()
        entered_path = Path(destination_text).expanduser()
        base_resolved = base_folder.resolve()
        entered_resolved = entered_path.resolve()

        try:
            destination_path = entered_resolved.relative_to(base_resolved)
        except ValueError:
            QMessageBox.warning(
                self,
                APP_NAME,
                "The destination must be inside the configured base folder.",
            )
            return

        destination = str(destination_path)
        if not destination or destination == ".":
            QMessageBox.warning(
                self,
                APP_NAME,
                "Enter a destination folder name after the base folder.",
            )
            return

        item = QueueItem(url, destination)
        self.queue_items.append(item)

        list_item = QListWidgetItem()
        item.list_item = list_item
        self.queue.addItem(list_item)
        self.refresh_queue_item(item)

        self.url_edit.clear()
        self.update_queue_progress()
        self.log_message(f"Added: {destination}  —  {url}")

    def refresh_queue_item(self, item: QueueItem) -> None:
        if item.list_item is None:
            return

        stats = f"D:{item.downloaded}  S:{item.skipped}  E:{item.errors}"
        if item.status == QueueItem.DOWNLOADING and item.current_file:
            text = f"[{item.status}]  {stats}  {item.destination}  —  {item.current_file}"
        else:
            text = f"[{item.status}]  {stats}  {item.destination}  —  {item.url}"
        item.list_item.setText(text)

        if item.status == QueueItem.COMPLETED:
            item.list_item.setForeground(QColor("green"))
        elif item.status == QueueItem.COMPLETED_WITH_ERRORS:
            item.list_item.setForeground(QColor("orange"))
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
        self.update_queue_progress()

    def clear_finished(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return

        finished = {
            QueueItem.COMPLETED,
            QueueItem.COMPLETED_WITH_ERRORS,
            QueueItem.FAILED,
            QueueItem.CANCELLED,
        }
        for item in list(self.queue_items):
            if item.status in finished:
                if item.list_item is not None:
                    self.queue.takeItem(self.queue.row(item.list_item))
                self.queue_items.remove(item)
        self.update_queue_progress()

    def update_queue_progress(self) -> None:
        total = len(self.queue_items)
        finished = sum(
            item.status in {
                QueueItem.COMPLETED,
                QueueItem.COMPLETED_WITH_ERRORS,
                QueueItem.FAILED,
                QueueItem.CANCELLED,
            }
            for item in self.queue_items
        )

        self.queue_progress.setRange(0, max(total, 1))
        self.queue_progress.setValue(finished)
        self.queue_progress.setFormat(
            f"Queue: {finished} / {total}" if total else "Queue: 0 / 0"
        )

    def start_download(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
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
        item.pending_error_reason = ""

        base_folder = Path(
            self.settings.value("base_folder", "M:\\Blah")
        ).expanduser()
        destination = base_folder / item.destination
        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(
                self,
                APP_NAME,
                f"Could not create the destination folder:\n{destination}\n\n{exc}",
            )
            self.current_index = -1
            return
        self.update_queue_progress()
        item.status = QueueItem.DOWNLOADING
        self.refresh_queue_item(item)

        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Downloading…")
        item.started_at = time.monotonic()
        self.status_label.setText(f"Downloading: {item.destination}  —  {item.url}  |  D:0  S:0  E:0")
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancelling = False

        self.process.setWorkingDirectory(str(destination))
        self.log_message(f"Starting: {item.destination}  —  {item.url}")
        args = []
        scumgui_config = app_root() / "Resources" / "scumgui-gallery-dl.json"
        if scumgui_config.is_file():
            args.extend(["--config-json", str(scumgui_config)])
        args.extend([
            "-o", "output.mode=terminal",
            "-o", "output.ansi=false",
            "--Print", "after:[SCUMGUI_SUCCESS] {_path}",
            "--Print", "skip:[SCUMGUI_SKIP] {_path}",
            "--Print", "error:[SCUMGUI_ERROR] {_path}",
            item.url,
        ])
        self.process.start(engine, args)

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
        # gallery-dl is a Windows console application. QProcess.terminate()
        # sends WM_CLOSE on Windows, which console applications may not handle.
        # kill() uses TerminateProcess, so use it for a reliable immediate
        # cancellation.
        self.process.kill()
        self.process.waitForFinished(1500)

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
            if self.consume_result_marker(line):
                continue

            if self.consume_gallery_log(line):
                continue

            progress = parse_progress(line)
            if progress is not None:
                self.progress.setValue(progress.percent)
                self.progress.setFormat(
                    str(progress.percent) + "%  " + progress.downloaded + "  " + progress.speed
                )
            else:
                self.log_message(line)

    @staticmethod
    def is_redundant_gallery_output(line: str) -> bool:
        # gallery-dl's terminal output uses "* <path>" for completed files.
        # ScumGUI already receives a cleaner --Print event marker, so suppress
        # the duplicate terminal status line.
        return bool(re.match(r"^\*\s+.+$", line.strip()))

    def consume_gallery_log(self, line: str) -> bool:
        match = re.match(
            r"^\[(?P<logger>[^]]+)\]\[(?P<level>warning|error|info)\]\s+(?P<message>.*)$",
            line,
            re.IGNORECASE,
        )
        if not match:
            return self.is_redundant_gallery_output(line)

        level = match.group("level").lower()
        message = match.group("message").strip()
        item = self.queue_items[self.current_index] if self.current_index >= 0 else None

        timeout = re.search(
            r"ConnectTimeoutError: Connection to (?P<host>[^ ]+) timed out\. "
            r"\((?P<attempt>\d+)/(?P<total>\d+)\)",
            message,
        )
        if timeout:
            reason = (
                f"Connection timeout — {timeout.group('host')} — "
                f"retry {timeout.group('attempt')}/{timeout.group('total')}"
            )
            if item is not None:
                item.pending_error_reason = (
                    f"connection timeout after {timeout.group('total')} retries"
                )
            self.log_event("⚠", "orange", reason)
            return True

        not_found = re.search(
            r"(?P<code>\d{3}) (?P<reason>[^:]+?) for (?P<url>https?://\S+)",
            message,
        )
        if not_found and not_found.group("code") == "404":
            url = not_found.group("url").rstrip(".,")
            host = url.split("/", 3)[2] if "://" in url else url
            reason = f"404 Not Found — {host}"
            if item is not None:
                item.pending_error_reason = "404 Not Found"
            self.log_event("⚠", "orange", reason)
            return True

        if level == "error" and message.lower().startswith("failed to download"):
            if item is not None and not item.pending_error_reason:
                item.pending_error_reason = "download failed"
            return True

        if level == "warning":
            self.log_event("⚠", "orange", message)
            return True

        if level == "error":
            if item is not None:
                item.pending_error_reason = message
            self.log_event("✗", "red", message)
            return True

        return False

    def consume_result_marker(self, line: str) -> bool:
        if self.current_index < 0:
            return False

        item = self.queue_items[self.current_index]
        markers = (
            ("[SCUMGUI_SUCCESS] ", "downloaded"),
            ("[SCUMGUI_SKIP] ", "skipped"),
            ("[SCUMGUI_ERROR] ", "errors"),
        )
        for marker, counter in markers:
            if line.startswith(marker):
                filename = line[len(marker):].strip()
                setattr(item, counter, getattr(item, counter) + 1)
                item.current_file = filename
                self.refresh_queue_item(item)
                self.update_current_item(item)
                if counter == "downloaded":
                    self.log_event("✓", "green", filename)
                elif counter == "skipped":
                    self.log_event("⚠", "orange", filename)
                else:
                    reason = item.pending_error_reason
                    message = f"{filename} — {reason}" if reason else filename
                    self.log_event("✗", "red", message)
                    # Only an actual file-level error consumes the pending
                    # reason. Successful/skipped files must not wipe out a
                    # reason reported just before their error marker arrives.
                    item.pending_error_reason = ""
                return True
        return False

    def update_current_item(self, item: QueueItem) -> None:
        elapsed = time.monotonic() - item.started_at if item.started_at else 0
        minutes, seconds = divmod(int(elapsed), 60)
        elapsed_text = f"{minutes:02d}:{seconds:02d}"
        current = item.current_file or item.url
        self.status_label.setText(
            f"{current}  |  D:{item.downloaded}  S:{item.skipped}  E:{item.errors}  |  {elapsed_text}"
        )

    def queue_totals(self) -> tuple[int, int, int]:
        return (
            sum(item.downloaded for item in self.queue_items),
            sum(item.skipped for item in self.queue_items),
            sum(item.errors for item in self.queue_items),
        )

    def process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self.current_index < 0:
            return

        item = self.queue_items[self.current_index]

        if self.cancelling:
            item.status = QueueItem.CANCELLED
        elif exit_status == QProcess.ExitStatus.CrashExit:
            item.status = QueueItem.FAILED
        elif exit_code == 0:
            item.status = QueueItem.COMPLETED
        elif item.errors > 0 and (item.downloaded > 0 or item.skipped > 0):
            # gallery-dl can continue downloading after individual files fail.
            # A non-zero exit code therefore does not necessarily mean that
            # the whole URL failed.
            item.status = QueueItem.COMPLETED_WITH_ERRORS
        else:
            item.status = QueueItem.FAILED

        self.refresh_queue_item(item)
        self.update_queue_progress()
        elapsed = time.monotonic() - item.started_at if item.started_at else 0
        self.log_message(
            f"Finished: {item.url} — {item.status} "
            f"(exit code {exit_code}, downloaded {item.downloaded}, "
            f"skipped {item.skipped}, failed {item.errors}, elapsed {elapsed:.1f}s)"
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
        totals = self.queue_totals()
        total_errors = totals[2]
        result_text = "Completed with errors" if total_errors else "Completed"
        self.status_label.setText(
            f"Queue {result_text.lower()}  |  "
            f"Downloaded: {totals[0]}  Skipped: {totals[1]}  Failed: {total_errors}"
        )
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def log_event(self, glyph: str, color: str, message: str) -> None:
        cursor = self.log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)

        glyph_format = cursor.charFormat()
        glyph_format.setForeground(QColor(color))
        glyph_format.setFontWeight(700)
        cursor.insertText(glyph + " ", glyph_format)

        text_format = cursor.charFormat()
        text_format.setForeground(self.palette().text().color())
        text_format.setFontWeight(400)
        cursor.insertText(message + "\n", text_format)

        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

    def log_message(self, message: str) -> None:
        self.log_event("", self.palette().text().color().name(), message)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("windows11")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
