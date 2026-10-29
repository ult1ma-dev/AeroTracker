[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

function Invoke-PoetryCheck {
    param([Parameter(Mandatory = $true)][string[]]$PoetryArguments)

    Write-Host ("poetry " + ($PoetryArguments -join " "))
    & poetry @PoetryArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Quality check failed with exit code $LASTEXITCODE."
    }
}

$checkExitCode = 0
Push-Location -LiteralPath $projectRoot
try {
    Invoke-PoetryCheck -PoetryArguments @("check", "--lock")
    Invoke-PoetryCheck -PoetryArguments @("run", "black", "--check", ".")
    Invoke-PoetryCheck -PoetryArguments @(
        "run", "isort", "--check-only", "."
    )
    Invoke-PoetryCheck -PoetryArguments @("run", "flake8", ".")
    Invoke-PoetryCheck -PoetryArguments @("run", "mypy")
    Invoke-PoetryCheck -PoetryArguments @("run", "pytest")
}
catch {
    Write-Host $_ -ForegroundColor Red
    $checkExitCode = 1
}
finally {
    Pop-Location
}

exit $checkExitCode
