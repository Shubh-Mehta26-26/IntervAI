$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location $taskRoot
try {
    $apiPort = if ($env:API_PORT) { $env:API_PORT } else { '8000' }
    $frontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { '3000' }
    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    $dockerPath = if ($dockerCommand) { $dockerCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe' }
    if (-not (Test-Path -LiteralPath $dockerPath)) { throw 'Docker CLI not found. Install/start Docker Desktop and add its bin directory to PATH.' }
    & $dockerPath compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose configuration failed.' }
    Invoke-RestMethod "http://localhost:$apiPort/api/v1/health/live"
    Invoke-RestMethod "http://localhost:$apiPort/api/v1/health/ready"
    Invoke-RestMethod "http://localhost:$frontendPort/api/health"
    $page = Invoke-WebRequest "http://localhost:$frontendPort"
    if ($page.StatusCode -ne 200) { throw 'Frontend failed.' }
    Write-Host 'Frontend, API and database readiness checks passed.'
} finally { Pop-Location }
