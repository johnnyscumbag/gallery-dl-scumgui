# gallery-dl ScumGUI

A Windows desktop GUI frontend for [gallery-dl](https://github.com/mikf/gallery-dl).

## Current status

Early development. ScumGUI can now:

- Queue URLs
- Select a destination
- Locate a bundled `gallery-dl.exe` or fall back to the system PATH
- Launch gallery-dl without freezing the GUI
- Capture stdout/stderr into the built-in log
- Cancel a running gallery-dl process

The bundled engine/update system and richer queue/progress handling are planned next.

## Development

Python 3.14 + PySide6.

Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

Run:

```powershell
py src\scumgui.py
```

ScumGUI intentionally delegates downloading to gallery-dl instead of reimplementing extraction logic.
