import csv
import struct
import os
import re
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from datetime import datetime

APP_NAME = "Lofi-12XT WAV Batch Prep"


def sanitize_filename(stem):
    """Replace spaces/punctuation in a filename stem with underscores."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    return cleaned or "sample"

def rewrite_as_minimal_pcm_wav(path):
    """Keep only the standard fmt and data chunks in a little-endian PCM WAV."""
    raw = Path(path).read_bytes()
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("FFmpeg output is not a standard RIFF/WAVE file")

    chunks = {}
    pos = 12
    while pos + 8 <= len(raw):
        chunk_id = raw[pos:pos + 4]
        chunk_size = struct.unpack_from("<I", raw, pos + 4)[0]
        start = pos + 8
        end = start + chunk_size
        if end > len(raw):
            raise ValueError(f"Invalid WAV chunk size for {chunk_id!r}")
        if chunk_id in (b"fmt ", b"data") and chunk_id not in chunks:
            chunks[chunk_id] = raw[start:end]
        pos = end + (chunk_size & 1)

    if b"fmt " not in chunks or b"data" not in chunks:
        raise ValueError("WAV is missing its fmt or data chunk")
    fmt = chunks[b"fmt "]
    if len(fmt) < 16 or struct.unpack_from("<H", fmt, 0)[0] != 1:
        raise ValueError("Expected uncompressed PCM WAV output")

    def pack_chunk(tag, payload):
        pad = b"\x00" if len(payload) & 1 else b""
        return tag + struct.pack("<I", len(payload)) + payload + pad

    body = b"WAVE" + pack_chunk(b"fmt ", fmt) + pack_chunk(b"data", chunks[b"data"])
    minimal = b"RIFF" + struct.pack("<I", len(body)) + body
    Path(path).write_bytes(minimal)


def find_ffmpeg():
    here = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    candidates = [here / "ffmpeg.exe", here / "ffmpeg", Path(shutil.which("ffmpeg") or "")]
    for p in candidates:
        try:
            if p.is_file():
                return str(p)
        except OSError:
            pass
    return None

# Import sys after function definition is fine: function runs after module import completes.
import sys

class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.geometry("760x520")
        root.minsize(650, 450)
        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self.status = tk.StringVar(value="Choose a source folder and an output folder.")
        self.busy = False

        frame = ttk.Frame(root, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Lofi-12XT WAV Batch Prep", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Recursively re-exports WAVs as minimal-header 44.1 kHz, 16-bit PCM, preserving mono/stereo. Originals are never modified.",
                  wraplength=710).pack(anchor="w", pady=(4, 14))

        self._folder_row(frame, "Source folder:", self.source)
        self._folder_row(frame, "Output folder:", self.output)

        opts = ttk.LabelFrame(frame, text="Processing", padding=10)
        opts.pack(fill="x", pady=10)
        ttk.Label(opts, text="Output audio: 44,100 Hz • signed 16-bit PCM • original channels • minimal WAV header").pack(anchor="w")
        ttk.Label(opts, text="Existing output files are skipped; source files are never overwritten.").pack(anchor="w", pady=(4, 0))

        self.start_btn = ttk.Button(frame, text="Prepare WAV files", command=self.start)
        self.start_btn.pack(anchor="w", pady=(2, 10))
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x")
        ttk.Label(frame, textvariable=self.status, wraplength=710).pack(anchor="w", pady=(8, 4))
        self.log = tk.Text(frame, height=12, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, pady=(4, 0))
        self._append("Ready. FFmpeg must be placed beside this program as ffmpeg.exe, or be available on PATH. Output WAVs use only the standard fmt and data chunks.")
        self._check_ffmpeg()

    def _folder_row(self, parent, label, var):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=15).pack(side="left")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Browse…", command=lambda: self._browse(var)).pack(side="left")

    def _browse(self, var):
        chosen = filedialog.askdirectory()
        if chosen:
            var.set(chosen)

    def _append(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _check_ffmpeg(self):
        ff = find_ffmpeg()
        if ff:
            self._append("FFmpeg found: " + ff)
        else:
            self._append("FFmpeg NOT found. Add ffmpeg.exe beside this app or install FFmpeg and add it to PATH.")

    def start(self):
        if self.busy:
            return
        src = Path(self.source.get()).expanduser()
        out = Path(self.output.get()).expanduser()
        if not src.is_dir():
            messagebox.showerror(APP_NAME, "Choose an existing source folder.")
            return
        if not str(self.output.get()).strip():
            messagebox.showerror(APP_NAME, "Choose an output folder.")
            return
        try:
            if out.resolve() == src.resolve() or src.resolve() in out.resolve().parents:
                messagebox.showerror(APP_NAME, "Choose an output folder outside the source folder.")
                return
        except OSError:
            pass
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            messagebox.showerror(APP_NAME, "FFmpeg was not found. Place ffmpeg.exe beside this program or add FFmpeg to PATH.")
            return
        self.busy = True
        self.start_btn.configure(state="disabled")
        self.progress.start(10)
        threading.Thread(target=self._worker, args=(src, out, ffmpeg), daemon=True).start()

    def _worker(self, src, out, ffmpeg):
        rows = []
        ok = skipped = failed = 0
        files = sorted(p for p in src.rglob("*") if p.is_file() and p.suffix.lower() == ".wav")
        self.root.after(0, self._append, f"Found {len(files)} WAV file(s).")
        for i, inp in enumerate(files, 1):
            try:
                rel = inp.relative_to(src)
                safe_name = sanitize_filename(inp.stem) + ".wav"
                dest_rel = rel.with_name(safe_name)
                dest = out / dest_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    skipped += 1
                    rows.append([str(rel), "SKIPPED", f"Output already exists; left unchanged ({dest_rel})"])
                    self.root.after(0, self._append, f"[SKIP] {rel} → {dest_rel} — output already exists")
                    continue
                # Write to a unique temporary WAV, then atomically rename to avoid partial outputs.
                tmp = dest.with_name(dest.stem + ".__lofi12xt_tmp__.wav")
                if tmp.exists():
                    tmp.unlink()
                cmd = [
                    ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(inp), "-map", "0:a:0", "-vn",
                    "-ar", "44100", "-c:a", "pcm_s16le", "-map_metadata", "-1",
                    "-rf64", "never", str(tmp)
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
                    detail = (proc.stderr or f"FFmpeg exited with code {proc.returncode}").strip()
                    try:
                        if tmp.exists():
                            tmp.unlink()
                    except OSError:
                        pass
                    failed += 1
                    rows.append([str(rel), "FAILED", detail])
                    self.root.after(0, self._append, f"[FAIL] {rel} — {detail[:220]}")
                else:
                    # Strip optional metadata/ancillary chunks that may confuse stricter samplers.
                    try:
                        rewrite_as_minimal_pcm_wav(tmp)
                    except Exception as e:
                        tmp.unlink(missing_ok=True)
                        failed += 1
                        rows.append([str(rel), "FAILED", f"Could not make minimal WAV header: {e}"])
                        self.root.after(0, self._append, f"[FAIL] {rel} — could not make minimal WAV header: {e}")
                        continue
                    # Never overwrite a pre-existing output; recheck immediately before publishing.
                    if dest.exists():
                        tmp.unlink(missing_ok=True)
                        skipped += 1
                        rows.append([str(rel), "SKIPPED", f"Output appeared during processing; left unchanged ({dest_rel})"])
                    else:
                        os.replace(tmp, dest)
                        ok += 1
                        rows.append([str(rel), "OK", f"Exported to {dest_rel}; 44100 Hz, signed 16-bit PCM; minimal fmt/data-only WAV; channels preserved"])
                        self.root.after(0, self._append, f"[OK] {rel} → {dest_rel}")
            except Exception as e:
                failed += 1
                rows.append([str(inp), "FAILED", repr(e)])
                self.root.after(0, self._append, f"[FAIL] {inp}: {e}")
            self.root.after(0, self.status.set, f"Processing {i}/{len(files)} • OK {ok} • skipped {skipped} • failed {failed}")

        try:
            out.mkdir(parents=True, exist_ok=True)
            report = out / f"lofi12xt_batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with report.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Relative path", "Result", "Details"])
                writer.writerows(rows)
            self.root.after(0, self._append, f"Report saved: {report}")
        except Exception as e:
            self.root.after(0, self._append, f"Could not save report: {e}")

        summary = f"Finished. {ok} prepared, {skipped} skipped, {failed} failed. Report saved in output folder."
        self.root.after(0, self._finish, summary)

    def _finish(self, summary):
        self.progress.stop()
        self.start_btn.configure(state="normal")
        self.busy = False
        self.status.set(summary)
        messagebox.showinfo(APP_NAME, summary)

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
