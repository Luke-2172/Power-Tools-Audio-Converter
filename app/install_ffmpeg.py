"""Optional, user-triggered Windows FFmpeg setup from a provider linked by ffmpeg.org."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
import urllib.request
import urllib.parse
from safe_io import reject_links
import zipfile

URL = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'

class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        p=urllib.parse.urlparse(newurl)
        if p.scheme!='https' or p.hostname not in ('www.gyan.dev','gyan.dev','github.com','objects.githubusercontent.com','release-assets.githubusercontent.com'):
            raise RuntimeError('Unexpected download redirect; use manual FFmpeg setup')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def get(url):
    return urllib.request.build_opener(HTTPSRedirects()).open(urllib.request.Request(url,headers={'User-Agent':'FNV-Audio-Converter/1.0'}),timeout=60)

def install(destination, log=print):
    from converter import check_tools
    destination=Path(destination)
    reject_links(destination)
    if os.name!='nt': raise RuntimeError('This installer is for Windows only')
    if (destination/'ffmpeg.exe').is_file() and (destination/'ffprobe.exe').is_file():
        check_tools(str(destination/'ffmpeg.exe'),str(destination/'ffprobe.exe'))
        log('Existing FFmpeg installation is ready.'); return
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fnv-ffmpeg-',dir=destination.parent) as temporary:
        temporary=Path(temporary); archive=temporary/'download.zip'
        log('Retrieving provider SHA-256 checksum...')
        with get(URL+'.sha256') as response: checksum=response.read(8192).decode('ascii')
        match=re.search(r'\b[0-9a-fA-F]{64}\b',checksum)
        if not match: raise RuntimeError('Provider checksum was missing or invalid')
        expected=match.group().lower(); digest=hashlib.sha256(); downloaded=0; last=-1
        log('Downloading FFmpeg essentials (roughly 100 MB). No audio files are uploaded.')
        with get(URL) as response, archive.open('wb') as out:
            total=int(response.headers.get('Content-Length',0))
            while True:
                chunk=response.read(1024*1024)
                if not chunk: break
                downloaded+=len(chunk)
                if downloaded>500*1024*1024: raise RuntimeError('Download unexpectedly exceeds 500 MB')
                out.write(chunk); digest.update(chunk)
                step=downloaded//(10*1024*1024)
                if step!=last:
                    log('Downloaded %d MB%s'%(downloaded//1024//1024,(' / %d MB'%(total//1024//1024)) if total else '')); last=step
        if digest.hexdigest()!=expected: raise RuntimeError('Download checksum mismatch. Nothing installed; try again.')
        staged=temporary/'staged'; staged.mkdir()
        with zipfile.ZipFile(archive) as z:
            for name in ('ffmpeg.exe','ffprobe.exe'):
                matches=[i for i in z.infolist() if i.filename.replace('\\','/').endswith('/bin/'+name)]
                if len(matches)!=1: raise RuntimeError('Expected executable missing or duplicated: '+name)
                if matches[0].file_size>200*1024**2: raise RuntimeError('Executable exceeds extraction limit')
                with z.open(matches[0]) as inp, (staged/name).open('wb') as out: shutil.copyfileobj(inp,out)
            for item in z.infolist():
                name=Path(item.filename).name
                if name.lower() in ('license','license.txt','readme.txt') and item.file_size<2*1024**2:
                    with z.open(item) as inp, (staged/name).open('wb') as out: shutil.copyfileobj(inp,out)
        check_tools(str(staged/'ffmpeg.exe'),str(staged/'ffprobe.exe'))
        destination.mkdir(exist_ok=True)
        for p in staged.iterdir():
            reject_links(destination/p.name)
            os.replace(p,destination/p.name)
        (destination/'download-source.txt').write_text(URL+'\nSHA256: '+expected+'\nProvider: https://www.gyan.dev/ffmpeg/builds/\n',encoding='utf-8')
        log('FFmpeg installed and Vorbis encoder checked.')
