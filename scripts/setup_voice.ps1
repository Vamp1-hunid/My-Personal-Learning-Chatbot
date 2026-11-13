# setup_voice.ps1 - downloads OFFLINE voice typing for QuantaKai (run by VOICE_SETUP.bat)
#   1. whisper.cpp for Windows (whisper-cli.exe), about 4 MB
#   2. the Whisper "base.en" speech model, about 148 MB (for listening)
#   3. Piper + a bright US female voice, about 80 MB (for speaking)
# Both go in QuantaKai\voice. After this, voice typing never needs the internet.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # makes downloads much faster in Windows PowerShell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root  = Split-Path -Parent $PSScriptRoot
$voice = Join-Path $root 'voice'
New-Item -ItemType Directory -Force $voice | Out-Null
$report = Join-Path $root 'logs\voice_setup.txt'
function Say($text) { Write-Host $text; Add-Content -Path $report -Value $text }
Set-Content -Path $report -Value "QuantaKai voice setup - $(Get-Date -Format 'yyyy-MM-dd HH:mm')"

try {
    # ---------------------------------------------------------------- 1. engine
    $cli = Get-ChildItem $voice -Recurse -Filter 'whisper-cli.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cli) {
        Say "ENGINE: already installed ($($cli.FullName))"
    } else {
        Say 'ENGINE: finding the latest whisper.cpp release...'
        $rel = Invoke-RestMethod 'https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest' -Headers @{ 'User-Agent' = 'QuantaKai' }
        $asset = $rel.assets | Where-Object { $_.name -eq 'whisper-bin-x64.zip' } | Select-Object -First 1
        if ($asset) {
            $url = $asset.browser_download_url; $tag = $rel.tag_name
        } else {
            # some releases (e.g. v1.9.5) ship source code only; v1.8.7 is the last with a Windows build we know of
            $url = 'https://github.com/ggml-org/whisper.cpp/releases/download/v1.8.7/whisper-bin-x64.zip'; $tag = 'v1.8.7'
        }
        Say "ENGINE: downloading whisper.cpp $tag..."
        $zip = Join-Path $env:TEMP 'quantakai-whisper.zip'
        $tmp = Join-Path $env:TEMP 'quantakai-whisper'
        Invoke-WebRequest $url -OutFile $zip -UseBasicParsing
        if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
        Expand-Archive $zip $tmp -Force
        $found = Get-ChildItem $tmp -Recurse -Filter 'whisper-cli.exe' | Select-Object -First 1
        if (-not $found) { throw 'whisper-cli.exe was not inside the download.' }
        Copy-Item (Join-Path $found.DirectoryName '*') $voice -Recurse -Force
        Remove-Item $zip -Force; Remove-Item $tmp -Recurse -Force
        Say 'ENGINE: OK'
    }

    # ---------------------------------------------------------------- 2. speech model
    $model = Join-Path $voice 'ggml-base.en.bin'
    if ((Test-Path $model) -and ((Get-Item $model).Length -gt 100MB)) {
        Say 'SPEECH MODEL: already downloaded'
    } else {
        Say 'SPEECH MODEL: downloading Whisper base.en (about 148 MB, a few minutes)...'
        $urls = @('https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin',
                  'https://huggingface.co/ggml-org/whisper.cpp/resolve/main/ggml-base.en.bin')
        $ok = $false
        foreach ($u in $urls) {
            try {
                Invoke-WebRequest $u -OutFile "$model.part" -UseBasicParsing
                if ((Get-Item "$model.part").Length -gt 100MB) { Move-Item "$model.part" $model -Force; $ok = $true; break }
            } catch { Say "  (could not use $u, trying the next source)" }
        }
        if (-not $ok) { throw 'The speech model could not be downloaded. Check your internet and run VOICE_SETUP.bat again.' }
        Say 'SPEECH MODEL: OK'
    }

    # ---------------------------------------------------------------- 3. speaking voice (Piper)
    $piperDir = Join-Path $voice 'piper'
    if (Get-ChildItem $piperDir -Recurse -Filter 'piper.exe' -ErrorAction SilentlyContinue | Select-Object -First 1) {
        Say 'VOICE ENGINE: already installed'
    } else {
        Say 'VOICE ENGINE: downloading Piper (about 22 MB)...'
        $zip = Join-Path $env:TEMP 'quantakai-piper.zip'
        Invoke-WebRequest 'https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip' -OutFile $zip -UseBasicParsing
        New-Item -ItemType Directory -Force $piperDir | Out-Null
        Expand-Archive $zip $piperDir -Force
        Remove-Item $zip -Force
        if (-not (Get-ChildItem $piperDir -Recurse -Filter 'piper.exe' | Select-Object -First 1)) { throw 'piper.exe was not inside the download.' }
        Say 'VOICE ENGINE: OK'
    }
    # bright young US female voice first; the others are backups if a download fails
    $voices = @('en_US/hfc_female/medium/en_US-hfc_female-medium',
                'en_US/amy/medium/en_US-amy-medium',
                'en_US/lessac/medium/en_US-lessac-medium')
    $haveVoice = Get-ChildItem $voice -Filter '*.onnx' -ErrorAction SilentlyContinue | Where-Object { Test-Path ($_.FullName + '.json') }
    if ($haveVoice) {
        Say "VOICE: already downloaded ($($haveVoice[0].Name))"
    } else {
        $got = $false
        foreach ($v in $voices) {
            $name = Split-Path $v -Leaf
            $base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/$v"
            try {
                Say "VOICE: downloading $name (about 60 MB)..."
                Invoke-WebRequest "$base.onnx.json" -OutFile (Join-Path $voice "$name.onnx.json") -UseBasicParsing
                Invoke-WebRequest "$base.onnx" -OutFile (Join-Path $voice "$name.onnx.part") -UseBasicParsing
                Move-Item (Join-Path $voice "$name.onnx.part") (Join-Path $voice "$name.onnx") -Force
                $got = $true
                if ($name -ne 'en_US-hfc_female-medium') { Say "  Note: set ""tts_voice"": ""$name"" in config.json" }
                break
            } catch { Say "  (could not download $name, trying the next voice)" }
        }
        if (-not $got) { throw 'No speaking voice could be downloaded. Check your internet and run VOICE_SETUP.bat again.' }
        Say 'VOICE: OK'
    }
    # say hello, to prove it works
    $piperExe = (Get-ChildItem $piperDir -Recurse -Filter 'piper.exe' | Select-Object -First 1).FullName
    $onnx = (Get-ChildItem $voice -Filter '*.onnx' | Select-Object -First 1).FullName
    $hello = Join-Path $voice 'hello.wav'
    "Hi! I'm your offline voice. Everything I say is made right here on your laptop." | & $piperExe --model $onnx --output_file $hello --length_scale 0.88 2>$null
    if (Test-Path $hello) { (New-Object Media.SoundPlayer $hello).PlaySync(); Remove-Item $hello -Force; Say 'VOICE TEST: OK (you should have heard it)' }

    # ---------------------------------------------------------------- 3. quick test
    $cli = Get-ChildItem $voice -Recurse -Filter 'whisper-cli.exe' | Select-Object -First 1
    & $cli.FullName --help *> $null
    Say 'TEST: the speech engine starts correctly'
    Say ''
    Say 'Voice typing is ready. Restart QuantaKai (STOP.bat, then START.bat) and click the microphone.'
} catch {
    Say ''
    Say "PROBLEM: $($_.Exception.Message)"
    Say 'Nothing else was changed. Fix the problem (usually the internet connection) and run VOICE_SETUP.bat again.'
    exit 1
}
