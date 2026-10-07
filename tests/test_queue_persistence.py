from types import SimpleNamespace

from src.queue_persistence import QueuePersistence


def test_queue_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))

    store = QueuePersistence()
    waiting = SimpleNamespace(
        status="Waiting",
        url="https://example.com/one",
        destination=r"D:\Downloads\One",
    )
    downloading = SimpleNamespace(
        status="Downloading",
        url="https://example.com/two",
        destination=r"X:\Downloads\Two",
    )
    completed = SimpleNamespace(
        status="Completed",
        url="https://example.com/done",
        destination=r"D:\Downloads\Done",
    )

    store.save([waiting, downloading, completed])

    assert store.path.exists()
    assert store.load() == [
        {
            "url": "https://example.com/one",
            "destination": r"D:\Downloads\One",
        },
        {
            "url": "https://example.com/two",
            "destination": r"X:\Downloads\Two",
        },
    ]


def test_corrupt_queue_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))

    store = QueuePersistence()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not valid json", encoding="utf-8")

    assert store.load() == []


def test_invalid_entries_are_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))

    store = QueuePersistence()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        '[{"url":"https://example.com/good","destination":"D:\\\\Good"},'
        '{"url":"","destination":"D:\\\\Bad"},'
        '{"url":"https://example.com/no-destination","destination":""},'
        '"not an object"]',
        encoding="utf-8",
    )

    assert store.load() == [
        {
            "url": "https://example.com/good",
            "destination": r"D:\Good",
        }
    ]
