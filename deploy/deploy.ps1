# Slipstream deployment helper (Windows PowerShell 5.1+).
#
#   .\deploy.ps1                     load the image (if needed) and start
#   .\deploy.ps1 -ImageFile FILE     load a specific exported tarball, then start
#   .\deploy.ps1 -Action status      container state + API health
#   .\deploy.ps1 -Action logs        follow container logs
#   .\deploy.ps1 -Action restart     restart the container
#   .\deploy.ps1 -Action down        stop and remove (data volume kept)
#
# Works in the repository (deploy\deploy.ps1) and in the exported deployment
# package (script next to docker-compose.yml).
[CmdletBinding()]
param(
    [ValidateSet('up', 'down', 'logs', 'status', 'restart')]
    [string]$Action = 'up',

    [string]$ImageFile = ''
)

$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path -LiteralPath (Join-Path $here 'docker-compose.yml')) {
    $pkgDir = $here
}
elseif (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $here) 'docker-compose.yml')) {
    $pkgDir = Split-Path -Parent $here
}
else {
    throw "docker-compose.yml not found next to $here or its parent"
}
Set-Location -LiteralPath $pkgDir
$composeFile = Join-Path $pkgDir 'docker-compose.yml'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'docker is not installed or not on PATH'
}

# Docker writes progress/warnings to stderr (including the harmless Compose
# "version is obsolete" notice). With $ErrorActionPreference = 'Stop' that
# would be treated as a terminating error, so every native call goes through
# this wrapper and errors are handled via $LASTEXITCODE explicitly.
function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [switch]$SuppressErrors,
        [switch]$Quiet
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($Quiet) {
            & $FilePath @Arguments *> $null
        }
        elseif ($SuppressErrors) {
            & $FilePath @Arguments 2>$null
        }
        else {
            & $FilePath @Arguments
        }
    }
    finally {
        $ErrorActionPreference = $previous
    }
}

# Prefer the Compose v2 plugin, fall back to the standalone v1 binary.
$null = cmd.exe /c 'docker compose version >nul 2>&1'
if ($LASTEXITCODE -eq 0) {
    $script:composeExe = 'docker'
    $script:composePrefix = @('compose')
}
elseif (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    $script:composeExe = 'docker-compose'
    $script:composePrefix = @()
}
else {
    throw "Docker Compose not found (need 'docker compose' or 'docker-compose')"
}

$script:composeArgs = $script:composePrefix + @('-f', $composeFile)

function Invoke-Compose {
    param([string[]]$Arguments)
    Invoke-Native -FilePath $script:composeExe -Arguments ($script:composeArgs + $Arguments)
}

function Get-ComposeImage {
    $img = ''
    $out = Invoke-Native -FilePath $script:composeExe `
        -Arguments ($script:composeArgs + @('config', '--images')) -SuppressErrors
    if ($LASTEXITCODE -eq 0 -and $out) {
        $img = ([string]($out | Select-Object -First 1)).Trim()
    }
    if (-not $img) {
        # Compose v1 has no `config --images`; `config` still resolves .env.
        $out = Invoke-Native -FilePath $script:composeExe `
            -Arguments ($script:composeArgs + @('config')) -SuppressErrors
        if ($LASTEXITCODE -eq 0 -and $out) {
            $line = $out | Where-Object { $_ -match '^\s*image:\s*' } | Select-Object -First 1
            if ($line) { $img = ($line -replace '^\s*image:\s*', '').Trim().Trim('"') }
        }
    }
    if (-not $img) {
        $line = Get-Content -LiteralPath $script:composeFile |
            Where-Object { $_ -match '^\s*image:\s*' } |
            Select-Object -First 1
        if ($line) {
            $img = ($line -replace '^\s*image:\s*', '').Trim()
            if ($img -match '^\$\{SLIPSTREAM_IMAGE:-(.+)\}$') {
                $img = $Matches[1]
            }
        }
    }
    if (-not $img) { $img = 'slipstream:0.2.0' }
    return $img
}

function Test-Image {
    param([string]$Image)
    Invoke-Native -FilePath 'docker' -Arguments @('image', 'inspect', $Image) -Quiet
    return ($LASTEXITCODE -eq 0)
}

function Get-ImageTarball {
    $candidate = Get-ChildItem -LiteralPath $pkgDir -File |
        Where-Object { $_.Name -like 'slipstream-*.tar.gz' -or $_.Name -like 'slipstream-*.tar' } |
        Sort-Object Name |
        Select-Object -Last 1
    if ($candidate) { return $candidate.FullName }
    return ''
}

function Install-Image {
    param([string]$Image, [string]$File)

    if ($File) {
        if (-not (Test-Path -LiteralPath $File)) {
            throw "image file not found: $File"
        }
        Write-Host "loading image from $File ..."
        Invoke-Native -FilePath 'docker' -Arguments @('load', '-i', $File)
        if ($LASTEXITCODE -ne 0) { throw 'docker load failed' }
        return
    }

    if (Test-Image -Image $Image) {
        Write-Host "image $Image already present"
        return
    }

    $tarball = Get-ImageTarball
    if (-not $tarball) {
        throw "image '$Image' is not loaded and no slipstream-*.tar.gz is next to $composeFile"
    }
    Write-Host "loading image from $tarball ..."
    Invoke-Native -FilePath 'docker' -Arguments @('load', '-i', $tarball)
    if ($LASTEXITCODE -ne 0) { throw 'docker load failed' }
    if (-not (Test-Image -Image $Image)) {
        throw "$tarball did not provide image '$Image'"
    }
}

function Initialize-EnvFile {
    $envFile = Join-Path $pkgDir '.env'
    if (-not (Test-Path -LiteralPath $envFile)) {
        $example = Join-Path $pkgDir '.env.example'
        if (-not (Test-Path -LiteralPath $example)) {
            $example = Join-Path $pkgDir 'deploy\.env.example'
        }
        if (Test-Path -LiteralPath $example) {
            Copy-Item -LiteralPath $example -Destination $envFile
            Write-Host "created $envFile from $example"
        }
        else {
            New-Item -ItemType File -Path $envFile | Out-Null
        }
    }

    if (-not $env:SLIPSTREAM_WORKERS) {
        $text = Get-Content -LiteralPath $envFile -Raw -ErrorAction SilentlyContinue
        if ($text -notmatch '(?m)^\s*SLIPSTREAM_WORKERS\s*=') {
            $cores = [Environment]::ProcessorCount
            $workers = if ($cores -ge 12) { 2 } else { 1 }
            Add-Content -LiteralPath $envFile -Value (
                "`r`n# Added by deploy.ps1: $cores logical processors detected`r`n" +
                "SLIPSTREAM_WORKERS=$workers")
            Write-Host "set SLIPSTREAM_WORKERS=$workers (host logical processors: $cores)"
        }
    }
}

function Wait-Healthy {
    $cid = (Invoke-Compose -Arguments @('ps', '-q', 'slipstream') | Select-Object -First 1)
    if ($cid) { $cid = ([string]$cid).Trim() }
    if (-not $cid) {
        Invoke-Compose -Arguments @('ps')
        throw 'the slipstream container was not created'
    }

    $deadline = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $deadline) {
        $status = Invoke-Native -FilePath 'docker' -Arguments @(
            'inspect', '--format',
            '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}',
            $cid
        ) -SuppressErrors
        $status = ([string]($status | Select-Object -First 1)).Trim()
        if ($status -eq 'healthy') { return }
        if ($status -in @('unhealthy', 'exited', 'dead')) {
            Invoke-Compose -Arguments @('logs', '--tail=80', 'slipstream')
            throw "container is $status"
        }
        Start-Sleep -Seconds 3
    }
    Invoke-Compose -Arguments @('logs', '--tail=80', 'slipstream')
    throw 'container did not become healthy within 180s'
}

function Show-AccessUrl {
    $published = (Invoke-Compose -Arguments @('port', 'slipstream', '8000') | Select-Object -First 1)
    $port = '8000'
    if ($published -and ([string]$published) -match ':(\d+)\s*$') {
        $port = $Matches[1]
    }
    Write-Host ''
    Write-Host "Slipstream is ready:  http://localhost:$port"
    Write-Host "API health:           http://localhost:$port/api/health"
    Write-Host "LAN access:           http://<this-host-ip>:$port"
}

switch ($Action) {
    'up' {
        Initialize-EnvFile
        $img = Get-ComposeImage
        Install-Image -Image $img -File $ImageFile
        Write-Host "starting $img ..."
        Invoke-Compose -Arguments @('up', '-d')
        if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }
        Wait-Healthy
        Show-AccessUrl
    }
    'down' {
        Invoke-Compose -Arguments @('down')
        if ($LASTEXITCODE -ne 0) { throw 'docker compose down failed' }
        Write-Host "container removed; run data is kept in the 'slipstream-data' volume (unless a bind mount is configured)."
    }
    'logs' {
        Invoke-Compose -Arguments @('logs', '-f', '--tail=200', 'slipstream')
    }
    'status' {
        Invoke-Compose -Arguments @('ps')
        $cid = (Invoke-Compose -Arguments @('ps', '-q', 'slipstream') | Select-Object -First 1)
        if ($cid) {
            $cid = ([string]$cid).Trim()
            Write-Host ''
            Invoke-Native -FilePath 'docker' -Arguments @(
                'inspect', '--format',
                'health: {{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}  status: {{.State.Status}}',
                $cid
            )
            $published = (Invoke-Compose -Arguments @('port', 'slipstream', '8000') | Select-Object -First 1)
            $port = '8000'
            if ($published -and ([string]$published) -match ':(\d+)\s*$') { $port = $Matches[1] }
            Write-Host "health URL: http://localhost:$port/api/health"
            try {
                $health = Invoke-RestMethod -Uri "http://localhost:$port/api/health" -TimeoutSec 5
                $health | ConvertTo-Json -Compress
            }
            catch {
                Write-Warning "health request failed: $($_.Exception.Message)"
            }
        }
    }
    'restart' {
        Invoke-Compose -Arguments @('restart')
        if ($LASTEXITCODE -ne 0) { throw 'docker compose restart failed' }
        Wait-Healthy
        Show-AccessUrl
    }
}
