# setup.ps1 - one-time setup for QuantaKai. Run it through SETUP.bat.
# Safe to run again: anything already done is skipped, broken downloads resume.
#   1. Portable Python in runtime\python + numpy and pymupdf
#   2. AI engine: llama.cpp for Windows (CPU build) from GitHub
#   3. Models: the chat model and the search model from Hugging Face
#   4. Speed test: loads the chat model and times one answer
# Written in plain ASCII so Windows PowerShell 5.1 reads it correctly.

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Report = New-Object System.Collections.Generic.List[string]
function Say([string]$m) { Write-Host ("  " + $m) }
function Note([string]$m) { $Report.Add($m); Write-Host ("  " + $m) }

foreach ($d in 'books', 'models', 'engine', 'data', 'logs') {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root $d) | Out-Null
}
$ReportPath = Join-Path $Root 'logs\setup_report.txt'
$Config = Get-Content (Join-Path $Root 'config.json') -Raw | ConvertFrom-Json
$Report.Add("QuantaKai setup report - " + (Get-Date -Format 'yyyy-MM-dd HH:mm'))
$Report.Add("Folder: $Root")

# ===================================================================== 1. Python
# QuantaKai carries its own portable Python ("embeddable package") in runtime\python,
# so it never depends on the Python installed on the computer. That is what lets
# you move the folder anywhere.
Write-Host ""
Write-Host "[1/4] Portable Python"
$RuntimeDir = Join-Path $Root 'runtime\python'
$Py = Join-Path $RuntimeDir 'python.exe'
$WheelDir = Join-Path $Root 'runtime\wheels'
$SitePackages = Join-Path $RuntimeDir 'Lib\site-packages'
$PyVersions = @('3.14.5', '3.14.4', '3.14.3', '3.14.2', '3.14.1', '3.14.0')

function Test-Runtime {
    if (-not (Test-Path $Py)) { return $false }
    & $Py -c "import numpy, pymupdf" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Find-Python {
    foreach ($cmd in @('py', 'python')) {
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { continue }
        try {
            if ($cmd -eq 'py') { $out = & py -3 -c "import sys; print(sys.executable)" 2>$null }
            else { $out = & python -c "import sys; print(sys.executable)" 2>$null }
            if ($LASTEXITCODE -eq 0 -and $out) {
                $p = ($out | Select-Object -Last 1).Trim()
                if (Test-Path $p) { return $p }
            }
        } catch { }
    }
    return $null
}

if (Test-Runtime) {
    Say "Portable Python already set up."
} else {
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    if (-not (Test-Path $Py)) {
        foreach ($v in $PyVersions) {
            $zip = Join-Path $Root "runtime\python-$v-embed-amd64.zip"
            Say "Downloading portable Python $v from python.org..."
            & curl.exe -L --fail --retry 3 -s -o $zip "https://www.python.org/ftp/python/$v/python-$v-embed-amd64.zip"
            if ($LASTEXITCODE -eq 0) {
                Expand-Archive -Path $zip -DestinationPath $RuntimeDir -Force
                Remove-Item $zip -Force
                break
            }
            if (Test-Path $zip) { Remove-Item $zip -Force }
        }
    }
    if (Test-Path $Py) {
        # The ._pth file tells portable Python where to look for code:
        #   its own zip, its own folder, Lib\site-packages, and ..\.. (the QuantaKai folder).
        # All paths are relative, so they stay correct wherever the folder is moved.
        $pth = Get-ChildItem -Path $RuntimeDir -Filter 'python3*._pth' | Select-Object -First 1
        $stdlib = Get-ChildItem -Path $RuntimeDir -Filter 'python3*.zip' | Select-Object -First 1
        if ($pth -and $stdlib) {
            Set-Content -Path $pth.FullName -Value @($stdlib.Name, '.', 'Lib\site-packages', '..\..', 'import site') -Encoding ASCII
        }
        New-Item -ItemType Directory -Force -Path $SitePackages | Out-Null
        # Install numpy and pymupdf by unpacking the .whl files shipped in runtime\wheels.
        foreach ($w in (Get-ChildItem -Path $WheelDir -Filter '*.whl' -ErrorAction SilentlyContinue)) {
            Say ("Unpacking " + $w.Name + " ...")
            & $Py -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" $w.FullName $SitePackages
        }
        if (-not (Test-Runtime)) {
            # Fallback: ask any installed Python's pip to fetch packages that match the portable Python.
            $sysPy = Find-Python
            if ($sysPy) {
                $ver = (& $Py -c "import sys; print('%d.%d' % sys.version_info[:2])").Trim()
                Say "Fetching packages for Python $ver with pip..."
                & $sysPy -m pip install --disable-pip-version-check -q --upgrade --target $SitePackages `
                    --platform win_amd64 --python-version $ver --only-binary=:all: -r (Join-Path $Root 'requirements.txt')
            }
        }
    }
}
if (Test-Runtime) {
    $pv = (& $Py -c "import sys, numpy, pymupdf; print(sys.version.split()[0], '| numpy', numpy.__version__, '| pymupdf', pymupdf.__version__)").Trim()
    Note "PYTHON: OK (portable Python $pv)"
} elseif (-not (Test-Path $Py)) {
    Note "PYTHON: FAILED - could not download portable Python from python.org. Check the internet and run SETUP.bat again."
} else {
    Note "PYTHON: FAILED - numpy or pymupdf would not load. Read the messages above."
}

# ===================================================================== 2. Engine
Write-Host ""
Write-Host "[2/4] AI engine (llama.cpp)"
$EngineDir = Join-Path $Root 'engine'
function Find-Server {
    $f = Get-ChildItem -Path $EngineDir -Recurse -Filter 'llama-server.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($f) { return $f.FullName }
    return $null
}
$Server = Find-Server
if ($Server) {
    Say "Engine already present."
} else {
    Say "Asking GitHub for the newest Windows CPU build..."
    try {
        $rels = Invoke-RestMethod -Uri 'https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=20' `
                                  -Headers @{ 'User-Agent' = 'quantakai-setup' }
        $asset = $null
        foreach ($r in $rels) {
            $asset = $r.assets | Where-Object { $_.name -like 'llama-*-bin-win-cpu-x64.zip' } | Select-Object -First 1
            if ($asset) { break }
        }
        if ($asset) {
            $zip = Join-Path $EngineDir $asset.name
            Say ("Downloading " + $asset.name + " ...")
            & curl.exe -L --fail --retry 3 -o $zip $asset.browser_download_url
            if ($LASTEXITCODE -eq 0) {
                Expand-Archive -Path $zip -DestinationPath $EngineDir -Force
                Remove-Item $zip -Force
                $Server = Find-Server
                if ($Server) { $Report.Add("ENGINE SOURCE: " + $asset.name) }
            }
        } else { Say "No Windows CPU build found in the latest releases." }
    } catch {
        Say ("GitHub download failed: " + $_.Exception.Message)
    }
    if (-not $Server) {
        $old = Join-Path $HOME 'Desktop\Schooly\python\QuantaKai\tools\llama.cpp'
        if (Test-Path (Join-Path $old 'llama-server.exe')) {
            Say "Using the older engine copy from the QuantaKai group project instead..."
            Copy-Item -Path (Join-Path $old '*') -Destination $EngineDir -Recurse -Force
            $Server = Find-Server
            if ($Server) { $Report.Add("ENGINE SOURCE: copied from the group project (Schooly\python\QuantaKai\tools\llama.cpp)") }
        }
    }
}
if ($Server) { Note "ENGINE: OK ($Server)" }
else { Note "ENGINE: FAILED - download llama.cpp by hand (BUILD_GUIDE.html, Download the engine) and unzip it into the engine folder." }

# ===================================================================== 3. Models
Write-Host ""
Write-Host "[3/4] Models"
function Test-Gguf([string]$Path) {
    if (-not (Test-Path $Path)) { return $false }
    try {
        $s = [System.IO.File]::OpenRead($Path)
        try {
            $b = New-Object byte[] 4
            if ($s.Read($b, 0, 4) -ne 4) { return $false }
            return ([System.Text.Encoding]::ASCII.GetString($b) -eq 'GGUF')
        } finally { $s.Dispose() }
    } catch { return $false }
}
function Get-Model([string]$Name, [string[]]$Urls, [double]$MinMB, [string]$Label) {
    $dest = Join-Path $Root ("models\" + $Name)
    if ((Test-Gguf $dest) -and ((Get-Item $dest).Length / 1MB) -ge $MinMB) {
        Note ("{0}: OK (already downloaded, {1:N0} MB)" -f $Label, ((Get-Item $dest).Length / 1MB))
        return $true
    }
    $part = $dest + '.part'
    foreach ($u in $Urls) {
        Say "Downloading $Name (it resumes if the connection drops)..."
        & curl.exe -L --fail --retry 5 --retry-delay 5 -C - -o $part $u
        if ($LASTEXITCODE -eq 0 -and (Test-Gguf $part) -and ((Get-Item $part).Length / 1MB) -ge $MinMB) {
            Move-Item -Force $part $dest
            Note ("{0}: OK ({1:N0} MB)" -f $Label, ((Get-Item $dest).Length / 1MB))
            return $true
        }
        if ((Test-Path $part) -and -not (Test-Gguf $part)) { Remove-Item $part -Force }
    }
    Note "${Label}: FAILED - download did not finish. Run SETUP.bat again to resume."
    return $false
}

$chatOk = Get-Model $Config.default_model @(
    'https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf'
) 1500 'CHAT MODEL (Qwen2.5 3B, about 1.9 GB)'

$embedOk = Get-Model $Config.embedding_model @(
    'https://huggingface.co/ggml-org/bge-small-en-v1.5-Q8_0-GGUF/resolve/main/bge-small-en-v1.5-q8_0.gguf',
    'https://huggingface.co/CompendiumLabs/bge-small-en-v1.5-gguf/resolve/main/bge-small-en-v1.5-q8_0.gguf'
) 20 'SEARCH MODEL (bge-small, about 37 MB)'

# ===================================================================== 4. Speed test
Write-Host ""
Write-Host "[4/4] Speed test"
if ($Server -and $chatOk) {
    $port = [int]$Config.chat_port
    $modelPath = Join-Path $Root ("models\" + $Config.default_model)
    $outLog = Join-Path $Root 'logs\speedtest.out.log'
    $errLog = Join-Path $Root 'logs\speedtest.err.log'
    $engineArgs = @('-m', ('"{0}"' -f $modelPath), '-c', "$($Config.context_window)", '-t', "$($Config.threads)",
                    '-ngl', "$($Config.gpu_layers)", '--parallel', '1', '--host', '127.0.0.1', '--port', "$port")
    $proc = $null
    try {
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        $proc = Start-Process -FilePath $Server -ArgumentList $engineArgs -WorkingDirectory $Root `
            -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
        $ready = $false
        $deadline = (Get-Date).AddSeconds(240)
        while ((Get-Date) -lt $deadline) {
            try {
                $h = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
                if ($h.StatusCode -eq 200) { $ready = $true; break }
            } catch { }
            if ($proc.HasExited) { break }
            Start-Sleep -Milliseconds 500
        }
        $watch.Stop()
        if (-not $ready) {
            Note "SPEED TEST: FAILED - the engine did not start. Read logs\speedtest.err.log"
        } else {
            Note ("MODEL LOAD TIME: {0:N1} s" -f $watch.Elapsed.TotalSeconds)
            Say "Asking a test question (can take up to a minute)..."
            $body = @{
                messages = @(
                    @{ role = 'system'; content = 'You are a helpful tutor. Explain simply.' },
                    @{ role = 'user'; content = 'In about 80 words, explain what overfitting means in machine learning to a beginner.' }
                )
                max_tokens = 140
                temperature = 0.2
            } | ConvertTo-Json -Depth 5
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$port/v1/chat/completions" -Method Post `
                -ContentType 'application/json' -Body $body -TimeoutSec 300
            $sw.Stop()
            $tokens = [int]$resp.usage.completion_tokens
            $tps = 0.0
            if ($resp.timings -and $resp.timings.predicted_per_second) { $tps = [double]$resp.timings.predicted_per_second }
            elseif ($sw.Elapsed.TotalSeconds -gt 0) { $tps = $tokens / $sw.Elapsed.TotalSeconds }
            Note ("SPEED TEST: OK - {0} tokens in {1:N1} s = {2:N1} tokens per second (processor only, {3} threads)" -f $tokens, $sw.Elapsed.TotalSeconds, $tps, $Config.threads)
            if ($resp.timings -and $resp.timings.prompt_per_second) {
                Note ("READING SPEED: {0:N1} tokens per second" -f [double]$resp.timings.prompt_per_second)
            }
            $Report.Add("TEST ANSWER: " + ($resp.choices[0].message.content -replace "\s+", ' '))
            Write-Host ""
            Write-Host "  The model answered:"
            Write-Host ("  " + $resp.choices[0].message.content)
        }
    } catch {
        Note ("SPEED TEST: FAILED - " + $_.Exception.Message)
    } finally {
        if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    }
} else {
    Note "SPEED TEST: SKIPPED (engine or chat model missing)"
}

try {
    $os = Get-CimInstance Win32_OperatingSystem
    $Report.Add(("FREE RAM AT END: {0:N1} GB" -f ($os.FreePhysicalMemory / 1MB)))
    $drive = Get-PSDrive -Name ($Root.Substring(0, 1))
    $Report.Add(("FREE DISK: {0:N1} GB" -f ($drive.Free / 1GB)))
} catch { }

$Report | Set-Content -Path $ReportPath -Encoding UTF8
Write-Host ""
Write-Host "================================================================"
$Report | Where-Object { $_ -match '^(PYTHON|ENGINE|CHAT MODEL|SEARCH MODEL|SPEED TEST|MODEL LOAD)' } | ForEach-Object { Write-Host ("  " + $_) }
Write-Host "================================================================"
Write-Host "  Next: double-click START.bat"
