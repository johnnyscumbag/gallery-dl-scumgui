import importlib
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QListWidgetItem

from src.queue_persistence import QueuePersistence


@pytest.fixture(scope="module")
def app_module():
    application = QApplication.instance() or QApplication([])
    module = importlib.import_module("scumgui")
    yield module
    application.quit()


def make_window(app_module, monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return app_module.MainWindow()


def add_item(window, item):
    item.list_item = QListWidgetItem()
    window.queue_items.append(item)
    window.queue.addItem(item.list_item)
    window.refresh_queue_item(item)


def test_restored_items_are_waiting_without_starting_downloads(
    app_module, monkeypatch, tmp_path
):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    store = QueuePersistence()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        '[{"url":"https://example.com/one","destination":"D:\\\\One"},'
        '{"url":"https://example.com/two","destination":"D:\\\\Two"}]',
        encoding="utf-8",
    )

    window = app_module.MainWindow()

    assert [item.status for item in window.queue_items] == [
        app_module.QueueItem.WAITING,
        app_module.QueueItem.WAITING,
    ]
    assert window.process.state() == QProcess.ProcessState.NotRunning
    assert window.current_index == -1
    window.close()


def test_stop_all_persists_active_and_waiting_items_as_unfinished(
    app_module, monkeypatch, tmp_path
):
    window = make_window(app_module, monkeypatch, tmp_path)
    active = app_module.QueueItem("https://example.com/active", str(tmp_path))
    active.status = app_module.QueueItem.DOWNLOADING
    waiting = app_module.QueueItem("https://example.com/waiting", str(tmp_path))
    add_item(window, active)
    add_item(window, waiting)
    window.current_index = 0
    window.stop_all_requested = True

    window.process_finished(1, QProcess.ExitStatus.CrashExit)

    assert active.status == app_module.QueueItem.WAITING
    assert window.queue_store.load() == [
        {"url": active.url, "destination": active.destination},
        {"url": waiting.url, "destination": waiting.destination},
    ]
    assert window.current_index == -1
    window.close()


def test_failed_gallery_dl_launch_is_removed_from_persistent_queue(
    app_module, monkeypatch, tmp_path
):
    window = make_window(app_module, monkeypatch, tmp_path)
    item = app_module.QueueItem("https://example.com/fail", str(tmp_path / "output"))
    add_item(window, item)

    class FailedProcess:
        def state(self):
            return QProcess.ProcessState.NotRunning

        def setWorkingDirectory(self, _directory):
            pass

        def start(self, _engine, _args):
            pass

        def waitForStarted(self, _timeout):
            return False

    window.process = FailedProcess()
    monkeypatch.setattr(app_module, "find_gallery_dl", lambda: "gallery-dl.exe")

    window.start_download()

    assert item.status == app_module.QueueItem.FAILED
    assert window.queue_store.load() == []
    window.close()


def test_queue_write_errors_are_reported_by_main_window(
    app_module, monkeypatch, tmp_path
):
    window = make_window(app_module, monkeypatch, tmp_path)
    reported = []

    class FailingStore:
        path = tmp_path / "ScumGUI" / "queue.json"

        def save(self, _items):
            raise OSError("disk full")

    window.queue_store = FailingStore()
    monkeypatch.setattr(
        window,
        "log_event",
        lambda glyph, color, message: reported.append((glyph, color, message)),
        raising=False,
    )

    window.save_queue()

    assert len(reported) == 1
    assert reported[0][:2] == ("✗", "red")
    assert "queue.json" in reported[0][2]
    assert "disk full" in reported[0][2]
    window.close()


def test_queue_write_errors_are_not_swallowed(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    store = QueuePersistence()
    monkeypatch.setattr(
        "src.queue_persistence.os.replace",
        lambda *_args: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        store.save([])


def test_file_errors_remain_available_in_queue_tooltip(
    app_module, monkeypatch, tmp_path
):
    window = make_window(app_module, monkeypatch, tmp_path)
    item = app_module.QueueItem("https://example.com/gallery", str(tmp_path))
    item.status = app_module.QueueItem.DOWNLOADING
    item.pending_error_reason = "404 Not Found"
    add_item(window, item)
    window.current_index = 0

    assert window.consume_result_marker("[SCUMGUI_ERROR] Photos/image.jpg")

    tooltip = item.list_item.toolTip()
    assert "Photos/image.jpg" in tooltip
    assert "404 Not Found" in tooltip
    assert item.error_details == ["Photos/image.jpg — 404 Not Found"]
    window.close()


def test_retry_selected_resets_failed_and_partial_items(
    app_module, monkeypatch, tmp_path
):
    window = make_window(app_module, monkeypatch, tmp_path)
    failed = app_module.QueueItem("https://example.com/failed", str(tmp_path))
    failed.status = app_module.QueueItem.FAILED
    failed.downloaded = 2
    failed.skipped = 1
    failed.errors = 3
    failed.current_file = "old.jpg"
    failed.pending_error_reason = "old failure"
    failed.error_details.append("old.jpg — old failure")
    partial = app_module.QueueItem("https://example.com/partial", str(tmp_path))
    partial.status = app_module.QueueItem.COMPLETED_WITH_ERRORS
    completed = app_module.QueueItem("https://example.com/done", str(tmp_path))
    completed.status = app_module.QueueItem.COMPLETED

    for item in (failed, partial, completed):
        add_item(window, item)

    failed.list_item.setSelected(True)
    partial.list_item.setSelected(True)
    completed.list_item.setSelected(True)

    window.retry_selected()

    assert failed.status == app_module.QueueItem.WAITING
    assert failed.downloaded == failed.skipped == failed.errors == 0
    assert failed.current_file == ""
    assert failed.pending_error_reason == ""
    assert failed.error_details == []
    assert partial.status == app_module.QueueItem.WAITING
    assert completed.status == app_module.QueueItem.COMPLETED
    assert window.queue_store.load() == [
        {"url": failed.url, "destination": failed.destination},
        {"url": partial.url, "destination": partial.destination},
    ]
    window.close()



def test_move_waiting_item_keeps_list_order_and_persists_queue(
    app_module, monkeypatch, tmp_path
):
    window = make_window(app_module, monkeypatch, tmp_path)
    first = app_module.QueueItem("https://example.com/first", str(tmp_path))
    second = app_module.QueueItem("https://example.com/second", str(tmp_path))
    third = app_module.QueueItem("https://example.com/third", str(tmp_path))
    for item in (first, second, third):
        add_item(window, item)

    second.list_item.setSelected(True)
    window.move_selected_up()

    assert window.queue_items == [second, first, third]
    assert [window.queue.item(i) for i in range(window.queue.count())] == [
        second.list_item, first.list_item, third.list_item
    ]
    assert window.queue.currentItem() is second.list_item
    assert [entry["url"] for entry in window.queue_store.load()] == [
        second.url, first.url, third.url
    ]
    window.close()


def test_move_down_cannot_cross_active_or_nonwaiting_items(
    app_module, monkeypatch, tmp_path
):
    window = make_window(app_module, monkeypatch, tmp_path)
    active = app_module.QueueItem("https://example.com/active", str(tmp_path))
    active.status = app_module.QueueItem.DOWNLOADING
    waiting = app_module.QueueItem("https://example.com/waiting", str(tmp_path))
    finished = app_module.QueueItem("https://example.com/finished", str(tmp_path))
    finished.status = app_module.QueueItem.COMPLETED
    later = app_module.QueueItem("https://example.com/later", str(tmp_path))
    for item in (active, waiting, finished, later):
        add_item(window, item)
    window.current_index = 0
    window.process.state = lambda: QProcess.ProcessState.Running

    waiting.list_item.setSelected(True)
    window.move_selected_down()
    assert window.queue_items == [active, waiting, finished, later]

    later.list_item.setSelected(True)
    window.move_selected_up()
    assert window.queue_items == [active, waiting, finished, later]
    assert window.current_index == 0
    window.close()


def test_move_buttons_reorder_queue_when_idle(
    app_module, monkeypatch, tmp_path
):
    window = make_window(app_module, monkeypatch, tmp_path)
    first = app_module.QueueItem("https://example.com/first", str(tmp_path))
    second = app_module.QueueItem("https://example.com/second", str(tmp_path))
    first.status = app_module.QueueItem.COMPLETED
    for item in (first, second):
        add_item(window, item)

    second.list_item.setSelected(True)
    window.move_selected_up()

    assert window.queue_items == [second, first]
    assert window.current_index == -1
    window.close()
