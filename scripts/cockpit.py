"""The cockpit overlay: what each fly saw, what its steering neurons did, what it
commanded, and what the computer finally sent to the ship, tick by tick.

Every number drawn comes from the run's mission.jsonl; the panels are re-rendered from
the logged errors with the same function the flies were shown. Nothing is animated that
was not measured.

  replay RUN --out cockpit.mp4      one frame per telemetry row, piped to ffmpeg
  live RUN [--port 8765]            tail the log of a running flight; open the page
                                    in a browser window beside KSP while recording
"""

import argparse
import http.server
import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flybywire.instruments import black_panel, render_panel  # noqa: E402
from flybywire.pilot import DEFAULT_BASELINE_HZ  # noqa: E402

W, H = 900, 620
COL = 300
HEADER = 60
PANEL_SCALE = 2
HZ_FULL = 120.0  # neuron bar full scale
SEATS = [("pitch", "Jeb", "pitch"), ("yaw", "Bill", "yaw"), ("throttle", "Bob", "throttle")]
BG, INK, DIM, FLY, SHIP, GRID = (12, 12, 16), (235, 235, 235), (120, 120, 130), (255, 170, 40), (90, 190, 255), (50, 50, 60)


def font(size):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", size)
    except OSError:
        return ImageFont.load_default(size)


F_BIG, F, F_SMALL = font(18), font(13), font(11)


def panel_for(role, row, cfg):
    if role == "throttle":
        dv = row.get("dv_remaining")
        return black_panel() if dv is None else render_panel(min(1.0, max(0.0, dv) / cfg["dv_scale"]))
    return render_panel(row[f"{role}_error_deg"] / cfg["error_scale_deg"])


def hbar(d, x, y, w, h, frac, color, *, marks=()):
    d.rectangle([x, y, x + w, y + h], outline=GRID)
    d.rectangle([x, y, x + int(w * min(1.0, max(0.0, frac))), y + h], fill=color)
    for m in marks:
        mx = x + int(w * m)
        d.line([mx, y - 3, mx, y + h + 3], fill=INK)


def gauge(d, x, y, w, h, value, color, label):
    """Centered gauge for a [-1, 1] stick or control; fills from the centre."""
    d.rectangle([x, y, x + w, y + h], outline=GRID)
    mid = x + w // 2
    v = max(-1.0, min(1.0, value))
    d.rectangle([min(mid, mid + int(v * w / 2)), y, max(mid, mid + int(v * w / 2)), y + h], fill=color)
    d.line([mid, y - 3, mid, y + h + 3], fill=INK)
    d.text((x, y - 15), f"{label} {value:+.3f}", fill=color, font=F_SMALL)


def draw_seat(d, img, x0, role, who, row, cfg):
    d.text((x0 + 10, HEADER + 6), f"{who} - {role}", fill=INK, font=F_BIG)
    panel = Image.fromarray(panel_for(role, row, cfg)).resize((90 * PANEL_SCALE, 160 * PANEL_SCALE), Image.NEAREST)
    px = x0 + (COL - panel.width) // 2
    py = HEADER + 32
    img.paste(panel, (px, py))
    d.rectangle([px - 1, py - 1, px + panel.width, py + panel.height], outline=DIM)
    if role == "throttle":
        cap = "engine off, panel dark" if row.get("dv_remaining") is None else f"dv to go {row['dv_remaining']:.1f} m/s"
    else:
        cap = f"error {row[f'{role}_error_deg']:+.2f} deg"
    d.text((x0 + 10, py + panel.height + 4), cap, fill=DIM, font=F_SMALL)

    n = row["neural"].get(role, {})
    y = py + panel.height + 24
    d.text((x0 + 10, y), "descending neurons DNp20 + DNpe017", fill=INK, font=F_SMALL)
    y += 16
    for side, key in (("L", "left_hz"), ("R", "right_hz")):
        hz = n.get(key)
        if hz is None:
            d.text((x0 + 10, y), f"{side}  computer flies this seat", fill=DIM, font=F_SMALL)
        else:
            d.text((x0 + 10, y), side, fill=INK, font=F_SMALL)
            hbar(d, x0 + 26, y + 1, 200, 10, hz / HZ_FULL, FLY, marks=(DEFAULT_BASELINE_HZ[side] / HZ_FULL,))
            d.text((x0 + 232, y), f"{hz:5.0f} Hz", fill=INK, font=F_SMALL)
        y += 18
    d.text((x0 + 10, y), "| = dark rate.  steer = (R - L) / 70 Hz", fill=DIM, font=F_SMALL)
    y += 34

    stick = row["sticks"][role]
    gauge(d, x0 + 26, y, 200, 12, stick, FLY, "fly stick")
    y += 42
    if role == "throttle":
        thr = row["controls"]["throttle"]
        d.text((x0 + 26, y - 15), f"throttle {thr:.2f}", fill=SHIP, font=F_SMALL)
        hbar(d, x0 + 26, y, 200, 12, thr, SHIP)
    else:
        gauge(d, x0 + 26, y, 200, 12, row["controls"][role], SHIP, f"to ship: {cfg['authority']} x stick + gyro")


def render_frame(row, cfg, t0):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    t = row["ut"] - t0
    hh, rem = divmod(int(t), 3600)
    mm, ss = divmod(rem, 60)
    d.text((10, 8), f"FLY ME TO THE MUN   T+{hh:02d}:{mm:02d}:{ss:02d}   {row['phase']}", fill=INK, font=F_BIG)
    ap = row["apoapsis"]
    ap_s = "escape" if ap >= 6_000_000 else f"{ap / 1000:,.0f} km"
    d.text(
        (10, 34),
        f"{row['body']}  alt {row['altitude'] / 1000:,.1f} km   Ap {ap_s}   Pe {row['periapsis'] / 1000:,.1f} km"
        + (f"   {row['g_force']:.1f} G" if "g_force" in row else ""),
        fill=DIM,
        font=F,
    )
    for i, (role, who, _) in enumerate(SEATS):
        x0 = i * COL
        if i:
            d.line([x0, HEADER, x0, H - 30], fill=GRID)
        draw_seat(d, img, x0, role, who, row, cfg)
    d.text(
        (10, H - 22),
        "panel -> fly connectome -> descending neurons -> stick -> computer augmentation -> ship.   orange: the fly   blue: the ship",
        fill=DIM,
        font=F_SMALL,
    )
    return img


def load_config(run):
    p = json.loads((run / "provenance.json").read_text())
    return p["config"]


def rows_of(path):
    with open(path) as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def replay(args):
    run = Path(args.run)
    cfg = load_config(run)
    rows = list(rows_of(run / "mission.jsonl"))[:: args.every]
    t0 = rows[0]["ut"]
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(args.fps), "-i", "-",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", args.out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for i, row in enumerate(rows):
        ff.stdin.write(render_frame(row, cfg, t0).tobytes())
        if i % 500 == 0:
            print(f"{i}/{len(rows)}", file=sys.stderr)
    ff.stdin.close()
    ff.wait()
    print(f"{len(rows)} frames -> {args.out} ({len(rows) / args.fps:.0f} s)")


PAGE = b"""<html><body style="margin:0;background:#0c0c10"><img id=f src=/frame.png>
<script>setInterval(()=>{f.src='/frame.png?'+Date.now()},200)</script></body></html>"""


def live(args):
    run = Path(args.run)
    state = {"png": None, "t0": None, "cfg": None}

    def tail():
        while not (run / "provenance.json").exists() or not (run / "mission.jsonl").exists():
            time.sleep(0.5)
        state["cfg"] = load_config(run)
        with open(run / "mission.jsonl", "rb") as f:
            backlog = [l for l in f.readlines() if l.endswith(b"\n")]  # a flight already under way: jump to now
            pending = backlog[-1:] if backlog else []
            if backlog:
                state["t0"] = json.loads(backlog[0])["ut"]
            while True:
                line = pending.pop() if pending else f.readline()
                if not line.endswith(b"\n"):
                    time.sleep(0.05)  # nothing new, or a row still being written
                    f.seek(f.tell() - len(line))
                    continue
                row = json.loads(line)
                if state["t0"] is None:
                    state["t0"] = row["ut"]
                buf = io.BytesIO()
                render_frame(row, state["cfg"], state["t0"]).save(buf, "PNG")
                state["png"] = buf.getvalue()

    threading.Thread(target=tail, daemon=True).start()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body, ctype = (PAGE, "text/html") if not self.path.startswith("/frame.png") else (state["png"] or b"", "image/png")
            self.send_response(200 if body else 503)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    print(f"cockpit live at http://127.0.0.1:{args.port}/  (tailing {run / 'mission.jsonl'})")
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("replay")
    r.add_argument("run")
    r.add_argument("--out", default="cockpit.mp4")
    r.add_argument("--fps", type=float, default=5.0, help="rows are logged at about 5/s wall time")
    r.add_argument("--every", type=int, default=1, help="use every Nth row")
    r.set_defaults(fn=replay)
    l = sub.add_parser("live")
    l.add_argument("run")
    l.add_argument("--port", type=int, default=8765)
    l.set_defaults(fn=live)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
