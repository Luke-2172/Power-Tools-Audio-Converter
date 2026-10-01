import sys, tempfile, hashlib, struct, threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'app'))
import converter as c

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); source=root/'input'; source.mkdir(); nested=source/'Voice'/'Vegas Overhaul.esp'/'Female'; nested.mkdir(parents=True)
    ff,fp=c.tools_at()
    for name,rate,ch,codec in [('mono.wav',22050,1,'pcm_s16le'),('stereo.WAV',48000,2,'pcm_s24le'),('float ü test.wav',96000,2,'pcm_f32le')]:
        c.execute([ff,'-v','error','-f','lavfi','-i','sine=frequency=440:duration=0.7','-ar',rate,'-ac',ch,'-c:a',codec,nested/name])
    (nested/'mono.LIP').write_bytes(b'test-lip-bytes')
    (nested/'bad.wav').write_bytes(b'not audio')
    loop=(nested/'mono.wav').read_bytes()+b'cue '+struct.pack('<I',4)+struct.pack('<I',0)
    loop=loop[:4]+struct.pack('<I',len(loop)-8)+loop[8:]; (nested/'loop.wav').write_bytes(loop)
    hashes={p:sha(p) for p in source.rglob('*') if p.is_file()}
    for preset in c.PRESETS:
        out=root/('out'+str(list(c.PRESETS).index(preset)))
        result=c.batch(source,out,preset)
        assert result['counts']=={'converted':3,'skipped':0,'failed':2},result
        for p in out.rglob('*.'+c.PRESETS[preset][0]): c.validate(ff,fp,p,c.PRESETS[preset][0],c.PRESETS[preset][2])
        if c.PRESETS[preset][0]=='ogg': assert (out/'Voice'/'Vegas Overhaul.esp'/'Female'/'mono.lip').read_bytes()==b'test-lip-bytes'
        rerun=c.batch(source,out,preset)
        assert rerun['counts']=={'converted':0,'skipped':3,'failed':2}
        assert not list(out.rglob('.fnv-converting-*'))
    assert all(sha(p)==v for p,v in hashes.items())
    event=threading.Event(); event.set()
    try: c.batch(source,root/'cancel',list(c.PRESETS)[0],stop=event)
    except c.scan.__globals__['Cancelled']: pass
    else: raise AssertionError('Cancelled scan continued')
    try: c.batch(source,source/'bad-output',list(c.PRESETS)[0])
    except ValueError: pass
    else: raise AssertionError('Nested output was allowed')
    print('PASS: all 3 presets; 22.05/48/96 kHz inputs; mono/stereo; 16/24-bit PCM and float; Unicode paths; recursive folders; LIP copying; malformed and cue WAV rejection; full output decode; unchanged sources; existing-output preservation; cancellation; nesting guard.')
