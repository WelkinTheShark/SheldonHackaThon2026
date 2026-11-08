<#
Start CaveDawg on port 8000 and expose it through a Cloudflare quick tunnel so Wren can reach it.

  .\serve.ps1          real Claude calls, needs ANTHROPIC_API_KEY in .env
  .\serve.ps1 -Stub    fake upstream on port 9100, no key and no spend (never for Wren evidence)

Prints the public https URL. Ctrl+C stops everything. The URL changes on every start.
#>
param([switch]$Stub)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path .env) {
  Get-Content .env | Where-Object { $_ -match '^\s*[^#][^=]*=' } | ForEach-Object {
    $name, $value = $_ -split '=', 2
    if ($value.Trim()) { Set-Item -Path "env:$($name.Trim())" -Value $value.Trim() }
  }
}
if (-not $env:CAVEDAWG_GATEWAY_TOKEN) { throw "Set CAVEDAWG_GATEWAY_TOKEN in .env" }
if (-not $Stub -and -not $env:ANTHROPIC_API_KEY) { throw "Set ANTHROPIC_API_KEY in .env, or pass -Stub" }

$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $cloudflared)) { $cloudflared = (Get-Command cloudflared).Source }

$procs = @()
try {
  if ($Stub) {
    $env:ANTHROPIC_UPSTREAM = "http://127.0.0.1:9100"
    $procs += Start-Process python -ArgumentList "-m uvicorn tests.fake_upstream:app --port 9100" -NoNewWindow -PassThru
  } else {
    Remove-Item env:ANTHROPIC_UPSTREAM -ErrorAction SilentlyContinue
  }
  # --reload picks up Python edits without a restart, so the tunnel URL stays the same.
  $procs += Start-Process python -ArgumentList "-m uvicorn app.main:app --port 8000 --reload --reload-dir app" -NoNewWindow -PassThru

  $log = Join-Path $env:TEMP "cavedawg-tunnel.log"
  Remove-Item $log -ErrorAction SilentlyContinue
  $procs += Start-Process $cloudflared -ArgumentList "tunnel --url http://127.0.0.1:8000 --no-autoupdate" `
    -NoNewWindow -PassThru -RedirectStandardError $log

  $url = $null
  for ($i = 0; $i -lt 60 -and -not $url; $i++) {
    Start-Sleep 1
    if (Test-Path $log) {
      $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
      if ($m) { $url = $m.Matches[0].Value }
    }
  }
  if (-not $url) { throw "Tunnel did not start. See $log" }

  Write-Host ""
  Write-Host "CaveDawg is public at: $url" -ForegroundColor Green
  Write-Host "Local:                http://127.0.0.1:8000"
  if ($Stub) { Write-Host "Mode: STUB upstream (made-up replies). Not valid Wren evidence." -ForegroundColor Yellow }
  else { Write-Host "Mode: real Claude calls." }
  Write-Host "Ctrl+C to stop."
  Wait-Process -Id $procs[-1].Id
} finally {
  foreach ($p in $procs) { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } }
}
