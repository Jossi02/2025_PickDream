param(
    [string]$JavaHome = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

$candidateJavaHomes = @()

if ($JavaHome) {
    $candidateJavaHomes += $JavaHome
}

if ($env:JAVA_HOME) {
    $candidateJavaHomes += $env:JAVA_HOME
}

$candidateJavaHomes += @(
    "C:\Program Files\Android\Android Studio\jbr",
    "C:\Program Files\Android\Android Studio\jre"
)

$resolvedJavaHome = $candidateJavaHomes |
    Where-Object { $_ -and (Test-Path (Join-Path $_ "bin\java.exe")) } |
    Select-Object -First 1

if (-not $resolvedJavaHome) {
    throw "JDK를 찾을 수 없습니다. Android Studio를 설치했는지 확인하거나 -JavaHome 인자로 JDK 경로를 전달하세요."
}

$env:JAVA_HOME = $resolvedJavaHome
$env:Path = "$resolvedJavaHome\bin;$env:Path"

Write-Host "Using JAVA_HOME: $env:JAVA_HOME"
& .\gradlew.bat assembleDebug
