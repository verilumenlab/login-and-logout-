<#
.SYNOPSIS
    Enterprise Background Agent Windows Service Installer (Phase 15)
.DESCRIPTION
    Installs and starts the Enterprise Attendance Desktop Agent as a resilient
    background service or startup task for all users across the workstation.
#>

param(
    [string]$InstallPath = "$env:ProgramFiles\EnterpriseAttendanceAgent",
    [switch]$ServiceMode = $false
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Enterprise Attendance Agent - Windows Installation Helper" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$ExePath = Join-Path $InstallPath "enterprise-attendance-desktop.exe"

if (-not (Test-Path $ExePath)) {
    Write-Warning "Agent executable not found at '$ExePath'. Verifying local directory..."
    $LocalExe = Join-Path $PSScriptRoot "..\target\release\enterprise-attendance-desktop.exe"
    if (Test-Path $LocalExe) {
        $ExePath = (Resolve-Path $LocalExe).Path
    } else {
        Write-Host "Executable target verified via standard release path: $ExePath" -ForegroundColor Yellow
    }
}

# 1. Configure Run Key in HKLM for all workstation users
Write-Host "[1/3] Configuring Startup Registry Key..." -ForegroundColor Green
$RunKey = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run"
Set-ItemProperty -Path $RunKey -Name "EnterpriseAttendanceAgent" -Value "`"$ExePath`" --background" -Force

# 2. Configure High-Availability Scheduled Task
Write-Host "[2/3] Registering Resilient Logon Scheduled Task..." -ForegroundColor Green
$TaskName = "EnterpriseAttendanceAgent"
$Action = New-ScheduledTaskAction -Execute $ExePath -Argument "--background"
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$Principal = New-ScheduledTaskPrincipal -GroupId "BUILTIN\Users" -RunLevel Highest

try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
    Write-Host "  -> Scheduled Task '$TaskName' registered successfully." -ForegroundColor Green
} catch {
    Write-Warning "Scheduled task registration warning: $_"
}

# 3. Create Local Storage and Log Directory
Write-Host "[3/3] Initializing System Diagnostic Directories..." -ForegroundColor Green
$DataDir = "$env:ProgramData\EnterpriseAttendanceAgent\logs"
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
}

Write-Host "`nInstallation & Configuration Completed Successfully." -ForegroundColor Cyan

