from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QProcess, QSettings, Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from progress import parse_progress
from queue_persistence import QueuePersistence

from PySide6.QtWidgets import (
    QStyleFactory,
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "ScumGUI"
APP_VERSION = "1.2.1"


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

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.process_finished)

        self.queue_items: list[QueueItem] = []
        self.current_index = -1
        self.cancelling = False
        self.cancel_all_requested = False
        self.stop_all_requested = False
        self.queue_store = QueuePersistence()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Compact application header.
        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 2, 0)
        header.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(
            QIcon(str(resource_path("assets/scumgui.png"))).pixmap(48, 48)
        )
        logo.setFixedSize(48, 48)
        header.addWidget(logo)

        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)

        title = QLabel(f"{APP_NAME} {APP_VERSION}")
        title_font = title.font()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title_layout.addWidget(title)

        subtitle = QLabel("gallery-dl frontend")
        subtitle.setObjectName("appSubtitle")
        title_layout.addWidget(subtitle)

        header.addLayout(title_layout)
        header.addStretch(1)
        layout.addLayout(header)

        # Compact download input area.
        input_grid = QGridLayout()
        input_grid.setContentsMargins(2, 2, 2, 2)
        input_grid.setHorizontalSpacing(10)
        input_grid.setVerticalSpacing(7)
        input_grid.setColumnStretch(1, 1)

        url_label = QLabel("URL")
        url_label.setMinimumWidth(75)
        input_grid.addWidget(url_label, 0, 0)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste a gallery-dl URL here…")
        self.url_edit.returnPressed.connect(self.add_url)
        input_grid.addWidget(self.url_edit, 0, 1)

        self.add_button = QPushButton("Add to Queue")
        self.add_button.setMinimumWidth(130)
        self.add_button.clicked.connect(self.add_url)
        input_grid.addWidget(self.add_button, 0, 2)

        destination_label = QLabel("Destination")
        destination_label.setMinimumWidth(75)
        input_grid.addWidget(destination_label, 1, 0)

        self.destination_edit = QLineEdit("M:\\Blah")
        input_grid.addWidget(self.destination_edit, 1, 1)

        self.browse_button = QPushButton("…")
        self.browse_button.setToolTip("Choose a destination folder")
        self.browse_button.setFixedWidth(36)
        self.browse_button.clicked.connect(self.browse_destination)
        input_grid.addWidget(self.browse_button, 1, 2)

        layout.addLayout(input_grid)

        queue_box = QGroupBox("Queue")
        queue_layout = QVBoxLayout(queue_box)
        queue_layout.setContentsMargins(8, 8, 8, 8)
        queue_layout.setSpacing(7)

        self.queue = QListWidget()
        self.queue.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.queue.setAlternatingRowColors(True)
        self.queue.setUniformItemSizes(False)
        queue_layout.addWidget(self.queue, 1)

        self.queue_progress = QProgressBar()
        self.queue_progress.setRange(0, 1)
        self.queue_progress.setValue(0)
        self.queue_progress.setFormat("Queue: 0 / 0")
        self.queue_progress.setTextVisible(True)
        self.queue_progress.setFixedHeight(18)
        queue_layout.addWidget(self.queue_progress)

        controls = QHBoxLayout()
        controls.setSpacing(7)

        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self.remove_selected)
        controls.addWidget(remove_button)

        clear_button = QPushButton("Clear Finished")
        clear_button.clicked.connect(self.clear_finished)
        controls.addWidget(clear_button)

        controls.addStretch(1)

        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.start_download)
        controls.addWidget(self.download_button)

        self.stop_all_button = QPushButton("Stop All")
        self.stop_all_button.setEnabled(False)
        self.stop_all_button.setToolTip("Stop the queue and leave unfinished items ready to resume.")
        self.stop_all_button.clicked.connect(self.stop_all)
        controls.addWidget(self.stop_all_button)

        self.cancel_button = QPushButton("Cancel Current")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_download)
        controls.addWidget(self.cancel_button)

        self.cancel_all_button = QPushButton("Cancel All")
        self.cancel_all_button.setEnabled(False)
        self.cancel_all_button.clicked.connect(self.cancel_all)
        controls.addWidget(self.cancel_all_button)

        queue_layout.addLayout(controls)
        layout.addWidget(queue_box, 2)

        status_box = QGroupBox("Current Item")
        status_layout = QVBoxLayout(status_box)
        status_layout.setContentsMargins(8, 8, 8, 8)
        status_layout.setSpacing(6)

        self.status_label = QLabel("Ready")
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        status_layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Idle")
        status_layout.addWidget(self.progress)

        layout.addWidget(status_box)

        log_box = QGroupBox("Activity")
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(8, 8, 8, 8)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log.setPlaceholderText("Download activity will appear here…")
        log_layout.addWidget(self.log)

        layout.addWidget(log_box, 2)

        disabled_button_color = self.palette().color(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Text,
        ).name()
        self.setStyleSheet(f"""
            QMainWindow {{
                background: palette(window);
            }}
            QLabel#appSubtitle {{
                color: #a8a8a8;
            }}
            QLineEdit, QListWidget, QTextEdit {{
                border-radius: 5px;
            }}
            QListWidget {{
                alternate-background-color: #353535;
            }}
            QListWidget::item:selected {{
                background: palette(highlight);
                color: palette(highlighted-text);
            }}
            QPushButton {{
                min-height: 28px;
                padding-left: 10px;
                padding-right: 10px;
                border-radius: 9px;
                background-color: palette(button);
                border: 1px solid palette(mid);
            }}
            QPushButton:hover {{
                background-color: palette(midlight);
            }}
            QPushButton:disabled {{
                color: {disabled_button_color};
            }}
            QProgressBar {{
                border: 1px solid palette(mid);
                border-radius: 5px;
                background-color: palette(base);
                text-align: center;
            }}
            QProgressBar::chunk {{
                border-radius: 4px;
                background-color: palette(highlight);
            }}
            QScrollBar:vertical {{
                background: palette(base);
                width: 10px;
                margin: 0;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: #555555;
                min-height: 30px;
                border-radius: 5px;
                border: none;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #666666;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
                border: none;
                height: 0;
                image: none;
            }}
            QScrollBar::up-arrow:vertical,
            QScrollBar::down-arrow:vertical {{
                width: 0;
                height: 0;
                border: none;
                image: none;
            }}
            QScrollBar:horizontal {{
                background: palette(base);
                height: 10px;
                margin: 0;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: #555555;
                min-width: 30px;
                border-radius: 5px;
                border: none;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: #666666;
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {{
                background: transparent;
                border: none;
                width: 0;
                image: none;
            }}
            QScrollBar::left-arrow:horizontal,
            QScrollBar::right-arrow:horizontal {{
                width: 0;
                height: 0;
                border: none;
                image: none;
            }}
            QGroupBox {{
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
        """)
        self.log_message("ScumGUI started.")
        engine = find_gallery_dl()
        if engine:
            self.log_message(f"gallery-dl engine: {engine}")
        else:
            self.log_message("gallery-dl engine not found; PATH fallback unavailable.")

        self.restore_queue()

    def restore_queue(self) -> None:
        restored = 0
        for saved in self.queue_store.load():
            item = QueueItem(saved["url"], saved["destination"])
            self.queue_items.append(item)
            list_item = QListWidgetItem()
            item.list_item = list_item
            self.queue.addItem(list_item)
            self.refresh_queue_item(item)
            restored += 1
        if restored:
            self.update_queue_progress()
            self.log_message(f"Restored {restored} unfinished queue item(s).")

    def save_queue(self) -> None:
        self.queue_store.save(self.queue_items)

    def browse_destination(self) -> None:
        current = Path(self.destination_edit.text().strip()).expanduser()
        if not current.is_dir():
            current = Path("M:\\Blah")

        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose destination folder",
            str(current),
        )
        if selected:
            self.destination_edit.setText(str(Path(selected)))

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

        destination_path = Path(destination_text).expanduser()
        if not destination_path.is_absolute():
            QMessageBox.warning(
                self,
                APP_NAME,
                "The destination must be an absolute folder path.",
            )
            return

        destination = str(destination_path.resolve())

        item = QueueItem(url, destination)
        self.queue_items.append(item)

        list_item = QListWidgetItem()
        item.list_item = list_item
        self.queue.addItem(list_item)
        self.refresh_queue_item(item)

        self.url_edit.clear()
        self.update_queue_progress()
        self.save_queue()
        self.log_message(f"Added: {destination}  —  {url}")

    def refresh_queue_item(self, item: QueueItem) -> None:
        if item.list_item is None:
            return

        display_destination = item.destination

        stats = f"D:{item.downloaded}  S:{item.skipped}  E:{item.errors}"
        if item.status == QueueItem.DOWNLOADING and item.current_file:
            text = f"[{item.status}]  {stats}  {display_destination}  —  {item.current_file}"
        else:
            text = f"[{item.status}]  {stats}  {display_destination}  —  {item.url}"
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
        selected_rows = sorted(
            {self.queue.row(item) for item in self.queue.selectedItems()},
            reverse=True,
        )
        if not selected_rows:
            return

        current_item = (
            self.queue_items[self.current_index]
            if 0 <= self.current_index < len(self.queue_items)
            else None
        )
        removable_rows = [
            row
            for row in selected_rows
            if 0 <= row < len(self.queue_items)
            and self.queue_items[row] is not current_item
        ]
        if not removable_rows:
            return

        removable = set(removable_rows)
        self.queue_items = [
            item
            for row, item in enumerate(self.queue_items)
            if row not in removable
        ]

        for row in removable_rows:
            self.queue.takeItem(row)

        if current_item is not None:
            self.current_index = self.queue_items.index(current_item)
        else:
            self.current_index = -1

        self.update_queue_progress()
        self.save_queue()

    def clear_finished(self) -> None:
        finished = {
            QueueItem.COMPLETED,
            QueueItem.COMPLETED_WITH_ERRORS,
            QueueItem.FAILED,
            QueueItem.CANCELLED,
        }
        current_item = (
            self.queue_items[self.current_index]
            if 0 <= self.current_index < len(self.queue_items)
            else None
        )

        removable_rows = [
            row
            for row, item in enumerate(self.queue_items)
            if item.status in finished and item is not current_item
        ]
        if not removable_rows:
            return

        for row in reversed(removable_rows):
            self.queue.takeItem(row)

        removable = set(removable_rows)
        self.queue_items = [
            item
            for row, item in enumerate(self.queue_items)
            if row not in removable
        ]

        if current_item is not None:
            self.current_index = self.queue_items.index(current_item)
        else:
            self.current_index = -1

        self.update_queue_progress()
        self.save_queue()

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

        destination = Path(item.destination)
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
        self.save_queue()

        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Downloading…")
        item.started_at = time.monotonic()
        self.status_label.setText(f"Downloading: {destination}  —  {item.url}  |  D:0  S:0  E:0")
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_all_button.setEnabled(True)
        self.stop_all_button.setEnabled(True)
        self.cancelling = False
        self.stop_all_requested = False

        self.process.setWorkingDirectory(str(destination))
        self.log_message(f"Starting: {destination}  —  {item.url}")
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

    def terminate_gallery_process(self) -> None:
        target = Path(find_gallery_dl() or "").resolve()
        if not target.is_file():
            self.process.kill()
            self.process.waitForFinished(1500)
            return

        # gallery-dl can create more than one process for a single run.
        # Find only the bundled ScumGUI executable by its full path, so
        # independently launched gallery-dl processes are never touched.
        env = os.environ.copy()
        env["SCUMGUI_GALLERY_PATH"] = str(target)

        ps_script = r"""
$target = $env:SCUMGUI_GALLERY_PATH
$processes = @(Get-CimInstance Win32_Process -Filter "Name='gallery-dl.exe'" |
    Where-Object {
        $_.ExecutablePath -and
        ([IO.Path]::GetFullPath($_.ExecutablePath) -ieq $target)
    } |
    Select-Object ProcessId, ParentProcessId)

if ($processes.Count -gt 0) {
    $ids = @($processes | ForEach-Object { [int]$_.ProcessId })
    $roots = @($processes | Where-Object { $ids -notcontains [int]$_.ParentProcessId })

    if ($roots.Count -eq 0) {
        $roots = $processes
    }

    $roots | ForEach-Object {
        & taskkill.exe /PID $_.ProcessId /T /F *> $null
    }
}
"""

        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        self.process.waitForFinished(3000)
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)

    def cancel_download(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return

        self.cancelling = True
        self.log_message("Stopping gallery-dl…")
        self.terminate_gallery_process()

    def stop_all(self) -> None:
        """Stop the queue without cancelling unfinished items."""
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.save_queue()
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFormat("Stopped")
            self.status_label.setText("Queue stopped — unfinished items are ready to resume.")
            self.download_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.stop_all_button.setEnabled(False)
            self.cancel_all_button.setEnabled(False)
            return

        self.stop_all_requested = True
        self.cancelling = False
        self.log_message("Stopping gallery-dl and leaving the queue ready to resume…")
        self.terminate_gallery_process()

    def cancel_all(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            for item in self.queue_items:
                if item.status == QueueItem.WAITING:
                    item.status = QueueItem.CANCELLED
                    self.refresh_queue_item(item)
            self.update_queue_progress()
            self.save_queue()
            self.start_next_or_finish()
            return

        self.cancel_all_requested = True
        self.cancelling = True
        self.log_message("Stopping gallery-dl and cancelling remaining queue items…")
        for item in self.queue_items:
            if item.status == QueueItem.WAITING:
                item.status = QueueItem.CANCELLED
                self.refresh_queue_item(item)
        self.update_queue_progress()
        self.save_queue()
        # Do not start another gallery-dl process after this one exits.
        # Waiting items are cancelled before their destination folders are
        # created, so Cancel All cannot leave a trail of empty folders.
        self.terminate_gallery_process()

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
        # gallery-dl's terminal output emits its own start/success path
        # lines. ScumGUI already receives cleaner --Print event markers, so
        # suppress both the "* <path>" success line and the ".\\<path>"
        # start line.
        stripped = line.strip()
        return bool(
            re.match(r"^\*\s+.+$", stripped)
            or re.match(r"^\.\\.+$", stripped)
        )

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

        if self.stop_all_requested:
            item.status = QueueItem.WAITING
            self.refresh_queue_item(item)
            self.update_queue_progress()
            self.save_queue()
            self.stop_all_requested = False
            self.current_index = -1
            self.cancelling = False
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFormat("Stopped")
            self.status_label.setText("Queue stopped — unfinished items are ready to resume.")
            self.download_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.stop_all_button.setEnabled(False)
            self.cancel_all_button.setEnabled(False)
            self.log_message("Queue stopped. Click Download to resume.")
            return

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
        self.save_queue()
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

        if self.cancel_all_requested:
            self.cancel_all_requested = False
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.progress.setFormat("Cancelled")
            totals = self.queue_totals()
            self.status_label.setText(
                f"Queue cancelled  |  Downloaded: {totals[0]}  "
                f"Skipped: {totals[1]}  Failed: {totals[2]}"
            )
            self.download_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.stop_all_button.setEnabled(False)
            self.cancel_all_button.setEnabled(False)
            return

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
        self.stop_all_button.setEnabled(False)
        self.cancel_all_button.setEnabled(False)

    def closeEvent(self, event) -> None:
        self.save_queue()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.cancelling = True
            self.terminate_gallery_process()
        event.accept()

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
    style_name = "Fusion"
    qt_conf = app_root() / "qt.conf"
    if qt_conf.is_file():
        style_settings = QSettings(str(qt_conf), QSettings.Format.IniFormat)
        requested_style = str(
            style_settings.value("ScumGUI/Style", "Fusion")
        ).strip()
        if requested_style:
            available_styles = {
                style.lower(): style for style in QStyleFactory.keys()
            }
            style_name = available_styles.get(requested_style.lower(), "Fusion")

    app.setStyle(style_name)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
