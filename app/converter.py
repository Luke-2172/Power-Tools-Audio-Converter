"""FNV Audio Converter: Windows GUI and testable conversion engine. Python 3.9+."""
import csv
import datetime
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import math
import time
from safe_io import roots,scan,reject_links,atomic_publish,atomic_write,SafeCSV

APP = Path(__file__).resolve().parent
PRESETS = {
    'Dialogue / voice - OGG mono': ('ogg', 'libvorbis', 1),
    'Music / 2D ambience - OGG stereo': ('ogg', 'libvorbis', 2),
    'Weapons / 3D effects - PCM WAV mono': ('wav', 'pcm_s16le', 1),
}
NOTES = {
    list(PRESETS)[0]: 'Ogg Vorbis | 44,100 Hz | mono. Preserves timing and filenames. Existing LIP files can be copied; new LIP files are not generated.',
    list(PRESETS)[1]: 'Ogg Vorbis | 44,100 Hz | stereo. Use for music or non-positional ambience where the game supports OGG.',
    list(PRESETS)[2]: '16-bit PCM WAV | 44,100 Hz | mono. Use for weapon sounds and common 3D effects. Files with loop/cue chunks are held for manual review.',
}


def execute(command,timeout=1200):
    # File-backed logs prevent a corrupt decoder from filling RAM with diagnostics.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        r=subprocess.Popen([str(x) for x in command],stdin=subprocess.DEVNULL,
            stdout=stdout,stderr=stderr,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        started=time.monotonic()
        try:
            while r.poll() is None:
                if time.monotonic()-started>timeout: raise RuntimeError('Processing timed out; input retained')
                if os.fstat(stdout.fileno()).st_size>8*1024**2 or os.fstat(stderr.fileno()).st_size>16*1024**2:
                    raise RuntimeError('Audio tool exceeded diagnostic size limit')
                time.sleep(0.05)
        except BaseException:
            r.kill(); r.wait(); raise
        if r.returncode:
            stderr.seek(0,2); end=stderr.tell(); stderr.seek(max(0,end-8000))
            raise RuntimeError(stderr.read().decode('utf-8',errors='replace') or 'Audio tool failed')
        stdout.seek(0,2)
        if stdout.tell()>8*1024*1024: raise RuntimeError('Unexpectedly large tool response')
        stdout.seek(0); return stdout.read().decode('utf-8',errors='replace')


def tools_at(folder=''):
    ext = '.exe' if os.name == 'nt' else ''
    for base in ([Path(folder)] if folder else [APP/'tools']):
        a, b = base/('ffmpeg'+ext), base/('ffprobe'+ext)
        if a.is_file() and b.is_file(): return str(a.resolve()), str(b.resolve())
    if not folder and os.name != 'nt':
        a, b = shutil.which('ffmpeg'), shutil.which('ffprobe')
        if a and b: return a, b
    raise RuntimeError('FFmpeg and FFprobe were not found. Click Install FFmpeg, or select a folder containing both programs.')


def check_tools(ffmpeg, ffprobe):
    if 'libvorbis' not in execute([ffmpeg, '-hide_banner', '-encoders'],timeout=30):
        raise RuntimeError('This FFmpeg build lacks libvorbis. Use the supplied installer.')
    execute([ffprobe, '-version'],timeout=30)


def probe(ffprobe, path):
    return json.loads(execute([ffprobe, '-v', 'error', '-protocol_whitelist', 'file', '-show_streams', '-show_format', '-of', 'json', path],timeout=60))


def wav_loop_chunks(path):
    # Conversion can discard RIFF cue/smpl loop metadata; do not silently break looping sounds.
    tags = set()
    with path.open('rb') as f:
        header = f.read(12)
        if header[:4] not in (b'RIFF', b'RF64') or header[8:] != b'WAVE': raise ValueError('Not a RIFF/RF64 WAV file')
        end = path.stat().st_size
        while f.tell()+8 <= end:
            chunk = f.read(8); n = int.from_bytes(chunk[4:], 'little')
            if chunk[:4] in (b'cue ', b'smpl'): tags.add(chunk[:4].decode().strip())
            if n == 0xffffffff: break
            if f.tell()+n>end: raise ValueError('Truncated WAV chunk')
            f.seek(n+(n % 2), 1)
    return tags


def validate(ffmpeg, ffprobe, path, container, channels, source_duration=None):
    info = probe(ffprobe, path)
    streams = info.get('streams', [])
    expected = 'vorbis' if container == 'ogg' else 'pcm_s16le'
    if len(streams) != 1: raise ValueError('Expected exactly one audio stream')
    stream = streams[0]
    if stream.get('codec_name') != expected or stream.get('codec_type') != 'audio':
        raise ValueError('Incorrect audio codec')
    if int(stream.get('sample_rate', 0)) != 44100 or int(stream.get('channels', 0)) != channels:
        raise ValueError('Incorrect sample rate or channel count')
    if info.get('format', {}).get('format_name') != container: raise ValueError('Incorrect container format')
    duration = float(info.get('format', {}).get('duration', 0))
    if not math.isfinite(duration) or duration <= 0: raise ValueError('Empty or invalid audio duration')
    if source_duration is not None and abs(duration-source_duration) > max(0.08, source_duration*0.001):
        raise ValueError('Unexpected duration change')
    # Decode the entire output rather than trusting only its header.
    execute([ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-xerror', '-protocol_whitelist', 'file', '-i', path,
             '-map', '0:a:0', '-f', 'null', '-'])
    return duration


def convert_one(src, dest, preset, quality, ffmpeg, ffprobe):
    container, codec, channels = PRESETS[preset]
    reject_links(src); reject_links(dest)
    if src.stat().st_size > 8*1024**3: raise ValueError('WAV exceeds 8 GiB batch limit')
    chunks = wav_loop_chunks(src)
    if chunks: raise ValueError('REVIEW: WAV has '+', '.join(sorted(chunks))+' loop/cue metadata; retained original for manual handling')
    before = probe(ffprobe, src)
    audio = [s for s in before.get('streams', []) if s.get('codec_type') == 'audio']
    if len(audio) != 1: raise ValueError('Input must contain exactly one audio stream')
    if before.get('format', {}).get('format_name') != 'wav': raise ValueError('Input is not a WAV container')
    duration = float(before.get('format', {}).get('duration', 0))
    if not math.isfinite(duration) or duration <= 0: raise ValueError('Input has no audio duration')
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(dest.parent).free < duration*44100*channels*2+32*1024**2: raise OSError('Insufficient space for conversion')
    fd, name = tempfile.mkstemp(prefix='.fnv-converting-', suffix='.'+container, dir=dest.parent)
    os.close(fd); temporary = Path(name)
    try:
        command = [ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-xerror', '-y', '-protocol_whitelist', 'file', '-f', 'wav', '-i', src,
                   '-map', '0:a:0', '-vn', '-sn', '-dn', '-map_metadata', '-1', '-map_chapters', '-1',
                   '-ar', '44100', '-ac', str(channels), '-c:a', codec]
        if container == 'ogg': command += ['-q:a', str(quality)]
        else: command += ['-fflags', '+bitexact', '-flags:a', '+bitexact']
        command += ['-f', container, temporary]
        execute(command)
        duration = validate(ffmpeg, ffprobe, temporary, container, channels, duration)
        atomic_publish(temporary,dest)
        return duration
    finally:
        temporary.unlink(missing_ok=True)


def copy_lip(src, dest):
    matches = [p for p in src.parent.iterdir() if p.is_file() and p.stem.lower() == src.stem.lower() and p.suffix.lower() == '.lip']
    if len(matches) > 1: return 'Multiple matching LIP files; review manually'
    if not matches: return ''
    target = dest.with_suffix('.lip')
    if target.exists(): return 'Existing output LIP retained'
    reject_links(matches[0]); atomic_write(target,source=matches[0])
    return 'Existing LIP copied'


def batch(source, output, preset, quality=5, recursive=True, lips=True, tool_folder='', stop=None, emit=lambda *x: None):
    source,output=roots(source,output)
    if preset not in PRESETS or quality not in range(1, 11): raise ValueError('Invalid preset or quality')
    ffmpeg, ffprobe = tools_at(tool_folder); check_tools(ffmpeg, ffprobe)
    files=scan(source,'.wav',recursive,stop)
    if not files: raise ValueError('No WAV files found in the selected input folder')
    targets = {}
    for p in files:
        if p.is_symlink() or source not in p.resolve().parents: raise ValueError('Linked input file outside scan: '+str(p))
        rel = p.relative_to(source).with_suffix('.'+PRESETS[preset][0]); key = str(rel).casefold()
        if key in targets: raise ValueError('Two WAV names map to the same output: '+str(rel))
        targets[key] = p
    output.mkdir(parents=True, exist_ok=True)
    report = output/('conversion-report-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.csv')
    counts = {'converted':0, 'skipped':0, 'failed':0}; cancelled = False
    emit('total', len(files)); emit('log', 'Preset: '+preset+' | quality '+str(quality))
    with report.open('w', encoding='utf-8-sig', newline='') as f:
        writer = SafeCSV(f); writer.writerow(['Input','Output','Status','Seconds','Details'])
        for i, src in enumerate(files, 1):
            if stop is not None and stop.is_set(): cancelled = True; break
            dest = output/src.relative_to(source).with_suffix('.'+PRESETS[preset][0])
            if output not in dest.resolve().parents: raise ValueError('Output folder contains a link outside selected destination')
            seconds = ''; details = ''
            emit('current',str(src.relative_to(source)))
            try:
                reject_links(src); reject_links(dest)
                if dest.exists():
                    status = 'skipped'; details = 'Output already exists; not modified or revalidated'
                else:
                    seconds = round(convert_one(src,dest,preset,quality,ffmpeg,ffprobe),4)
                    status = 'converted'; details = 'Codec, rate, channels, duration and full decode verified'
                    if lips and PRESETS[preset][0] == 'ogg':
                        try:
                            note = copy_lip(src,dest)
                            if note: details += '; '+note
                        except Exception as exc: details += '; LIP copy failed: '+str(exc)
            except Exception as exc:
                status = 'failed'; details = str(exc)
            counts[status] += 1
            writer.writerow([str(src),str(dest),status,seconds,details]); f.flush()
            emit('log', status.upper()+': '+details); emit('progress',i)
    result = {'counts':counts,'cancelled':cancelled,'report':str(report),'output':str(output),'total':len(files)}
    emit('done', result)
    return result

