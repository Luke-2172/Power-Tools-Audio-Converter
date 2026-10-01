FNV AUDIO CONVERTER 1.0 - WINDOWS 10/11 x64

1. Extract the entire ZIP into a local folder you control.
2. Double-click FNV Audio Converter.exe. Python is included; no Python installation is needed.
3. On first use, click Install FFmpeg and accept its one-time download (roughly 100 MB).
   Alternatively select a folder containing ffmpeg.exe and ffprobe.exe in Advanced.
4. Choose the WAV input folder and a separate output folder.
5. Choose Dialogue, Music/2D ambience, or Weapons/3D effects.
6. Click Preview batch to inspect filenames, then Convert audio.
7. Open output or View report when finished.

Keep app and runtime beside the EXE. This is a portable folder application, not a single
self-contained EXE. Nothing needs administrator rights. Once FFmpeg is installed, the app
works offline. Source files and existing outputs are never overwritten or deleted.

Dialogue: OGG Vorbis, mono, 44,100 Hz. Music/2D ambience: OGG Vorbis, stereo, 44,100 Hz.
Effects: 16-bit PCM WAV, mono, 44,100 Hz. OGG is not suitable for every engine sound path;
weapon/common sound effects should use the WAV preset. The converter does not edit ESP
references, filenames, dialogue IDs, or installation paths for you.

Subfolder paths and basenames are preserved. Matching existing LIP files can be copied.
LIP generation is not included. Keep WAV originals for GECK preview/LIP generation.
Quality 5 is the OGG default; change it in Advanced. Existing outputs are skipped, not
revalidated. Choose a fresh output folder to reconvert with different settings.

Stop finishes the current file before stopping. WAV files with cue/smpl metadata need
manual review to avoid losing loop markers. Inputs above 8 GiB or commands exceeding
20 minutes per stage are refused/timed out. Full output decode is checked before publishing.

Read AUDIT.txt for review findings and TEST-RESULTS.txt for what was actually tested.
This application is not digitally signed; do not disable Windows security software.
If blocked or an error appears, send the exact message and small generated report.
The executable's SHA-256 is supplied in SHA256SUMS.txt for integrity checking.
The source code is in app; native launcher/build source is in source.
