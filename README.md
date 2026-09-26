# gallery-dl ScumGUI

A Windows desktop GUI frontend for [gallery-dl](https://github.com/mikf/gallery-dl).

> Early development / v0.1 scaffold.

## Goals

- Simple URL queue
- Download progress and live output
- Destination selection
- Profiles backed by gallery-dl configuration
- Preserve gallery-dl's existing capabilities instead of reimplementing the downloader
- Portable Windows build

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
