# Build the Slipstream image and export it as a self-contained deployment package.
#
#   .\deploy\export-image.ps1
#   .\deploy\export-image.ps1 -Version 0.3.0
#   $env:PIP_INDEX_URL='https://pypi.tuna.tsinghua.edu.cn/simple'
#   $env:NPM_REGISTRY='https://registry.npmmirror.com'
#   .\deploy\export-image.ps1
#
# Output (default: <repo>\dist-docker\):
#   slipstream-<version>-<os>-<arch>.tar.gz   docker save artifact
#   docker-compose.yml, deploy.ps1, deploy.sh, .env.example, README.md
#   SHA256SUMS
[CmdletBinding()]
param(
    [string]$Version = $env:SLIPSTREAM_VERSION,
    [string]$Image = $env:SLIPSTREAM_IMAGE,
    [string]$OutDir = $env:SLIPSTREAM_OUT_DIR
)

$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
if (-not $OutDir) { $OutDir = Join-Path $root 'dist-docker' }

if (-not $Version) {
    $pkg = Get-Content -LiteralPath (Join-Path $root 'frontend\package.json') -Raw | ConvertFrom-Json
    $Version = $pkg.version
}
if (-not $Version) { $Version = '0.2.0' }
if (-not $Image) { $Image = "slipstream:$Version" }

$openfoamImage = if ($env:OPENFOAM_IMAGE) { $env:OPENFOAM_IMAGE } else { 'opencfd/openfoam-default:2512' }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'docker is not installed or not on PATH'
}

# Docker writes build progress and warnings to stderr; with
# $ErrorActionPreference = 'Stop' those would abort the script. Route every
# native call through this helper and check $LASTEXITCODE explicitly.
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

$buildArgs = @(
    'build',
    '-t', $Image,
    '--build-arg', "OPENFOAM_IMAGE=$openfoamImage",
    '--build-arg', "SLIPSTREAM_VERSION=$Version"
)
if ($env:PIP_INDEX_URL) { $buildArgs += @('--build-arg', "PIP_INDEX_URL=$($env:PIP_INDEX_URL)") }
if ($env:SLIPSTREAM_PLATFORM) { $buildArgs += @('--platform', $env:SLIPSTREAM_PLATFORM) }
$buildArgs += $root

# The image copies the prebuilt frontend/dist, so build it on the host first.
$frontendDir = Join-Path $root 'frontend'
if ($env:SLIPSTREAM_SKIP_FRONTEND_BUILD -eq '1') {
    if (-not (Test-Path -LiteralPath (Join-Path $frontendDir 'dist\index.html'))) {
        throw 'SLIPSTREAM_SKIP_FRONTEND_BUILD=1 but frontend\dist is missing'
    }
}
else {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw 'npm is required to build the web UI (or set SLIPSTREAM_SKIP_FRONTEND_BUILD=1)'
    }
    Push-Location -LiteralPath $frontendDir
    try {
        if (-not (Test-Path -LiteralPath 'node_modules')) {
            Write-Host 'installing frontend dependencies ...'
            $npmArgs = @('ci', '--no-audit', '--no-fund')
            if ($env:NPM_REGISTRY) { $npmArgs += @('--registry', $env:NPM_REGISTRY) }
            Invoke-Native -FilePath 'npm' -Arguments $npmArgs
            if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
        }
        Write-Host 'building frontend ...'
        Invoke-Native -FilePath 'npm' -Arguments @('run', 'build')
        if ($LASTEXITCODE -ne 0) { throw 'npm run build failed' }
    }
    finally {
        Pop-Location
    }
}

Write-Host '=============================================================='
Write-Host ' Slipstream image export'
Write-Host "   version      : $Version"
Write-Host "   image        : $Image"
Write-Host "   OpenFOAM base: $openfoamImage"
Write-Host "   output       : $OutDir"
Write-Host '=============================================================='
Write-Host 'building (this can take a while on the first run) ...'

Invoke-Native -FilePath 'docker' -Arguments $buildArgs
if ($LASTEXITCODE -ne 0) { throw 'docker build failed' }

$arch = (Invoke-Native -FilePath 'docker' -Arguments @('image', 'inspect', $Image, '--format', '{{.Os}}-{{.Architecture}}') | Select-Object -First 1)
$arch = ([string]$arch).Trim() -replace '/', '-'
if (-not $arch) { throw "could not determine the architecture of $Image" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$file = Join-Path $OutDir "slipstream-$Version-$arch.tar.gz"
$tmp = "$file.tmp"

Write-Host "exporting $Image -> $file ..."
$dockerExe = (Get-Command docker).Source
$gzip = Get-Command gzip.exe -ErrorAction SilentlyContinue

try {
    if ($gzip) {
        # cmd.exe keeps the docker->gzip pipeline binary-safe (PowerShell's `>`
        # would re-encode it as text).
        $pipeline = '"{0}" save "{1}" | "{2}" -6 > "{3}"' -f $dockerExe, $Image, $gzip.Source, $tmp
        $null = cmd.exe /c $pipeline
        if ($LASTEXITCODE -ne 0) { throw 'docker save | gzip failed' }
        Move-Item -Force -LiteralPath $tmp -Destination $file
    }
    else {
        # No gzip on PATH: save the plain tar and compress with .NET.
        $tarFile = Join-Path $OutDir "slipstream-$Version-$arch.tar"
        $tmp = "$tarFile.tmp"
        Invoke-Native -FilePath 'docker' -Arguments @('save', '-o', $tmp, $Image)
        if ($LASTEXITCODE -ne 0) { throw 'docker save failed' }
        $file = "$tarFile.gz"
        $input = [System.IO.File]::OpenRead($tmp)
        $output = [System.IO.File]::Create($file)
        $gzipStream = New-Object System.IO.Compression.GZipStream(
            $output, [System.IO.Compression.CompressionLevel]::Optimal)
        try {
            $input.CopyTo($gzipStream)
        }
        finally {
            $gzipStream.Dispose()
            $output.Dispose()
            $input.Dispose()
        }
        Remove-Item -LiteralPath $tmp
        Write-Host 'note: gzip not found; used .NET compression'
    }
}
catch {
    Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
    throw
}

# Deployment package contents (script run from the package or the repo).
$packageFiles = @(
    @{ Source = Join-Path $root 'docker-compose.yml'; Name = 'docker-compose.yml' },
    @{ Source = Join-Path $root 'deploy\deploy.sh'; Name = 'deploy.sh' },
    @{ Source = Join-Path $root 'deploy\deploy.ps1'; Name = 'deploy.ps1' },
    @{ Source = Join-Path $root 'deploy\.env.example'; Name = '.env.example' },
    @{ Source = Join-Path $root 'deploy\README.md'; Name = 'README.md' }
)
foreach ($item in $packageFiles) {
    Copy-Item -LiteralPath $item.Source -Destination (Join-Path $OutDir $item.Name) -Force
}

$hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
$hashLine = "$hash  $(Split-Path -Leaf $file)"
Set-Content -LiteralPath (Join-Path $OutDir 'SHA256SUMS') -Value $hashLine -Encoding Ascii

$sizeMb = [math]::Round((Get-Item -LiteralPath $file).Length / 1MB, 1)
Write-Host ''
Write-Host "done: $file ($sizeMb MB)"
Write-Host "deployment package: $OutDir"
Get-ChildItem -LiteralPath $OutDir | Select-Object Name, Length
