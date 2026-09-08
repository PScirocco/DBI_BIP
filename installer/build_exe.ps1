<#
    BI-sim を EXE 化する（Windows / PowerShell）

    使い方（リポジトリ直下から、社内ネットワーク接続時）:
        .\installer\build_exe.ps1

    - リポジトリ直下の .venv を使う（無ければ作成を促す）
    - pyinstaller が無ければ pip で入れる（社内ミラー経由）
    - dist\BI-sim\BI-sim.exe を生成（onedir）
    - 最後に dist\BI-sim を zip 化
#>
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$py = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error ".venv が見つかりません。先に  py -3 -m venv .venv ; .\.venv\Scripts\pip install -r bisim\requirements.txt  を実行してください。"
}

# pyinstaller の確認・導入
& $py -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "pyinstaller を導入します..." -ForegroundColor Cyan
    & $py -m pip install pyinstaller
}

# クリーンビルド
if (Test-Path (Join-Path $repo "build\BI-sim")) { Remove-Item -Recurse -Force (Join-Path $repo "build\BI-sim") }
if (Test-Path (Join-Path $repo "dist\BI-sim"))  { Remove-Item -Recurse -Force (Join-Path $repo "dist\BI-sim") }

& $py -m PyInstaller --noconfirm --clean "installer\bisim.spec"
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller が失敗しました。" }

$dist = Join-Path $repo "dist\BI-sim"
$zip  = Join-Path $repo ("dist\BI-sim_{0}.zip" -f (Get-Date -Format "yyMMdd"))
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path (Join-Path $dist "*") -DestinationPath $zip

$size = "{0:N0} MB" -f ((Get-ChildItem -Recurse $dist | Measure-Object Length -Sum).Sum / 1MB)
Write-Host ""
Write-Host "完成: $dist  ($size)" -ForegroundColor Green
Write-Host "配布用 zip: $zip" -ForegroundColor Green
Write-Host "起動確認:   & '$dist\BI-sim.exe'"
