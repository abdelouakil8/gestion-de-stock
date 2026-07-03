; Inno Setup script — Gestion de Stock & Point de Vente
; Build after PyInstaller:  ISCC.exe installer\GestionStockPOS.iss
; Produces: installer\Output\GestionStockPOS-Setup-1.0.0.exe

#define MyAppName "Gestion Stock POS"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Wakilo"
#define MyAppExeName "GestionStockPOS.exe"

[Setup]
AppId={{9D2B1C64-5A17-4A63-9B7C-3E1F0F5C2A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
; App data (SQLite DB, logs, .env) lives in {localappdata}\GestionStockPOS,
; never in Program Files — see backend/app/core/config.py (frozen mode).
OutputDir=Output
OutputBaseFilename=GestionStockPOS-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Old low-spec hardware: 64-bit Windows 10+
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
Source: "..\dist\GestionStockPOS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Icônes supplémentaires :"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Program files only — user data in {localappdata} is deliberately preserved.
Type: filesandordirs; Name: "{app}"
