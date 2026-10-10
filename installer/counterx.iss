; Inno Setup script for counterX POS
; Build on Windows with: iscc installer\counterx.iss
; (after building the app folder with PyInstaller)

#define MyAppName "counterX POS"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "counterX"
#define MyAppExeName "counterX POS.exe"

[Setup]
AppId={{C0UNTERX-P0S-1000-000000000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://counterx.pk
DefaultDirName={autopf}\counterX POS
DefaultGroupName=counterX POS
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=counterX-POS-Setup-1.0.0
SetupIconFile=..\assets\counterx.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
; Per-user install: database lives in %APPDATA%\counterX and is never touched
; by reinstalls or uninstalls.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\build\counterX POS\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Never delete the customer's database or backups on uninstall.
; (No entries here on purpose.)
