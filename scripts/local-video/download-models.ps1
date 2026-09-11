param(
    [string]$ComfyRoot = 'D:\VedioGen-local\ComfyUI',
    [ValidateSet('diffusion', 'encoder', 'vae', 'all')][string]$Model = 'all',
    [ValidateSet('https://huggingface.co', 'https://hf-mirror.com', 'https://modelscope.cn')][string]$Endpoint = 'https://huggingface.co',
    [ValidateSet('curl', 'aria2')][string]$Downloader = 'curl',
    [string]$Aria2Path = 'D:\VedioGen-local\aria2\aria2-1.37.0-win-64bit-build1\aria2c.exe',
    [ValidateRange(1, 16)][int]$Connections = 4,
    [ValidateRange(30, 14400)][int]$MaxSeconds = 900
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($ComfyRoot)
if (-not (Test-Path -LiteralPath (Join-Path $root 'main.py'))) { throw 'ComfyUI main.py not found.' }
# File sizes and LFS SHA-256 values were read from the repository metadata on 2026-09-07.
$models = @(
    @{ Id='diffusion'; Repo='Comfy-Org/Wan_2.2_ComfyUI_Repackaged'; Folder='diffusion_models'; Name='wan2.2_ti2v_5B_fp16.safetensors'; Size=9999658848L; Hash='456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e' },
    @{ Id='encoder'; Repo='Comfy-Org/Wan_2.1_ComfyUI_repackaged'; Folder='text_encoders'; Name='umt5_xxl_fp8_e4m3fn_scaled.safetensors'; Size=6735906897L; Hash='c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68' },
    @{ Id='vae'; Repo='Comfy-Org/Wan_2.2_ComfyUI_Repackaged'; Folder='vae'; Name='wan2.2_vae.safetensors'; Size=1409400960L; Hash='e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156' }
)
foreach ($entry in $models) {
    if ($Model -ne 'all' -and $Model -ne $entry.Id) { continue }
    $directory = Join-Path $root ('models\' + $entry.Folder)
    $target = [IO.Path]::GetFullPath((Join-Path $directory $entry.Name))
    if (-not $target.StartsWith($root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Model path is outside ComfyUI.' }
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    if (Test-Path -LiteralPath $target) {
        if ((Get-Item -LiteralPath $target).Length -eq $entry.Size -and (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -eq $entry.Hash) {
            Write-Output ($entry.Id + ': already verified')
            continue
        }
        throw ('Existing model failed verification; left untouched: ' + $target)
    }
    $partial = $target + '.part'
    $hasControl = Test-Path -LiteralPath ($partial + '.aria2')
    if ($hasControl -and $Downloader -ne 'aria2') { throw 'This partial file has aria2 piece metadata; resume with -Downloader aria2.' }
    $downloaded = if (Test-Path -LiteralPath $partial) { (Get-Item -LiteralPath $partial).Length } else { 0 }
    $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($root))
    $requiredSpace = if ($hasControl) { $entry.Size + 5GB } else { $entry.Size - $downloaded + 5GB }
    if ($drive.AvailableFreeSpace -lt $requiredSpace) { throw 'Insufficient free disk space.' }
    if ($downloaded -lt $entry.Size -or $hasControl) {
        $url = "$Endpoint/$($entry.Repo)/resolve/main/split_files/$($entry.Folder)/$($entry.Name)"
        if ($Endpoint -eq 'https://modelscope.cn') {
            $url = "$Endpoint/models/$($entry.Repo)/resolve/master/split_files/$($entry.Folder)/$($entry.Name)"
        }
        if ($hasControl) {
            Write-Output ("Downloading {0}, resuming aria2 pieces; logical file length {1} is not completed bytes." -f $entry.Id, $downloaded)
        } else {
            Write-Output ("Downloading {0}, resuming at {1} bytes" -f $entry.Id, $downloaded)
        }
        if ($Downloader -eq 'aria2') {
            if (-not (Test-Path -LiteralPath $Aria2Path)) { throw 'aria2 executable not found.' }
            & $Aria2Path --continue=true --always-resume=true --auto-file-renaming=false --allow-overwrite=false --file-allocation=none `
                "--split=$Connections" "--max-connection-per-server=$Connections" --min-split-size=20M --connect-timeout=15 --timeout=30 --max-tries=8 --retry-wait=5 `
                --summary-interval=30 --console-log-level=warn --enable-color=false --show-console-readout=false --stop=$MaxSeconds `
                "--dir=$directory" "--out=$($entry.Name).part" $url
        } else {
            & curl.exe --silent --show-error --location --fail --connect-timeout 20 --max-time $MaxSeconds --speed-limit 1024 --speed-time 60 --continue-at - --output $partial $url
        }
        if ($LASTEXITCODE -ne 0) { throw ('Download stopped; any partial bytes remain available for resume at: ' + $partial) }
    }
    if ((Get-Item -LiteralPath $partial).Length -ne $entry.Size -or (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $entry.Hash) {
        throw ('Downloaded model failed size or SHA-256 verification; not activated: ' + $partial)
    }
    Move-Item -LiteralPath $partial -Destination $target
    Write-Output ($entry.Id + ': verified and activated')
}
