import importlib
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication

from src.single_instance import SingleInstance


@pytest.fixture(scope="module")
def app_module():
    application = QApplication.instance() or QApplication([])
    module = importlib.import_module("scumgui")
    yield module, application
    application.quit()


def test_second_instance_forwards_urls_into_existing_queue(
    app_module, monkeypatch, tmp_path
):
    module, application = app_module
    monkeypatch.setenv("APPDATA", str(tmp_path))
    lock_path = tmp_path / "ScumGUI" / "instance.lock"
    server_name = f"ScumGUI-test-{uuid4().hex}"
    primary = SingleInstance(lock_path, server_name)
    window = module.MainWindow()
    assert primary.start_or_forward([])
    primary.urls_received.connect(window.receive_forwarded_urls)

    child_code = (
        "import sys; from pathlib import Path; "
        "from PySide6.QtCore import QCoreApplication; "
        "from single_instance import SingleInstance; "
        "app = QCoreApplication([]); "
        "instance = SingleInstance(Path(sys.argv[1]), sys.argv[2]); "
        "print(instance.start_or_forward(sys.argv[3:]))"
    )
    child_env = os.environ.copy()
    source_dir = str(Path(__file__).resolve().parents[1] / "src")
    child_env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [source_dir, child_env.get("PYTHONPATH")])
    )
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            child_code,
            str(lock_path),
            server_name,
            "https://example.com/forwarded",
        ],
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 6
    while child.poll() is None and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.01)
    if child.poll() is None:
        child.kill()
    stdout, stderr = child.communicate(timeout=1)

    assert child.returncode == 0, stderr
    assert stdout.strip() == "False"
    assert [item.url for item in window.queue_items] == [
        "https://example.com/forwarded"
    ]
    assert window.queue_store.load() == [
        {
            "url": "https://example.com/forwarded",
            "destination": str(Path("M:/Blah").resolve()),
        }
    ]

    primary.close()
    window.close()


def test_single_instance_lock_is_released_on_shutdown(tmp_path):
    lock_path = tmp_path / "ScumGUI" / "instance.lock"
    server_name = f"ScumGUI-test-{uuid4().hex}"
    first = SingleInstance(lock_path, server_name)
    assert first.start_or_forward([])
    first.close()

    next_launch = SingleInstance(lock_path, server_name)
    assert next_launch.start_or_forward([])
    next_launch.close()
