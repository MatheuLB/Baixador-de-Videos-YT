; Instalador do Windows (Inno Setup 6.3+).
; Normalmente é chamado pelo scripts/package.py, que passa estes valores:
;   iscc /DAppVersion=1.0.0 /DSourceDir=...\dist\Baixador /DOutputDir=...\dist\release /DIconFile=...\assets\icon.ico installer.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\Baixador"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist\release"
#endif
#ifndef IconFile
  #define IconFile "..\..\assets\icon.ico"
#endif

#define AppName "Baixador de Vídeos"
#define AppExe "Baixador.exe"

[Setup]
AppId={{6C1E2F7A-4B5D-4E8A-9C3F-2D7B8A1E5F40}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Baixador
DefaultDirName={autopf}\Baixador
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Instala só para o usuário atual, sem pedir senha de administrador.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Baixador-{#AppVersion}-windows-x64-instalador
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Componentes que o app baixou (yt-dlp, FFmpeg, Deno).
Type: filesandordirs; Name: "{localappdata}\Baixador"
