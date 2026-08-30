# Install git pre-push hook for AI log submission (Windows PowerShell).
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1

param(
    [switch]$StartFresh
)

$ErrorActionPreference = 'Stop'

$HookFile = '.git/hooks/pre-push'

# Git on Windows runs hooks via Git Bash, so the hook body must be bash.
$HookBody = @'
#!/usr/bin/env bash
# Pre-push: sweep recent Antigravity / Gemini prompts, then submit AI logs.
bash scripts/_pyrun.sh scripts/log_antigravity.py --auto || true
bash scripts/_pyrun.sh scripts/submit_log.py || true
exit 0
'@

# Windows PowerShell 5 writes a UTF-8 BOM via Set-Content -Encoding UTF8.
# A BOM before #!/usr/bin/env bash can make Git unable to execute the hook.
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) $HookFile),
    $HookBody,
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "[ai-log] Git pre-push hook installed."

if (-not (Test-Path .ai-log)) { New-Item -ItemType Directory -Path .ai-log | Out-Null }
if (-not (Test-Path .ai-log/.gitkeep)) { New-Item -ItemType File -Path .ai-log/.gitkeep | Out-Null }

if ($StartFresh) {
    & scripts\_pyrun.cmd scripts\set_ai_log_cutoff.py
    if ($LASTEXITCODE -ne 0) { throw 'Could not create AI log submission cutoff.' }
}

Write-Host "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."
