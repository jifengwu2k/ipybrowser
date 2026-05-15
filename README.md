# IPyBrowser

A web browser built with **PyQt6** and **QtWebEngine**, featuring an
embedded **IPython console** for scripting live page content in Python.
Point at any element, pick it, and it lands as an `lxml` object in your
global namespace — no JavaScript required.

## Features

- **Full web rendering** via `QWebEngineView`
- **Navigation bar** with back, forward, refresh, and URL entry
- **DOM element picker** — click "Select Element", then click anything on the page to capture its HTML as an `lxml.html` element in the IPython console
- **IPython console** — full interactive Python with the page DOM available:
  - `html` — the `lxml.html` root element tree of the current page
  - `temp0`, `temp1`, ... — each picked element as an `lxml.html` node
  - `self` — the `QWebEngineView` instance (control the browser programmatically)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python ipybrowser.py
```
