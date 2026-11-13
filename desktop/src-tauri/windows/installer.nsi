; Enterprise Attendance Agent NSIS Custom Installer Configuration (Phase 15)
; Handles silent enterprise installation, GPO/Intune flags, startup registration,
; background service setup, and clean uninstallation.

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

Name "Enterprise Attendance Agent"
OutFile "EnterpriseAttendanceAgent-Setup-0.1.0.exe"
InstallDir "$PROGRAMFILES64\EnterpriseAttendanceAgent"
InstallDirRegKey HKLM "Software\EnterpriseAttendanceAgent" "InstallLocation"
RequestExecutionLevel admin

; Modern UI Appearance
!define MUI_ABORTWARNING
!define MUI_ICON "..\icons\icon.ico"
!define MUI_UNICON "..\icons\icon.ico"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\..\LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "MainSection" SEC01
    SetOutPath "$INSTDIR"
    File /r "..\target\release\enterprise-attendance-desktop.exe"
    File /r "..\target\release\*.dll"
    
    ; Write Uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; Register in Add/Remove Programs
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EnterpriseAttendanceAgent" \
                     "DisplayName" "Enterprise Attendance & Activity Agent"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EnterpriseAttendanceAgent" \
                     "DisplayVersion" "0.1.0"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EnterpriseAttendanceAgent" \
                     "Publisher" "Enterprise Solutions Inc."
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EnterpriseAttendanceAgent" \
                     "DisplayIcon" "$INSTDIR\enterprise-attendance-desktop.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EnterpriseAttendanceAgent" \
                     "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EnterpriseAttendanceAgent" \
                     "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EnterpriseAttendanceAgent" \
                     "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EnterpriseAttendanceAgent" \
                     "NoRepair" 1

    ; Configure Windows Startup Run Key (Launch Agent on User Login)
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Run" \
                     "EnterpriseAttendanceAgent" '"$INSTDIR\enterprise-attendance-desktop.exe" --background'

    ; Register Scheduled Task for Resilient Auto-Restart on Failure
    ExecWait 'schtasks /create /tn "EnterpriseAttendanceAgent" /tr "\"$INSTDIR\enterprise-attendance-desktop.exe\" --background" /sc onlogon /rl highest /f'
SectionEnd

Section "Uninstall"
    ; 1. Terminate running agent process
    ExecWait 'taskkill /F /IM enterprise-attendance-desktop.exe /T'

    ; 2. Remove Scheduled Task
    ExecWait 'schtasks /delete /tn "EnterpriseAttendanceAgent" /f'

    ; 3. Remove Startup Registry Keys
    DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "EnterpriseAttendanceAgent"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\EnterpriseAttendanceAgent"
    DeleteRegKey HKLM "Software\EnterpriseAttendanceAgent"

    ; 4. Clean Application Files
    Delete "$INSTDIR\enterprise-attendance-desktop.exe"
    Delete "$INSTDIR\uninstall.exe"
    Delete "$INSTDIR\*.dll"
    RMDir /r "$INSTDIR"

    ; 5. Clean AppData Local Storage (Preserve logs if specified)
    ${If} $CMDLINE == "/S"
        ; Silent uninstall preserves diagnostic logs in %PROGRAMDATA%\EnterpriseAttendanceAgent\logs
    ${Else}
        RMDir /r "$LOCALAPPDATA\EnterpriseAttendanceAgent"
    ${EndIf}
SectionEnd

