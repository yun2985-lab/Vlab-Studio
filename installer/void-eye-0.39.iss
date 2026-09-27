[Setup]
AppId=VoidEyePC
AppName=VOID EYE
AppVersion=0.39
AppPublisher=Vlab Studio
DefaultDirName={localappdata}\Programs\VoidEye
DefaultGroupName=VOID EYE
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\output
OutputBaseFilename=VoidEye-PC-0.39-Full-x64-Setup
Compression=zip
SolidCompression=no
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\VoidEye.exe

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Files]
Source: "..\payload\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\VOID EYE"; Filename: "{app}\VoidEye.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\VOID EYE"; Filename: "{app}\VoidEye.exe"; WorkingDir: "{app}"
