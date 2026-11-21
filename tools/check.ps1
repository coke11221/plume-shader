param(
    [string]$Checker = "",
    [switch]$Package
)
$ErrorActionPreference = "Stop"
$shaderProject = Split-Path -Parent $PSScriptRoot
if (-not $Checker) {
    $shaderLocalChecker = Join-Path $shaderProject ".tools\target\release\horizon-shader.exe"
    if (Test-Path -LiteralPath $shaderLocalChecker) {
        $Checker = $shaderLocalChecker
    } else {
        $shaderCommand = Get-Command horizon-shader -ErrorAction SilentlyContinue
        if (-not $shaderCommand) {
            throw "horizon-shader is required. Build the pinned upstream checker as described in README.md, or pass -Checker PATH."
        }
        $Checker = $shaderCommand.Source
    }
}
$Checker = (Resolve-Path -LiteralPath $Checker).Path
$shaderArguments = @((Join-Path $PSScriptRoot "validate.py"), "--checker", $Checker)
if ($Package) { $shaderArguments += "--package" }
& python @shaderArguments
if ($LASTEXITCODE -ne 0) { throw "Shader validation failed (exit $LASTEXITCODE)." }
