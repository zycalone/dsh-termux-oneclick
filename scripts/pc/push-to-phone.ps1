<#
.SYNOPSIS
    把 dsh-phone-termux 目录打包成 zip 并通过 adb 推到手机的 /sdcard/Download。

.DESCRIPTION
    adb push 到 /sdcard/Download 不需要手机 root，也不需要「所有文件访问」权限
    （Termux 里用 termux-setup-storage 之后即可读取）。

.EXAMPLE
    pwsh -File .\push-to-phone.ps1
    pwsh -File .\push-to-phone.ps1 -AdbPath "C:\platform-tools\adb.exe"
#>
[CmdletBinding()]
param(
    [string]$SourceDir = (Split-Path -Parent $MyInvocation.MyCommand.Path),
    [string]$AdbPath = "",
    [string]$RemoteDir = "/sdcard/Download"
)

$ErrorActionPreference = 'Stop'

function Find-Adb {
    if ($AdbPath -and (Test-Path $AdbPath)) { return $AdbPath }
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($c in @(
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe",
        "C:\platform-tools\adb.exe",
        "C:\adb\adb.exe"
    )) { if (Test-Path $c) { return $c } }
    return $null
}

$adb = Find-Adb
if (-not $adb) {
    Write-Host "[XX] 没找到 adb。也可以不用 adb：" -ForegroundColor Red
    Write-Host "     1. 手动把 dsh-phone-termux.zip 通过微信/QQ/网盘发到手机"
    Write-Host "     2. 手机文件管理器里放到 Download 目录"
    Write-Host "     3. Termux 里: termux-setup-storage && cd ~/storage/downloads"
    exit 1
}

$zip = Join-Path $env:TEMP 'dsh-phone-termux.zip'
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $SourceDir '*') -DestinationPath $zip -CompressionLevel Optimal
Write-Host "[OK] 已打包: $zip ($([math]::Round((Get-Item $zip).Length/1KB,1)) KB)" -ForegroundColor Green

$devices = & $adb devices
if (-not ($devices -match '\s+device$')) {
    Write-Host "[XX] 没有已授权的设备，开启 USB 调试并允许本机后重试。" -ForegroundColor Red
    exit 1
}

& $adb push $zip "$RemoteDir/dsh-phone-termux.zip"
if ($LASTEXITCODE -ne 0) { Write-Host "[XX] push 失败" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "[OK] 已推到手机 $RemoteDir/dsh-phone-termux.zip" -ForegroundColor Green
Write-Host "接下来在手机的 Termux 里执行：" -ForegroundColor Cyan
Write-Host @"
  termux-setup-storage
  cd ~ && mkdir -p dsh-phone-src && cd dsh-phone-src
  unzip -o ~/storage/downloads/dsh-phone-termux.zip
  bash setup.sh
"@ -ForegroundColor DarkGray
