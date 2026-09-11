param(
    [string]$ComfyRoot = 'D:\VedioGen-local\ComfyUI',
    [ValidateRange(1024, 65535)][int]$Port = 8188
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($ComfyRoot)
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath (Join-Path $root 'main.py'))) { throw 'ComfyUI installation is incomplete.' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw 'Port is occupied; choose another port and update the admin configuration.' }
$logs = Join-Path $root 'vediogen-logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$process = Start-Process -FilePath $python -WorkingDirectory $root -WindowStyle Hidden -PassThru `
    -ArgumentList @('main.py', '--listen', '127.0.0.1', '--port', "$Port", '--disable-api-nodes', '--disable-all-custom-nodes', '--disable-metadata', '--lowvram', '--reserve-vram', '2', '--disable-smart-memory', '--cache-none', '--disable-pinned-memory') `
    -RedirectStandardOutput (Join-Path $logs 'stdout.log') -RedirectStandardError (Join-Path $logs 'stderr.log')
Write-Output ("ComfyUI starting: PID={0}, URL=http://127.0.0.1:{1}, logs={2}" -f $process.Id, $Port, $logs)
