!include "MUI2.nsh"

Name "PLGames Launcher"
OutFile "dist\PLGamesLauncher_Setup.exe"
InstallDir "$PROGRAMFILES\PLGames Launcher"
RequestExecutionLevel admin

!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "Russian"

Section "Install"
    SetOutPath "$INSTDIR"

    File "dist\PLGamesLauncher.exe"

    ; Desktop shortcut
    CreateShortCut "$DESKTOP\PLGames Launcher.lnk" "$INSTDIR\PLGamesLauncher.exe"

    ; Start menu
    CreateDirectory "$SMPROGRAMS\PLGames Launcher"
    CreateShortCut "$SMPROGRAMS\PLGames Launcher\PLGames Launcher.lnk" "$INSTDIR\PLGamesLauncher.exe"
    CreateShortCut "$SMPROGRAMS\PLGames Launcher\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Registry for Add/Remove Programs
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLGamesLauncher" "DisplayName" "PLGames Launcher"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLGamesLauncher" "UninstallString" "$INSTDIR\Uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLGamesLauncher" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLGamesLauncher" "Publisher" "PLGames"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLGamesLauncher" "DisplayVersion" "0.2.0"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\PLGamesLauncher.exe"
    Delete "$INSTDIR\aria2c.exe"
    Delete "$INSTDIR\*.torrent"
    Delete "$INSTDIR\Uninstall.exe"
    Delete "$INSTDIR\plgames_settings.json"
    RMDir "$INSTDIR"

    Delete "$DESKTOP\PLGames Launcher.lnk"
    Delete "$SMPROGRAMS\PLGames Launcher\PLGames Launcher.lnk"
    Delete "$SMPROGRAMS\PLGames Launcher\Uninstall.lnk"
    RMDir "$SMPROGRAMS\PLGames Launcher"

    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PLGamesLauncher"
SectionEnd
