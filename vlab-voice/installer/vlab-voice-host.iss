#define AppName "VLab Voice Host"
#define AppVersion "0.3.0"
[Setup]
AppId={{EE48A962-B015-5ED0-9344-6C17C44F2390}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=VLab
DefaultDirName={localappdata}\Programs\VLab Voice Host
DefaultGroupName=VLab Voice Host
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\installer-output
OutputBaseFilename=VLabVoiceHost-0.3.0-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\VLabVoiceHost.exe
WizardStyle=modern

[Files]
Source: "..\dist\VLabVoiceHost\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README-KO.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\VLab Voice Host"; Filename: "{app}\VLabVoiceHost.exe"
Name: "{autodesktop}\VLab Voice Host"; Filename: "{app}\VLabVoiceHost.exe"

[Run]
Filename: "{app}\VLabVoiceHost.exe"; Description: "VLab Voice Host 실행"; Flags: nowait postinstall skipifsilent
