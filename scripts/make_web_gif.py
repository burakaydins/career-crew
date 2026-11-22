"""Builds docs/web-demo.gif and docs/web.png from the real web interface.

It runs the mock demo once, starts `career-crew web`, opens the replay page
(`/?replay=<run>&adim=N`, which shows the first N events at once) in headless Chrome and
takes one screenshot per step. Pillow joins the frames. Needs Chrome or Chromium; set
CHROME to its path if it is not found. Nothing is drawn by hand: every frame is the page
as the browser renders it.

    python scripts/make_web_gif.py
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
WINDOW = (1500, 1420)
CROP_TOP = 0
OUT_WIDTH = 1100
# Event counts after which the conversation has something new to show (see events.jsonl of the mock run).
STEPS = [3, 8, 9, 14, 17, 18, 23, 28, 33]
HOLD_MS = [1400, 1400, 2200, 1800, 1400, 1400, 2000, 1600, 4000]


def find_chrome() -> str:
    candidates = [os.environ.get("CHROME", ""), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  shutil.which("google-chrome") or "", shutil.which("chromium") or "", shutil.which("chromium-browser") or ""]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    sys.exit("Chrome or Chromium not found. Set CHROME=/path/to/chrome.")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    chrome = find_chrome()
    work = Path(tempfile.mkdtemp(prefix="career-crew-gif-"))
    runs, port = work / "runs", free_port()
    subprocess.run([sys.executable, "-m", "app.cli", "--ilan", "examples/ilan.md", "--cv", "examples/cv.md", "--evet", "--hizli",
                    "--runs", str(runs), "--hafiza", str(work / "mem")], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    run = next(runs.iterdir()).name
    server = subprocess.Popen([sys.executable, "-m", "app.cli", "web", "--acma", "--hizli", "--port", str(port), "--runs", str(runs),
                               "--hafiza", str(work / "mem")], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/config", timeout=1)
                break
            except OSError:
                time.sleep(0.25)
        frames = []
        for n in STEPS:
            shot = work / f"step{n}.png"
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={WINDOW[0]},{WINDOW[1]}",
                            "--virtual-time-budget=8000", f"--screenshot={shot}", f"http://127.0.0.1:{port}/?replay={run}&adim={n}"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            img = Image.open(shot).convert("RGB").crop((0, CROP_TOP, WINDOW[0], WINDOW[1]))
            frames.append(img.resize((OUT_WIDTH, round(img.height * OUT_WIDTH / img.width)), Image.LANCZOS))
            print("frame", n)
        DOCS.mkdir(exist_ok=True)
        frames[-1].save(DOCS / "web.png", optimize=True)
        pal = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
        pal[0].save(DOCS / "web-demo.gif", save_all=True, append_images=pal[1:], duration=HOLD_MS, loop=0, optimize=True)
        print("wrote docs/web.png and docs/web-demo.gif")
    finally:
        server.terminate()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
