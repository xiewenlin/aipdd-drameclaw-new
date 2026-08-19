$ErrorActionPreference = "Stop"

$desktopRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repoRoot = [IO.Path]::GetFullPath((Split-Path $desktopRoot -Parent))
$localDotnet = Join-Path $repoRoot ".tools\dotnet\dotnet.exe"
$dotnet = if (Test-Path -LiteralPath $localDotnet) { $localDotnet } else { "dotnet" }
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $desktopRoot "release"))
$publishRoot = [IO.Path]::GetFullPath((Join-Path $releaseRoot "native-publish"))

if (-not $publishRoot.StartsWith($desktopRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "发布目录不在 desktop 工作区内"
}

if (Test-Path -LiteralPath $publishRoot) {
    Remove-Item -LiteralPath $publishRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $publishRoot -Force | Out-Null

& $dotnet restore (Join-Path $desktopRoot "Gulong.ShortDrama.Desktop.csproj") -p:NuGetAudit=false
if ($LASTEXITCODE -ne 0) { throw "NuGet 依赖还原失败" }

& $dotnet restore (Join-Path $desktopRoot "tests-native\Gulong.ShortDrama.Tests.csproj") -p:NuGetAudit=false
if ($LASTEXITCODE -ne 0) { throw "测试项目还原失败" }

& $dotnet run --project (Join-Path $desktopRoot "tests-native\Gulong.ShortDrama.Tests.csproj") -c Release --no-restore
if ($LASTEXITCODE -ne 0) { throw "原生客户端测试失败" }

& $dotnet publish (Join-Path $desktopRoot "Gulong.ShortDrama.Desktop.csproj") -c Release -r win-x64 --self-contained true -o $publishRoot
if ($LASTEXITCODE -ne 0) { throw "原生客户端发布失败" }

$publishedExe = Join-Path $publishRoot "Gulong.ShortDrama.exe"
$portableExe = Join-Path $releaseRoot "Gulong-ShortDrama-Native-3.0.0-x64.exe"
Copy-Item -LiteralPath $publishedExe -Destination $portableExe -Force

$localNsis = Join-Path $repoRoot ".tools\nsis\makensis.exe"
$systemNsis = Get-Command "makensis.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source
$makeNsis = if (Test-Path -LiteralPath $localNsis) { $localNsis } else { $systemNsis }
if (-not $makeNsis) {
    throw "未找到 NSIS 编译器；请安装 NSIS 或放到 .tools\nsis，便携版已成功生成"
}

Push-Location $desktopRoot
try {
    & $makeNsis "/INPUTCHARSET" "UTF8" (Join-Path $desktopRoot "installer.nsi")
    if ($LASTEXITCODE -ne 0) { throw "Windows 安装包生成失败" }
}
finally {
    Pop-Location
}

Get-Item -LiteralPath $portableExe, (Join-Path $releaseRoot "Gulong-ShortDrama-Native-Setup-3.0.0-x64.exe") |
    Select-Object Name, Length, LastWriteTime
