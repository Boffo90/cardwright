; Cardwright installer (Inno Setup)
;
; Per-user install (no admin needed): the app writes settings, models and
; output next to its exe, so it must NOT live in Program Files.
; Build:  ISCC installer.iss   (after building Cardwright.exe)

#define AppName "Cardwright"
#define AppVersion "2.15.0"
#define AppExe "Cardwright.exe"

[Setup]
; New AppId (the app was renamed from ProxyForge): a fresh install lands in
; its own {localappdata}\Cardwright folder, separate from any old ProxyForge.
AppId={{FD9711B0-1EBF-49B4-84C6-D7814144F42E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Boffo90
AppPublisherURL=https://github.com/Boffo90/cardwright
DefaultDirName={localappdata}\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
; underscore matters: release assets are listed alphabetically by the GitHub
; API, and older clients pick the FIRST .exe â€” "_" sorts after ".exe" so the
; bare app exe always comes first
OutputBaseFilename={#AppName}_Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; downloaded engine/models and user config live next to the exe
Type: filesandordirs; Name: "{app}\models"
Type: filesandordirs; Name: "{app}\_temp"
Type: files; Name: "{app}\realesrgan-ncnn-vulkan.exe"
Type: files; Name: "{app}\vcomp140.dll"
Type: files; Name: "{app}\settings.json"
; keep {app}\output â€” never delete the user's work
