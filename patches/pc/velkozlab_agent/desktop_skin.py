"""Applied after the preserved desktop module. All recorder/review methods remain original."""
import math
from tkinter import messagebox
from .ui_theme import BG, SURFACE, ACCENT
_old_init=Desktop.__init__
_old_populate=Desktop.populate

def _header_art(canvas,width):
    canvas.delete('all')
    for y in range(125):
        t=y/124;r=5+int(3*(1-t));g=14+int(8*(1-t));b=25+int(14*(1-t))
        canvas.create_line(0,y,width,y,fill=f'#{r:02x}{g:02x}{b:02x}')
    for i in range(13):
        x=width*.63+i*8
        canvas.create_arc(x,-165+i*3,x+300,185+i*3,start=210,extent=110,style='arc',outline='#10365d' if i%2 else '#0a284a')
    for pad,color,line in [(0,'#1262ad',9),(1,'#2a9ef0',5),(2,'#36cdff',2)]:
        canvas.create_arc(16,24,114,99,start=10,extent=160,style='arc',outline=color,width=line)
        canvas.create_arc(16,13,114,88,start=190,extent=160,style='arc',outline=color,width=line)
    canvas.create_oval(47,35,82,70,fill='#229fea',outline='');canvas.create_oval(58,32,72,53,fill=BG,outline='')
    canvas.create_text(143,42,text='VOID',anchor='w',fill='#f3f7ff',font=('Segoe UI',28,'bold'))
    canvas.create_text(258,42,text='EYE',anchor='w',fill='#18c6f4',font=('Segoe UI',28,'bold'))
    canvas.create_text(145,80,text='당신의 게임을, 더 선명하게.',anchor='w',fill='#9bc2e3',font=('Malgun Gothic',11))
    if width>820:
        canvas.create_line(370,22,370,99,fill='#286283')
        canvas.create_text(402,43,text='기록하고, 분석하고, 더 강해지세요.',anchor='w',fill='#e7f2ff',font=('Malgun Gothic',16,'bold'))
        canvas.create_text(402,80,text='내 경기, 필요한 순간부터 다시 보기',anchor='w',fill='#a2c1de',font=('Malgun Gothic',11))
    if width>1250:
        canvas.create_line(width-190,25,width-190,99,fill='#203f59')
        canvas.create_text(width-165,45,text='V L A B  S T U D I O',anchor='w',fill='#80b9f3',font=('Segoe UI',10,'bold'))
        canvas.create_text(width-165,73,text='PLAY ANALYTICS',anchor='w',fill='#568bb7',font=('Segoe UI',8))
        canvas.create_text(width-165,91,text='FOR A HIGHER YOU',anchor='w',fill='#568bb7',font=('Segoe UI',8))

def _init(self,root,launch_agent=True):
    _old_init(self,root,launch_agent)
    root.title('VOID EYE · PC 0.40 — Voice')
    root.geometry('1480x960');root.minsize(1120,820)
    old_status=str(self.status.cget('text'))
    children=self.shell.winfo_children()
    # Only remove the old header/action widgets, preserving the live content and footer.
    for child in children[:3]: child.destroy()
    top=ttk.Frame(self.shell);top.pack(fill='x',before=self.content)
    art=tk.Canvas(top,height=125,bg=BG,highlightthickness=0)
    art.pack(fill='x');art.bind('<Configure>',lambda e:_header_art(art,e.width))
    row=ttk.Frame(top);row.pack(fill='x',pady=(0,14))
    ttk.Button(row,text='▣   저장 폴더 열기',command=self.open_recordings).pack(side='left')
    self.status=ttk.Label(row,text=old_status,style='Status.TLabel',wraplength=960)
    self.status.pack(side='right',fill='x',expand=True,padx=(18,0))
    actions=ttk.Frame(top);actions.pack(fill='x',pady=(0,12))
    ttk.Label(actions,text='▣   PC 원본 보관     /     맵 데이터 선택 전송',style='Muted.TLabel').pack(side='left')
    ttk.Button(actions,text='종료',style='Danger.TButton',command=self.close).pack(side='right',padx=(10,0))
    from .account_panel import AccountPanel
    self.account_login=ttk.Button(actions,text='Google 로그인',style='Accent.TButton',command=lambda:AccountPanel(root,self.account))
    self.account_logout=ttk.Button(actions,text='로그아웃',command=self.logout_account)
    self.account_name=ttk.Label(actions,style='Muted.TLabel')
    self.update_account_actions()
    self.content.configure(padding=(0,8))
    # Footer belongs to the existing shell and survives review navigation.
    for child in self.shell.winfo_children():
        if isinstance(child,ttk.Label):child.configure(text='VOID EYE     ›     내 경기, 필요한 순간부터 다시 보기                                     PC 0.40  |  VLab Studio')

def _resend(self):
    ids=self.table.selection()
    if not ids:
        messagebox.showinfo('맵 데이터 전송','먼저 전송할 경기를 선택하세요.',parent=self.root);return
    sid=ids[0]
    if self.jobs.resend(sid):
        self.populate()
        messagebox.showinfo('맵 데이터 전송 예약','선택한 경기의 맵 데이터 전송을 예약했습니다. 녹화 중이면 종료 후 진행합니다.\nPC에 업로드 완료가 표시되면 휴대폰에서 새 경기 동기화를 눌러 주세요.',parent=self.root)
    else:
        messagebox.showinfo('전송 준비 확인','로그인 상태, 경기 녹화 완료, PC 미니맵 원본을 확인하세요.\n현재 처리 중인 경기는 완료 후 다시 시도하세요.',parent=self.root)

def _show_list(self):
    self.selected=None;self.clear()
    border=tk.Frame(self.content,bg=SURFACE,highlightbackground='#1b4665',highlightthickness=1)
    border.pack(fill='both',expand=True)
    area=ttk.Frame(border,padding=18,style='Card.TFrame');area.pack(fill='both',expand=True)
    toolbar=ttk.Frame(area,style='Card.TFrame');toolbar.pack(fill='x',pady=(0,16))
    ttk.Label(toolbar,text='▤  게임 목록',style='Heading.TLabel',background=SURFACE).pack(side='left')
    ttk.Button(toolbar,text='↥  맵 데이터 모바일 전송',style='Accent.TButton',command=lambda:_resend(self)).pack(side='right')
    ttk.Button(toolbar,text='분석 열기',command=self.open_selected).pack(side='right',padx=10)
    self.count_label=ttk.Label(area,text='',style='Muted.TLabel',background=SURFACE);self.count_label.pack(anchor='w',pady=(0,12))
    frame=ttk.Frame(area,style='Card.TFrame');frame.pack(fill='both',expand=True)
    cols=('date','champion','length','size','recording','analysis')
    self.table=ttk.Treeview(frame,columns=cols,show='headings',selectmode='browse')
    for col,label,width in zip(cols,('날짜 · 시작 시간','내 챔피언','경기 시간','영상 크기','녹화','PC 분석 · 선택 전송'),(190,105,90,95,100,520)):
        self.table.heading(col,text=label);self.table.column(col,width=width,minwidth=width,stretch=col=='analysis',anchor='w')
    sy=ttk.Scrollbar(frame,orient='vertical',command=self.table.yview);sy.pack(side='right',fill='y')
    sx=ttk.Scrollbar(frame,orient='horizontal',command=self.table.xview);sx.pack(side='bottom',fill='x')
    self.table.configure(yscrollcommand=sy.set,xscrollcommand=sx.set);self.table.pack(fill='both',expand=True)
    self.table.tag_configure('even',background='#0a192a');self.table.tag_configure('odd',background='#0c1e31')
    self.table.bind('<Double-1>',self.open_selected);self.table.bind('<Return>',self.open_selected);self.table.bind('<Button-3>',self.show_context_menu)
    self.context_menu=tk.Menu(self.root,tearoff=0,bg='#102a44',fg='#e7f2ff',activebackground='#17536a')
    self.context_menu.add_command(label='분석 열기',command=self.open_selected)
    self.context_menu.add_command(label='맵 데이터 모바일 전송',command=lambda:_resend(self))
    self.context_menu.add_separator();self.context_menu.add_command(label='이 경기 삭제',command=self.delete_selected)
    self.empty=ttk.Label(area,text='',style='Muted.TLabel',background=SURFACE);self.empty.pack(anchor='w',pady=10)
    self.populate()

def _populate(self):
    _old_populate(self)
    ids=self.table.get_children()
    for i,sid in enumerate(ids):self.table.item(sid,tags=('even' if i%2==0 else 'odd',))
    if hasattr(self,'count_label') and self.count_label.winfo_exists():
        self.count_label.configure(text=f'총 {len(ids)}개의 경기  ·  더블클릭하여 분석 열기  ·  맵 데이터는 선택한 경기만 전송')

Desktop.__init__=_init
Desktop.show_list=_show_list
Desktop.populate=_populate

# PC 0.37: full video playback opens the cut workspace.
def _play_clips(self,start=None,end=None):
    record=self.catalog.get(self.selected)
    if not record:return
    path=video_path(record,BASE/self.raw['recording']['outputDirectory'])
    if not path:messagebox.showinfo('VOID EYE','원본 영상 파일을 찾을 수 없습니다.');return
    if record.get('recordingStatus')!='complete':messagebox.showinfo('VOID EYE','녹화가 끝난 뒤 클립을 선택하세요.');return
    from .clip_player import ClipPlayer
    ffmpeg=Path(self.raw['recording']['ffmpegPath'])
    if not ffmpeg.is_absolute():ffmpeg=BASE/ffmpeg
    if self.player and self.player.winfo_exists():self.player.close()
    try:self.player=ClipPlayer(self.root,path,BASE,ffmpeg,record,self.account,start or 0,end)
    except Exception as e:messagebox.showerror('클립 작업실',str(e))
Desktop.play=_play_clips

# The Voice Host is installed alongside VOID EYE and starts before the agent.
def _voice_state():
    import os,json
    from pathlib import Path
    return Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'VLab Voice' / 'host.json'

_prior_voice_init=Desktop.__init__
def _voice_init(self,root,launch_agent=True):
    import subprocess
    voice_exe=BASE/'VLabVoiceHost'/'VLabVoiceHost.exe'
    state=_voice_state()
    state.parent.mkdir(parents=True,exist_ok=True)
    with (state.parent/'voice-bridge.log').open('a',encoding='utf-8') as diagnostic:
        diagnostic.write(f'GUI startup: base={BASE} host_exists={voice_exe.is_file()}\n')
    if voice_exe.is_file():
        import os
        model=BASE/'models'/'faster-whisper-small'
        cmd=[str(voice_exe),'--state-file',str(state),'--no-browser','--model',str(model)]
        # The recorder retains control if Voice is unavailable.
        try:
            from urllib.request import urlopen
            try:urlopen('http://127.0.0.1:8790/',timeout=.4).close()
            except Exception:
                log_dir=state.parent;log_dir.mkdir(parents=True,exist_ok=True)
                self._voice_log=(log_dir/'voice-host.log').open('ab')
                self._voice_process=subprocess.Popen(cmd,stdout=self._voice_log,stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError as exc:
            with (state.parent/'voice-bridge.log').open('a',encoding='utf-8') as diagnostic:
                diagnostic.write(f'Host launch failed: {exc!r}\n')
    _prior_voice_init(self,root,launch_agent)
    # Separate browser surface for participant consent and per-speaker tracks.
    bar=ttk.Frame(self.shell);bar.pack(fill='x',before=self.content)
    ttk.Button(bar,text='🎙  VLab Voice 작업실',command=self.open_voice_workspace).pack(side='right',padx=14,pady=5)

def _voice_open(self):
    import json,webbrowser
    from urllib.parse import urlencode
    try:
        data=json.loads(_voice_state().read_text(encoding='utf-8'))
        if data.get('url')!='http://127.0.0.1:8790':raise ValueError('Voice Host 주소 오류')
        webbrowser.open(data['url']+'/#'+urlencode({'code':data['code'],'admin':data['admin']}))
    except (OSError,ValueError,KeyError):
        messagebox.showinfo('VLab Voice','Voice Host가 준비 중입니다. 잠시 후 다시 눌러 주세요.',parent=self.root)
Desktop.__init__=_voice_init
Desktop.open_voice_workspace=_voice_open
