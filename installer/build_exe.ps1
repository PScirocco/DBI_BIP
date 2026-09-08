<#
    BI-sim を EXE 化する（Windows / PowerShell）

    使い方（リポジトリ直下から、社内ネットワーク接続時）:
        .\installer\build_exe.ps1

    - リポジトリ直下の .venv を使う（無ければ作成を促す）
    - pyinstaller が無ければ pip で入れる（社内ミラー経由）
    - dist\BI-sim\BI-sim.exe を生成（onedir）
    - 最後に dist\BI-sim を zip 化（失敗してもフォルダは完成しているので致命的ではない）
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
$size = "{0:N0} MB" -f ((Get-ChildItem -Recurse $dist | Measure-Object Length -Sum).Sum / 1MB)
Write-Host ""
Write-Host "EXE 完成: $dist  ($size)" -ForegroundColor Green
Write-Host "起動確認:   & '$dist\BI-sim.exe'"

# ---- 配布用 zip（ここから先は失敗しても dist\BI-sim\ は完成済み）----
$ErrorActionPreference = "Continue"
$zip = Join-Path $repo ("dist\BI-sim_{0}.zip" -f (Get-Date -Format "yyMMdd"))
if (Test-Path $zip) { Remove-Item -Force $zip }
$zipped = $false

# 1) tar（Windows 10 1803+ 同梱。多数ファイル・長パスに強い）
$tar = Get-Command tar.exe -ErrorAction SilentlyContinue
if ($tar) {
    & tar.exe -a -c -f $zip -C (Join-Path $repo "dist") "BI-sim"
    if ($LASTEXITCODE -eq 0 -and (Test-Path $zip)) { $zipped = $true }
}
# 2) フォールバック: Compress-Archive
if (-not $zipped) {
    try {
        Compress-Archive -Path (Join-Path $dist "*") -DestinationPath $zip -Force -ErrorAction Stop
        $zipped = $true
    } catch {
        Write-Warning "zip 圧縮に失敗しました: $($_.Exception.Message)"
    }
}

if ($zipped) {
    Write-Host "配布用 zip: $zip" -ForegroundColor Green
} else {
    Write-Host "zip は作れませんでした。dist\BI-sim\ を手動で zip 化するか、フォルダごとコピー配布してください。" -ForegroundColor Yellow
    Write-Host "  例: tar -a -c -f dist\BI-sim.zip -C dist BI-sim" -ForegroundColor Yellow
}
