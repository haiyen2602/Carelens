<#
.SYNOPSIS
  Deploy CapyMedi lên Railway. Thay cho `make deploy-*` trên máy Windows không có make.

.EXAMPLE
  ./scripts/deploy.ps1                       # cả api + web, production
  ./scripts/deploy.ps1 -Target api           # chỉ backend
  ./scripts/deploy.ps1 -Environment preview  # deploy vào environment `preview`
#>
[CmdletBinding()]
param(
    [ValidateSet('both', 'api', 'web')]
    [string]$Target = 'both',

    [string]$Environment = 'production'
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$isProd = $Environment -eq 'production'

if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    throw "Railway CLI chưa cài. Chạy: npm i -g @railway/cli"
}

function Invoke-Deploy {
    param([string]$Name, [string]$Directory, [string]$Service, [string]$SmokeUrl)

    Write-Host "`n==> Deploying $Name ($Environment)" -ForegroundColor Cyan
    Push-Location $Directory
    try {
        # -c: chỉ stream build log rồi thoát. Thiếu cờ này CLI bám vào log
        # runtime và script treo vô hạn vì server không bao giờ tự kết thúc.
        & railway up -c --service $Service --environment $Environment
        if ($LASTEXITCODE -ne 0) { throw "$Name deploy thất bại (exit $LASTEXITCODE)" }
    }
    finally {
        Pop-Location
    }

    # Environment khác production có domain riêng, script không đoán được URL.
    if ($isProd -and $SmokeUrl) {
        Write-Host "==> Smoke test $SmokeUrl" -ForegroundColor Cyan
        $response = Invoke-WebRequest -Uri $SmokeUrl -TimeoutSec 30 -UseBasicParsing
        Write-Host "    HTTP $($response.StatusCode)" -ForegroundColor Green
    }
}

if ($Target -in @('both', 'api')) {
    Invoke-Deploy -Name 'api (FastAPI)' -Directory $repoRoot -Service 'VMEC-04/BE' `
        -SmokeUrl 'https://vmec-04be-production.up.railway.app/api/v1/status'
}

if ($Target -in @('both', 'web')) {
    Invoke-Deploy -Name 'web (Next.js)' -Directory (Join-Path $repoRoot 'frontend') -Service 'VMEC-04/FE' `
        -SmokeUrl 'https://vmec-04fe-production.up.railway.app/'
}

Write-Host "`nXong." -ForegroundColor Green
