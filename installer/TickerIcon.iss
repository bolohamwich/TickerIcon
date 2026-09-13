; Build dist\TickerIcon first with PyInstaller on Windows.
; Compile this file with Inno Setup 6.

#define MyAppName "TickerIcon"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "TickerIcon"
#define MyAppExeName "TickerIcon.exe"

[Setup]
AppId={{B9E7C7C4-3D36-4F7B-BD35-7D7D7E8C4F43}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=TickerIcon-Setup
SetupIconFile=..\assets\tickericon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "startup"; Description: "Start TickerIcon when I sign in to Windows"; GroupDescription: "Startup options:"

[Files]
Source: "..\dist\TickerIcon\*"; DestDir: "{app}"; Excludes: "*.cfg"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\TickerIcon\config.cfg"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: startup; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
