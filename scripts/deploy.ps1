<#
.SYNOPSIS
  Deploy CapyMedi lên Vercel. Thay cho `make deploy-*` trên máy Windows không có make.

.EXAMPLE
  ./scripts/deploy.ps1              # cả api + web, production
  ./scripts/deploy.ps1 -Target api  # chỉ backend
  ./scripts/deploy.ps1 -Preview     # ra preview URL thay vì production
#>
[CmdletBinding()]
param(
    [ValidateSet('both', 'api', 'web')]
    [string]$Target = 'both',

    [switch]$Preview
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$prodFlag = if ($Preview) { @() } else { @('--prod') }
$label = if ($Preview) { 'preview' } else { 'production' }

if (-not (Get-Command vercel -ErrorAction SilentlyContinue)) {
    throw "Vercel CLI chưa cài. Chạy: npm i -g vercel"
}

function Invoke-Deploy {
    param([string]$Name, [string]$Directory, [string]$SmokeUrl)

    Write-Host "`n==> Deploying $Name ($label)" -ForegroundColor Cyan
    Push-Location $Directory
    try {
        & vercel deploy @prodFlag
        if ($LASTEXITCODE -ne 0) { throw "$Name deploy thất bại (exit $LASTEXITCODE)" }
    }
    finally {
        Pop-Location
    }

    # Preview deploy ra URL ngẫu nhiên nên chỉ smoke test được domain production.
    if (-not $Preview -and $SmokeUrl) {
        Write-Host "==> Smoke test $SmokeUrl" -ForegroundColor Cyan
        $response = Invoke-WebRequest -Uri $SmokeUrl -TimeoutSec 30 -UseBasicParsing
        Write-Host "    HTTP $($response.StatusCode)" -ForegroundColor Green
    }
}

if ($Target -in @('both', 'api')) {
    Invoke-Deploy -Name 'api (FastAPI)' -Directory $repoRoot `
        -SmokeUrl 'https://capymedi.vercel.app/api/v1/status'
}

if ($Target -in @('both', 'web')) {
    Invoke-Deploy -Name 'web (Next.js)' -Directory (Join-Path $repoRoot 'frontend') `
        -SmokeUrl 'https://capymedi-web.vercel.app/'
}

Write-Host "`nXong." -ForegroundColor Green
