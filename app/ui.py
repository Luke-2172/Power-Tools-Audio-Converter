"""Shared desktop interface. Workers communicate with Tk through a bounded event queue."""
from pathlib import Path
import datetime, json, os, queue, threading, time, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from safe_io import scan, roots, Cancelled

VERSION='1.0'

def launch(kind):
    audio=kind=='audio'
    if audio: import converter as engine
    else: import downscaler as engine
    root=tk.Tk(); title='FNV Audio Converter' if audio else 'FNV Texture Downscaler'
    root.title(title+'  '+VERSION); root.geometry('980x800'); root.minsize(800,680)
    try:
        import ctypes
        if os.name=='nt': ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    style=ttk.Style()
    if 'vista' in style.theme_names(): style.theme_use('vista')
    style.configure('Title.TLabel',font=('Segoe UI',22,'bold'))
    style.configure('Sub.TLabel',font=('Segoe UI',10))
    root.option_add('*Font',('Segoe UI',10))
    outer=ttk.Frame(root,padding=20); outer.pack(fill='both',expand=True)
    outer.columnconfigure(1,weight=1); outer.rowconfigure(6,weight=1)
    ttk.Label(outer,text=title,style='Title.TLabel').grid(row=0,column=0,columnspan=3,sticky='w')
    subtitle='WAV to verified OGG Vorbis or PCM WAV' if audio else 'Normal-aware DDS resizing with complete mipmaps'
    ttk.Label(outer,text=subtitle+'  •  Originals are always kept',style='Sub.TLabel').grid(row=1,column=0,columnspan=3,sticky='w',pady=(0,15))
    source=tk.StringVar(); output=tk.StringVar(); recursive=tk.BooleanVar(value=True)
    maximum=tk.IntVar(value=1024); normal_max=tk.IntVar(value=1024)
    mode=tk.StringVar(value='' if audio else engine.MODES[0]); normal_fmt=tk.StringVar(value='' if audio else engine.FORMATS[0]); srgb=tk.BooleanVar(value=False); mips=tk.BooleanVar(value=True)
    preset=tk.StringVar(value=list(engine.PRESETS)[0] if audio else ''); quality=tk.IntVar(value=5); lips=tk.BooleanVar(value=True); tool_dir=tk.StringVar()
    note=tk.StringVar(); status=tk.StringVar(value='Choose an input folder. Preview lets you check the batch before writing files.')
    current=tk.StringVar(value=''); progress_text=tk.StringVar(value=''); events=queue.Queue(maxsize=600)
    stop=threading.Event(); state={'busy':False,'last_output':None,'report':None,'start':0,'total':0,'auto_output':''}
    controls=[]
    def choose(var,is_input=False):
        selected=filedialog.askdirectory(parent=root,initialdir=var.get() if Path(var.get()).is_dir() else None)
        if not selected: return
        var.set(selected)
        if is_input and (not output.get() or output.get()==state['auto_output']):
            name=' - FNV Audio' if audio else ' - FNV Textures'
            suggestion=str(Path(selected).with_name(Path(selected).name+name)); output.set(suggestion); state['auto_output']=suggestion
    for row,label,var in [(2,'1. Input folder',source),(3,'2. Output folder',output)]:
        ttk.Label(outer,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=5)
        entry=ttk.Entry(outer,textvariable=var); entry.grid(row=row,column=1,sticky='ew'); controls.append(entry)
        b=ttk.Button(outer,text='Browse…',command=lambda v=var,r=row:choose(v,r==2)); b.grid(row=row,column=2,padx=(8,0)); controls.append(b)
    opts=ttk.LabelFrame(outer,text='3. Settings',padding=12); opts.grid(row=4,column=0,columnspan=3,sticky='ew',pady=12); opts.columnconfigure(1,weight=1)
    def combo(parent,row,label,var,values):
        ttk.Label(parent,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=4)
        w=ttk.Combobox(parent,textvariable=var,values=values,state='readonly'); w.grid(row=row,column=1,sticky='ew',pady=4); controls.append(w); return w
    if audio:
        cb=combo(opts,0,'Use for',preset,list(engine.PRESETS))
        def update_note(*args): note.set(engine.NOTES[preset.get()])
        cb.bind('<<ComboboxSelected>>',update_note); update_note()
        ttk.Label(opts,textvariable=note,wraplength=840).grid(row=1,column=0,columnspan=2,sticky='w',pady=(4,8))
    else:
        combo(opts,0,'Color texture limit',maximum,(128,256,512,1024,2048,4096,8192))
        combo(opts,1,'Normal map limit',normal_max,(128,256,512,1024,2048,4096,8192))
        ttk.Label(opts,text='Pixels on the longest edge. Aspect ratio stays intact; smaller textures are copied unchanged.',wraplength=840).grid(row=2,column=0,columnspan=2,sticky='w',pady=(4,8))
    check=ttk.Checkbutton(opts,text='Include subfolders and preserve their structure',variable=recursive); check.grid(row=3,column=0,columnspan=2,sticky='w'); controls.append(check)
    tabs=ttk.Notebook(outer); tabs.grid(row=6,column=0,columnspan=3,sticky='nsew')
    preview=ttk.Frame(tabs,padding=8); tabs.add(preview,text='Batch preview'); preview.columnconfigure(0,weight=1); preview.rowconfigure(0,weight=1)
    tree=ttk.Treeview(preview,columns=('file','type','action'),show='headings',height=9)
    for name,label,width in [('file','Relative filename',400),('type','Type / size',150),('action','Planned result',240)]: tree.heading(name,text=label); tree.column(name,width=width,minwidth=70)
    tree.grid(row=0,column=0,sticky='nsew'); scroll=ttk.Scrollbar(preview,orient='vertical',command=tree.yview); scroll.grid(row=0,column=1,sticky='ns'); tree.configure(yscrollcommand=scroll.set)
    ttk.Label(preview,text='Preview shows the first 1,000 files. The full batch is processed and recorded in the report.').grid(row=1,column=0,sticky='w',pady=6)
    advanced=ttk.Frame(tabs,padding=14); advanced.columnconfigure(1,weight=1); tabs.add(advanced,text='Advanced')
    if audio:
        combo(advanced,0,'OGG quality',quality,tuple(range(1,11)))
        ttk.Label(advanced,text='5 is a balanced default. Higher values increase file size. Ignored for PCM WAV.').grid(row=1,column=0,columnspan=2,sticky='w',pady=8)
        chk=ttk.Checkbutton(advanced,text='Copy existing matching LIP files with OGG dialogue',variable=lips); chk.grid(row=2,column=0,columnspan=2,sticky='w'); controls.append(chk)
        ttk.Label(advanced,text='Optional FFmpeg folder').grid(row=3,column=0,sticky='w',pady=12)
        entry=ttk.Entry(advanced,textvariable=tool_dir); entry.grid(row=3,column=1,sticky='ew'); controls.append(entry)
        browse=ttk.Button(advanced,text='Choose FFmpeg folder…',command=lambda:choose(tool_dir)); browse.grid(row=4,column=0,sticky='w'); controls.append(browse)
        ttk.Label(advanced,text='Leave blank to use the tools installed by this app. FFmpeg is downloaded only when you click Install FFmpeg.',wraplength=800).grid(row=5,column=0,columnspan=2,sticky='w',pady=10)
    else:
        combo(advanced,0,'Texture type',mode,engine.MODES)
        combo(advanced,1,'Normal map format',normal_fmt,engine.FORMATS)
        for row,label,var in [(2,'Generate full mip chains for resized textures',mips),(3,'Use sRGB filtering for color textures',srgb)]:
            c=ttk.Checkbutton(advanced,text=label,variable=var); c.grid(row=row,column=0,columnspan=2,sticky='w',pady=7); controls.append(c)
        ttk.Label(advanced,text='Auto recognizes _n, _normal, _norm, _nor and _normalmap. Normals use RGB XYZ; packed DXT5nm maps need a different tool. Alpha is filtered separately.\n\nUnsupported DDS formats are left in the input folder and marked REVIEW. They are not mixed into the ready-to-use output.\n\nDXT5 saves space; RGBA8 avoids block-compression artifacts but is larger.',wraplength=800).grid(row=4,column=0,columnspan=2,sticky='w',pady=12)
    logs=ttk.Frame(tabs,padding=8); tabs.add(logs,text='Activity'); logs.rowconfigure(0,weight=1); logs.columnconfigure(0,weight=1)
    log=ScrolledText(logs,height=10,font=('Consolas',9),state='disabled',wrap='word'); log.grid(row=0,column=0,sticky='nsew')
    footer=ttk.Frame(outer); footer.grid(row=7,column=0,columnspan=3,sticky='ew',pady=(12,0)); footer.columnconfigure(0,weight=1)
    ttk.Label(footer,textvariable=status,wraplength=900).grid(row=0,column=0,columnspan=4,sticky='w')
    ttk.Label(footer,textvariable=current,wraplength=900).grid(row=1,column=0,columnspan=4,sticky='w',pady=3)
    bar=ttk.Progressbar(footer); bar.grid(row=2,column=0,columnspan=3,sticky='ew',pady=6); ttk.Label(footer,textvariable=progress_text).grid(row=2,column=3,padx=8)
    actions=ttk.Frame(footer); actions.grid(row=3,column=0,columnspan=4,sticky='w',pady=6)
    def emit(k,v): events.put((k,v))
    def set_busy(value):
        state['busy']=value
        for w in controls: w.configure(state='disabled' if value else ('readonly' if isinstance(w,ttk.Combobox) else 'normal'))
        stop_button.configure(state='normal' if value else 'disabled')
    def values():
        if not source.get().strip() or not output.get().strip(): raise ValueError('Select both input and output folders.')
        roots(source.get(),output.get())
        if audio: return (source.get(),output.get(),preset.get(),quality.get(),recursive.get(),lips.get(),tool_dir.get())
        return (source.get(),output.get(),maximum.get(),normal_max.get(),mode.get(),normal_fmt.get(),srgb.get(),mips.get(),recursive.get())
    def start(preview_only=False):
        if state['busy']: return
        try: args=values()
        except Exception as exc: messagebox.showerror('Check settings',str(exc),parent=root); return
        stop.clear(); set_busy(True); state['start']=time.monotonic(); state['total']=0
        state['last_output']=args[1]; bar['value']=0; progress_text.set(''); current.set('')
        status.set('Scanning files…' if preview_only else 'Working… You can stop after the current file.')
        if preview_only: tree.delete(*tree.get_children())
        else: tabs.select(logs)
        def worker():
            try:
                if not preview_only: engine.batch(*args,stop=stop,emit=emit); return
                rootpath=Path(args[0]).resolve(); files=scan(rootpath,'.wav' if audio else '.dds',args[4] if audio else args[8],stop)
                rows=[]
                for p in files[:1000]:
                    if stop.is_set(): raise Cancelled('Preview stopped')
                    rel=p.relative_to(rootpath); target=Path(args[1])/rel
                    if audio:
                        target=target.with_suffix('.'+engine.PRESETS[args[2]][0]); typ='WAV'; action=args[2].split(' - ')[-1]
                    else:
                        try:
                            with p.open('rb') as f: w,h,_,fmt=engine.header(f.read(128))
                            kind=engine.classify(p,args[4]); size=engine.target_size(w,h,args[3] if kind=='normal' else args[2]); typ=f'{kind} · {w}×{h}'
                            action='Copy unchanged' if size==(w,h) else f'{size[0]}×{size[1]}'
                        except Exception as exc: typ='Review'; action=str(exc)
                    if target.exists(): action='Skip existing output'
                    rows.append((str(rel),typ,action))
                emit('preview',(rows,len(files)))
            except Cancelled as exc: emit('stopped',str(exc))
            except Exception as exc: emit('error',str(exc))
        threading.Thread(target=worker,daemon=True).start()
    def install():
        if state['busy']: return
        if not messagebox.askyesno('Install FFmpeg','Download FFmpeg from gyan.dev (roughly 100 MB)?\n\nOnly the encoder is downloaded. Your audio is never uploaded.',parent=root): return
        set_busy(True); stop_button.configure(state='disabled'); status.set('Installing FFmpeg. See Activity for download progress.'); tabs.select(logs)
        def worker():
            try:
                from install_ffmpeg import install as setup
                setup(engine.APP/'tools',lambda s:emit('log',s)); emit('installed','FFmpeg is ready. Choose your folders and start conversion.')
            except Exception as exc: emit('error','FFmpeg setup failed: '+str(exc))
        threading.Thread(target=worker,daemon=True).start()
    preview_button=ttk.Button(actions,text='Preview batch',command=lambda:start(True)); preview_button.pack(side='left',padx=(0,8)); controls.append(preview_button)
    go=ttk.Button(actions,text='Convert audio' if audio else 'Downscale textures',command=start); go.pack(side='left',padx=(0,8)); controls.append(go)
    def stop_job(): stop.set(); status.set('Stopping after the current file…')
    stop_button=ttk.Button(actions,text='Stop',command=stop_job,state='disabled'); stop_button.pack(side='left',padx=(0,8))
    if audio:
        ib=ttk.Button(actions,text='Install FFmpeg',command=install); ib.pack(side='left',padx=(0,8)); controls.append(ib)
    def open_path(report=False):
        p=state['report'] if report else state['last_output']
        if not p or not Path(p).exists(): messagebox.showinfo('Nothing to open','Run a batch first.',parent=root); return
        if os.name=='nt':
            if report:
                # Open reports as plain text: never invoke a spreadsheet on generated data.
                import subprocess
                notepad=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32'/'notepad.exe'
                subprocess.Popen([str(notepad),str(p)],shell=False)
            else: os.startfile(p)
        else: messagebox.showinfo('Path',str(p),parent=root)
    ttk.Button(actions,text='Open output',command=open_path).pack(side='left',padx=(0,8))
    ttk.Button(actions,text='View report',command=lambda:open_path(True)).pack(side='left')
    def append_log(text):
        log.configure(state='normal'); log.insert('end',text+'\n')
        lines=int(log.index('end-1c').split('.')[0])
        if lines>600: log.delete('1.0',f'{lines-500}.0')
        log.see('end'); log.configure(state='disabled')
    def poll():
        try:
            for _ in range(80):
                k,v=events.get_nowait()
                if k=='log': append_log(str(v))
                elif k=='current': current.set(v)
                elif k=='total': state['total']=v; bar['maximum']=max(1,v)
                elif k=='progress': bar['value']=v; progress_text.set(f"{v} / {state['total']}")
                elif k=='preview':
                    rows,total=v
                    for row in rows: tree.insert('','end',values=row)
                    set_busy(False); tabs.select(preview); status.set(f'{total} files found. Review the preview, then start processing.'); current.set('')
                elif k in ('error','stopped'):
                    set_busy(False); status.set(v); current.set(''); append_log(v)
                    if k=='error': messagebox.showerror('Could not finish',v,parent=root)
                elif k=='installed': set_busy(False); tool_dir.set(str(engine.APP/'tools')); status.set(v)
                elif k=='done':
                    set_busy(False); state['report']=v['report']; state['last_output']=str(Path(v['report']).parent)
                    text=('Stopped' if v['cancelled'] else 'Finished')+' — '+', '.join(f'{count} {key}' for key,count in v['counts'].items())
                    status.set(text); current.set(f"Report saved • elapsed {time.monotonic()-state['start']:.0f}s"); append_log(text+'\nReport: '+v['report'])
        except queue.Empty: pass
        root.after(100,poll)
    def close():
        if state['busy']: messagebox.showinfo('Task running','Use Stop and wait for the current file to finish. An encoder installation must finish before closing.',parent=root); return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close); root.after(100,poll)
    # A noninteractive startup smoke check used during packaging; not an end-user setting.
    if os.environ.get('FNV_GUI_SMOKE_TEST')=='1': root.after(800,root.destroy)
    root.mainloop()
