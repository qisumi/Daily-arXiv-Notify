param(
    [string]$OutputDir = "dist",
    [switch]$ExcludeLocalConfig,
    [switch]$Clean
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

$args = @(
    (Join-Path $scriptDir "build_release.py"),
    "--output-dir", $OutputDir
)

if ($ExcludeLocalConfig) {
    $args += "--exclude-local-config"
}

if ($Clean) {
    $args += "--clean"
}

python @args
exit $LASTEXITCODE
