# ScumGUI

A Windows desktop GUI frontend for [gallery-dl](https://github.com/mikf/gallery-dl).

## Current status

Early development. ScumGUI can now:

- Queue multiple URLs
- Select a download destination
- Locate a bundled `gallery-dl.exe` in `Resources\\`
- Fall back to a system `gallery-dl` on PATH
- Launch gallery-dl without freezing the GUI
- Show live download progress
- Track downloaded, skipped, and failed files for each queue item
- Show queue-wide result totals
- Capture gallery-dl diagnostics in the built-in log
- Cancel a running gallery-dl process

ScumGUI intentionally delegates downloading to gallery-dl instead of reimplementing its extraction and download logic.

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
