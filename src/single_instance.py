from __future__ import annotations

import json
import struct
import time
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


_MAX_MESSAGE_SIZE = 1024 * 1024
_ACK = b"\x06"
_REJECT = b"\x15"


class SingleInstance(QObject):
    """Coordinate one ScumGUI process and forward URL arguments to it."""

    urls_received = Signal(object)

    def __init__(self, lock_path: Path, server_name: str = "ScumGUI-instance") -> None:
        super().__init__()
        self.lock_path = Path(lock_path)
        self.server_name = server_name
        self.lock = QLockFile(str(self.lock_path))
        # A long-lived application must rely on PID checks, not lock age, to
        # distinguish a live instance from a lock left behind by a crash.
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept_connections)
        self._buffers: dict[int, bytearray] = {}

    def start_or_forward(self, urls: list[str], timeout_ms: int = 5000) -> bool:
        """Return True for the primary instance; otherwise forward and return False."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock.tryLock(0):
            self._listen()
            return True

        if self._forward(urls, timeout_ms):
            return False

        # The first process may have crashed after claiming the lock. QLockFile
        # removes a stale lock after checking its PID, allowing this launch to
        # recover instead of remaining permanently blocked.
        if self.lock.tryLock(0):
            self._listen()
            return True

        raise RuntimeError(
            "A ScumGUI instance holds the single-instance lock, but did not "
            "accept forwarded URLs. Try launching again after the existing "
            "instance finishes starting."
        )

    def _listen(self) -> None:
        # The lock ensures no live ScumGUI instance owns this endpoint. On
        # platforms that use filesystem sockets, remove a stale endpoint left
        # behind by a previous crash before listening again.
        QLocalServer.removeServer(self.server_name)
        if not self.server.listen(self.server_name):
            error = self.server.errorString()
            self.lock.unlock()
            raise RuntimeError(f"Could not create the ScumGUI instance server: {error}")

    def _forward(self, urls: list[str], timeout_ms: int) -> bool:
        payload = json.dumps(urls, ensure_ascii=False).encode("utf-8")
        if len(payload) > _MAX_MESSAGE_SIZE:
            raise RuntimeError("The forwarded URL list is too large.")
        message = struct.pack(">I", len(payload)) + payload
        deadline = time.monotonic() + timeout_ms / 1000

        while time.monotonic() < deadline:
            socket = QLocalSocket()
            socket.connectToServer(self.server_name)
            if socket.waitForConnected(200):
                if socket.write(message) != len(message):
                    socket.abort()
                    raise RuntimeError("Could not send URL arguments to the running ScumGUI instance.")
                if not socket.waitForBytesWritten(1000):
                    socket.abort()
                    raise RuntimeError("Could not send URL arguments to the running ScumGUI instance.")
                if not socket.waitForReadyRead(3000):
                    socket.abort()
                    raise RuntimeError("The running ScumGUI instance did not acknowledge the forwarded URLs.")
                accepted = bytes(socket.readAll()) == _ACK
                socket.disconnectFromServer()
                if not accepted:
                    raise RuntimeError("The running ScumGUI instance rejected the forwarded URL list.")
                return True

            socket.abort()
            time.sleep(0.05)

        return False

    def _accept_connections(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None:
                continue
            key = id(socket)
            self._buffers[key] = bytearray()
            socket.readyRead.connect(lambda key=key, socket=socket: self._read_request(key, socket))
            socket.disconnected.connect(lambda key=key: self._buffers.pop(key, None))
            socket.disconnected.connect(socket.deleteLater)
            self._read_request(key, socket)

    def _read_request(self, key: int, socket: QLocalSocket) -> None:
        buffer = self._buffers.get(key)
        if buffer is None:
            return
        buffer.extend(bytes(socket.readAll()))

        if len(buffer) < 4:
            return
        payload_size = struct.unpack(">I", buffer[:4])[0]
        if payload_size > _MAX_MESSAGE_SIZE:
            self._reject(socket)
            return
        if len(buffer) < 4 + payload_size:
            return

        try:
            urls = json.loads(buffer[4:4 + payload_size].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._reject(socket)
            return
        if not isinstance(urls, list) or any(not isinstance(url, str) for url in urls):
            self._reject(socket)
            return

        self.urls_received.emit(urls)
        socket.write(_ACK)
        socket.flush()
        socket.disconnectFromServer()

    @staticmethod
    def _reject(socket: QLocalSocket) -> None:
        socket.write(_REJECT)
        socket.flush()
        socket.disconnectFromServer()

    def close(self) -> None:
        if self.server.isListening():
            self.server.close()
            QLocalServer.removeServer(self.server_name)
        if self.lock.isLocked():
            self.lock.unlock()
