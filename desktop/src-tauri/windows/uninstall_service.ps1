<#
.SYNOPSIS
    Enterprise Background Agent Windows Service Uninstaller (Phase 15)
.DESCRIPTION
    Safely terminates the agent, deletes scheduled tasks, unregisters startup keys,
    and performs complete workstation cleanup.
#>

$ErrorActionPreference = "SilentlyContinue"

Write-Host "==========================================================" -ForegroundColor Yellow
Write-Host " Enterprise Attendance Agent - Windows Removal Helper" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Yellow

# 1. Terminate Agent process tree
Write-Host "[1/3] Terminating active agent processes..." -ForegroundColor Green
Stop-Process -Name "enterprise-attendance-desktop" -Force -ErrorAction SilentlyContinue

# 2. Delete Scheduled Task
Write-Host "[2/3] Deleting Scheduled Task..." -ForegroundColor Green
Unregister-ScheduledTask -TaskName "EnterpriseAttendanceAgent" -Confirm:$false -ErrorAction SilentlyContinue

# 3. Remove Startup Run Key
Write-Host "[3/3] Removing Startup Registry Key..." -ForegroundColor Green
Remove-ItemProperty -Path "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "EnterpriseAttendanceAgent" -ErrorAction SilentlyContinue
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "EnterpriseAttendanceAgent" -ErrorAction SilentlyContinue

Write-Host "`nUninstallation & Cleanup Completed." -ForegroundColor Yellow

