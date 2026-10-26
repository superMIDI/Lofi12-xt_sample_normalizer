# Lofi12-xt_sample_normalizer
Batch normalize samples to guarantee they're converted by the Sonicware Lofi-12XT

## What it does
- Recursively scans a source folder for `.wav` files.
- Re-encodes each file as WAV / 44,100 Hz / signed 16-bit PCM.
- Preserves mono vs stereo channel count (and the first audio stream).
- Mirrors relative subfolders and writes to a separate output folder.
- Sanitizes output filenames: spaces and punctuation/special characters in the name are replaced with underscores (runs of such characters become one underscore); the `.wav` extension is retained. For example, `C3 - A!.wav` becomes `C3_A.wav`.
- Never changes source files. Existing output files are skipped, not overwritten.
- Writes a CSV report listing OK, skipped, and failed files.

## Requirement
FFmpeg is required for decoding/resampling/re-encoding. This project does not include FFmpeg.
Download a trusted Windows FFmpeg build from the official FFmpeg download page (https://ffmpeg.org/download.html) or your preferred trusted distributor. Put `ffmpeg.exe` beside the script/app, or install FFmpeg and add it to PATH.

## Run from Python
1. Install Python 3.10+ for Windows (enable Tkinter, included with the standard installer).
2. Put `lofi12xt_wav_batch_prep.py` and `ffmpeg.exe` in the same folder.
3. Double-click the `.py` file, or run:
   `py lofi12xt_wav_batch_prep.py`

## Build a Windows EXE
This makes a single-file Python app, but FFmpeg remains a separate companion file:
1. Install Python 3.10+.
2. Open Command Prompt in this folder.
3. Run `build_exe.bat`.
4. Copy `ffmpeg.exe` into the resulting `dist` folder beside `Lofi12XT_WAV_Batch_Prep.exe`.

The tool deliberately does not bundle FFmpeg because its license and distribution terms depend on the build you choose.

## Suggested settings
The tool uses 44.1 kHz, signed 16-bit PCM, while preserving mono/stereo. This is a conservative normalization preset based on your successful Audacity exports; it is not a guarantee that every WAV will be accepted by the device.

## Safety notes
- Choose an output folder outside the source folder.
- If an output file already exists, the tool skips it. Different input names can sanitize to the same output name; in that case the later file is skipped rather than overwriting the earlier output, and the CSV report records the destination name.
- Keep a backup of important samples.
- WAVs with multiple audio streams use the first audio stream only.
- Very large files or unusual codecs may fail; check the CSV report.


IMPORTANT COMPATIBILITY UPDATE (v3)
This version removes optional WAV metadata/ancillary chunks after FFmpeg conversion and writes a minimal RIFF/WAVE file containing only the standard fmt and data chunks. This is based on a successful Lofi-12XT test with a minimal-header WAV. It does not guarantee every source file will be accepted by the device.
