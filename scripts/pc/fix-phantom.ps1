<#
.SYNOPSIS
    关闭 Android 12+ 的「幽灵进程杀手」，并把 Termux 加入电池白名单。
    这一条不做，后台的 node / python 网关会被系统随机杀掉。

.DESCRIPTION
    在电脑上运行（手机需开启「开发者选项 → USB 调试」并已授权本机）。
    adb 不在 PATH 时，脚本会去常见的 SDK 目录找；也可以手动传 -AdbPath。

.EXAMPLE
    pwsh -File .\fix-phantom.ps1
    pwsh -File .\fix-phantom.ps1 -AdbPath "C:\platform-tools\adb.exe"
#>
[CmdletBinding()]
param(
    [string]$AdbPath = ""
)

$ErrorActionPreference = 'Stop'

function Find-Adb {
    if ($AdbPath -and (Test-Path $AdbPath)) { return $AdbPath }
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe",
        "$env:USERPROFILE\AppData\Local\Android\Sdk\platform-tools\adb.exe",
        "C:\platform-tools\adb.exe",
        "C:\adb\adb.exe",
        "$env:ProgramFiles\platform-tools\adb.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

$adb = Find-Adb
if (-not $adb) {
    Write-Host "[XX] 没找到 adb。" -ForegroundColor Red
    Write-Host "     方案一：下载 platform-tools 解压后重跑："
    Write-Host "       https://developer.android.com/tools/releases/platform-tools"
    Write-Host "       pwsh -File .\fix-phantom.ps1 -AdbPath `"<解压目录>\platform-tools\adb.exe`""
    Write-Host "     方案二：跳过电脑，在手机里用 Shizuku 的 rish 执行："
    Write-Host "       rish -c 'settings put global settings_enable_monitor_phantom_procs false'"
    Write-Host "       rish -c 'device_config put activity_manager max_phantom_processes 2147483647'"
    Write-Host "       rish -c 'cmd deviceidle whitelist +com.termux'"
    exit 1
}

Write-Host "[..] adb: $adb" -ForegroundColor Cyan
$devices = & $adb devices
$devices | ForEach-Object { Write-Host "     $_" }
if (-not ($devices -match '\s+device$')) {
    Write-Host "[XX] 没有已授权的设备。检查：数据线是否支持传输、USB 调试是否开启、手机上是否点了「允许」。" -ForegroundColor Red
    exit 1
}

function Invoke-Adb {
    param([string]$Desc, [string[]]$Args)
    Write-Host "[..] $Desc" -ForegroundColor Cyan
    try {
        $out = & $adb @Args 2>&1
        if ($out) { $out | ForEach-Object { Write-Host "     $_" } }
    } catch {
        Write-Host "     [!!] 失败（老系统不支持该命令可忽略）：$($_.Exception.Message)" -ForegroundColor Yellow
    }
}

Invoke-Adb "1) 关闭幽灵进程监控"      @('shell', 'settings', 'put', 'global', 'settings_enable_monitor_phantom_procs', 'false')
Invoke-Adb "2) 锁定 device_config"     @('shell', 'device_config', 'set_sync_disabled_for_tests', 'persistent')
Invoke-Adb "3) 提高 phantom 进程上限"  @('shell', 'device_config', 'put', 'activity_manager', 'max_phantom_processes', '2147483647')
Invoke-Adb "4) Termux 加入电池白名单"  @('shell', 'cmd', 'deviceidle', 'whitelist', '+com.termux')
if (Get-Command -Name Get-Command -ErrorAction SilentlyContinue) {
    Invoke-Adb "5) (可选) Termux 加入待机例外" @('shell', 'dumpsys', 'deviceidle', 'whitelist')
}

Write-Host ""
Write-Host "[..] 回读验证：" -ForegroundColor Cyan
foreach ($pair in @(
    @('settings get global settings_enable_monitor_phantom_procs'),
    @('device_config get activity_manager max_phantom_processes')
)) {
    try {
        $v = & $adb shell $pair[0] 2>&1
        Write-Host "     $($pair[0]) -> $v"
    } catch {
        Write-Host "     $($pair[0]) -> 读取失败（命令可能不被该系统支持）" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "[OK] 完成。重启手机后设置依然有效；以后系统升级可能需要重跑一次。" -ForegroundColor Green
Write-Host "     注意：装完 Termux 之后如果改了包名（例如用 Fork 版），白名单要相应改。" -ForegroundColor DarkGray
