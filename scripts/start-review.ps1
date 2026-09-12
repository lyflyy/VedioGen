param([int]$WebPort = 3001, [int]$ApiPort = 8001)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$data = Join-Path $root '.data/internal-mvp'
$env:VEDIOGEN_DATABASE_URL = 'sqlite:///./.data/internal-mvp/vediogen.db'
$env:VEDIOGEN_DATA_DIR = './.data/internal-mvp'
$env:VEDIOGEN_API_ORIGIN = "http://127.0.0.1:$ApiPort"
if (-not (Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue)) {
    $api = Start-Process -FilePath (Join-Path $root 'services/api/.venv/Scripts/python.exe') -WorkingDirectory $root -WindowStyle Hidden -PassThru `
        -ArgumentList @('-m', 'uvicorn', 'vediogen_api.main:app', '--host', '127.0.0.1', '--port', "$ApiPort") `
        -RedirectStandardOutput (Join-Path $data 'review-api.stdout.log') -RedirectStandardError (Join-Path $data 'review-api.stderr.log')
    Write-Output "API PID=$($api.Id) http://127.0.0.1:$ApiPort"
}
if (-not (Get-NetTCPConnection -LocalPort $WebPort -State Listen -ErrorAction SilentlyContinue)) {
    $web = Start-Process -FilePath (Get-Command node).Source -WorkingDirectory (Join-Path $root 'apps/web') -WindowStyle Hidden -PassThru `
        -ArgumentList @('../../node_modules/next/dist/bin/next', 'dev', '--hostname', '127.0.0.1', '--port', "$WebPort") `
        -RedirectStandardOutput (Join-Path $data 'review-web.stdout.log') -RedirectStandardError (Join-Path $data 'review-web.stderr.log')
    Write-Output "Web PID=$($web.Id) http://127.0.0.1:$WebPort"
}
