[Setup]
AppId=VoidEyePC
AppName=VOID EYE + VLab Voice
AppVersion=0.40.0
AppPublisher=VLab Studio
DefaultDirName={localappdata}\Programs\VoidEye
DefaultGroupName=VOID EYE
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\output
OutputBaseFilename=VoidEye-VLabVoice-0.40-Full-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\VoidEye.exe

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Files]
Source: "..\payload\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\voice-dist\VLabVoiceHost\*"; DestDir: "{app}\VLabVoiceHost"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\models\faster-whisper-small\*"; DestDir: "{app}\models\faster-whisper-small"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\NOTICE-THIRD-PARTY.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\VOID EYE + VLab Voice"; Filename: "{app}\VoidEye.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\VOID EYE + VLab Voice"; Filename: "{app}\VoidEye.exe"; WorkingDir: "{app}"
