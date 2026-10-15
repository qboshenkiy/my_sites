$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Install Docker Desktop first.'
}
function Test-DockerReady {
    try {
        $version = docker info --format '{{.ServerVersion}}' 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}
if (-not (Test-DockerReady)) {
    Start-Process -FilePath (Get-Command docker).Source -ArgumentList @('desktop', 'start', '--detach') -WindowStyle Hidden
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        if (Test-DockerReady) { $ready = $true; break }
    }
    if (-not $ready) { throw 'Docker Desktop is still starting. Retry this script shortly.' }
}
docker compose up -d --build --wait --wait-timeout 120 web
if ($LASTEXITCODE -ne 0) { throw 'Could not start the site. Inspect docker compose logs.' }
$binding = docker compose port web 80
$port = ($binding -split ':')[-1]
Write-Output "Site is ready: http://localhost:$port/"
