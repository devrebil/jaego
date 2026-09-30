; PRO 재고관리 - 트레이 상주형 설치 프로그램
; 관리자 권한 없이 현재 사용자 폴더에 설치되고, 설치 후 트레이 아이콘으로 서버를 관리한다.

#define MyAppName "PRO재고관리"
#define MyAppVersion "1.0.0"
#define MyAppExeName "PRO재고관리.exe"

[Setup]
AppId={{B4E3F1A0-6C8E-4E9A-9B7B-PRO-INVENTORY-01}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename={#MyAppName}_Setup
Compression=lzma
SolidCompression=yes
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 아이콘:"
Name: "autostart"; Description: "Windows 시작 시 자동으로 서버 실행"; GroupDescription: "옵션:"

[Files]
Source: "dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 트레이 아이콘의 "Windows 시작 시 자동 실행" 토글과 같은 레지스트리 키를 사용해
; 설치 시 선택과 이후 트레이 메뉴 토글이 서로 충돌하지 않게 한다.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "설치 후 바로 실행"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#MyAppExeName} /F"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillProApp"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\db\auto_backups"
