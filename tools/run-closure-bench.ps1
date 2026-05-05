param(
    [ValidateSet("A0", "A1", "A2", "A3", "all")]
    [string]$Case = "all",

    [string]$Tasks = "ifeval,gsm8k",
    [int]$Limit = 50,
    [string]$RawModel = "qwen3:8b",
    [string]$SplitProfile = "qwen3-8b-local-max",
    [string]$HfModel = "Qwen/Qwen3-8B",
    [string]$AdapterDir = "runs\qwen3-8b-main-agent-v19-v18-failure-repair-lora-20260505",
    [int]$Port = 8010,
    [string]$Python = ".\.venv-bench\Scripts\python.exe",
    [string]$AdapterPython = ".\.venv-lora\Scripts\python.exe",
    [string]$OutputRoot = "runs\closure-bench",
    [int]$ServerWarmupSeconds = 5,
    [switch]$NoLimit,
    [switch]$PreflightOnly,
    [switch]$AdapterNo4bit,
    [switch]$EnableThinking
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$repo = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputRootPath = Join-Path $repo $OutputRoot

function Resolve-RepoPath {
    param([string]$PathText)
    if ([string]::IsNullOrWhiteSpace($PathText)) {
        return $null
    }
    if ([System.IO.Path]::IsPathRooted($PathText)) {
        return [System.IO.Path]::GetFullPath($PathText)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $repo $PathText))
}

function Resolve-CommandPath {
    param([string]$Command)
    if ([string]::IsNullOrWhiteSpace($Command)) {
        return $Command
    }
    if ($Command.Contains("\") -or $Command.Contains("/") -or [System.IO.Path]::IsPathRooted($Command)) {
        return Resolve-RepoPath $Command
    }
    return $Command
}

function Test-PythonCommand {
    param([string]$Command, [string]$Label)
    & $Command --version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "$Label is not runnable: $Command"
    }
}

function Test-LmEval {
    Test-PythonCommand -Command $Python -Label "Benchmark Python"
    & $Python -m lm_eval --help *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "lm-eval is not installed for this Python. Install with: $Python -m pip install `"lm-eval[api,ifeval]`""
    }
}

function Resolve-AdapterDirectory {
    if (-not [string]::IsNullOrWhiteSpace($AdapterDir)) {
        $explicit = Resolve-RepoPath $AdapterDir
        if (-not (Test-Path (Join-Path $explicit "adapter_config.json"))) {
            throw "AdapterDir does not look like a PEFT adapter directory: $explicit"
        }
        return $explicit
    }

    throw "AdapterDir is required for A2/A3. The default is the best local candidate, not the newest adapter."
}

function Invoke-LmEvalRun {
    param(
        [string]$Name,
        [string]$ModelName,
        [string]$BaseUrl
    )

    $out = Join-Path $outputRootPath "$Name-$stamp"
    $modelArgs = "model=$ModelName,base_url=$BaseUrl,num_concurrent=1,max_retries=3,tokenized_requests=False"
    $cmd = @(
        "-m", "lm_eval", "run",
        "--model", "local-chat-completions",
        "--model_args", $modelArgs,
        "--tasks", $Tasks,
        "--apply_chat_template",
        "--output_path", $out,
        "--log_samples"
    )
    if (-not $NoLimit) {
        $cmd += @("--limit", "$Limit")
    }

    Write-Host "Running $Name"
    & $Python @cmd
    if ($LASTEXITCODE -ne 0) {
        throw "lm-eval failed for $Name"
    }
}

function Wait-BenchServer {
    param([int]$ListenPort)
    $deadline = (Get-Date).AddSeconds([Math]::Max(10, $ServerWarmupSeconds + 60))
    do {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ListenPort/health" -TimeoutSec 2
            if ($health.status -eq "ok") {
                return
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)
    throw "Benchmark wrapper on port $ListenPort did not become healthy."
}

function Start-PublicBenchServer {
    param(
        [string]$Mode,
        [string]$Alias
    )

    $serverArgs = @(
        (Join-Path $repo "tools\public_bench_server.py"),
        "--profile", $SplitProfile,
        "--mode", $Mode,
        "--port", "$Port",
        "--model-alias", $Alias
    )
    $server = Start-Process -FilePath $Python -ArgumentList $serverArgs -PassThru -WindowStyle Hidden -WorkingDirectory $repo
    Start-Sleep -Seconds $ServerWarmupSeconds
    Wait-BenchServer -ListenPort $Port
    return $server
}

function Start-AdapterBenchServer {
    param(
        [string]$Mode,
        [string]$Alias,
        [string]$ResolvedAdapterDir
    )

    $serverArgs = @(
        (Join-Path $repo "tools\adapter_public_bench_server.py"),
        "--model", $HfModel,
        "--adapter-dir", $ResolvedAdapterDir,
        "--profile", $SplitProfile,
        "--mode", $Mode,
        "--port", "$Port",
        "--model-alias", $Alias
    )
    if ($AdapterNo4bit) {
        $serverArgs += "--no-4bit"
    }
    if ($EnableThinking) {
        $serverArgs += "--enable-thinking"
    }

    $server = Start-Process -FilePath $AdapterPython -ArgumentList $serverArgs -PassThru -WindowStyle Hidden -WorkingDirectory $repo
    Start-Sleep -Seconds $ServerWarmupSeconds
    Wait-BenchServer -ListenPort $Port
    return $server
}

function Invoke-WithServer {
    param(
        [scriptblock]$StartBlock,
        [scriptblock]$RunBlock
    )

    $server = & $StartBlock
    try {
        & $RunBlock
    }
    finally {
        if ($null -ne $server -and -not $server.HasExited) {
            Stop-Process -Id $server.Id -Force
        }
    }
}

function Write-PreflightSummary {
    param([string]$ResolvedAdapterDir)
    $limitLabel = if ($NoLimit) { "none" } else { "$Limit" }
    [pscustomobject]@{
        case = $Case
        tasks = $Tasks
        limit = $limitLabel
        raw_model = $RawModel
        split_profile = $SplitProfile
        hf_model = $HfModel
        adapter_dir = $ResolvedAdapterDir
        output_root = $outputRootPath
        benchmark_python = $Python
        adapter_python = $AdapterPython
    } | ConvertTo-Json -Depth 3
}

$Python = Resolve-CommandPath $Python
$AdapterPython = Resolve-CommandPath $AdapterPython
$outputRootPath = Resolve-RepoPath $OutputRoot

New-Item -ItemType Directory -Force -Path $outputRootPath | Out-Null
Test-LmEval
$needsAdapter = $Case -eq "A2" -or $Case -eq "A3" -or $Case -eq "all"
if ($needsAdapter) {
    Test-PythonCommand -Command $AdapterPython -Label "Adapter Python"
    $resolvedAdapterDir = Resolve-AdapterDirectory
}
else {
    $resolvedAdapterDir = ""
}

Write-PreflightSummary -ResolvedAdapterDir $resolvedAdapterDir
if ($PreflightOnly) {
    Write-Host "Preflight only; no benchmark cases were run."
    exit 0
}

if ($Case -eq "A0" -or $Case -eq "all") {
    Invoke-LmEvalRun -Name "A0-raw-b8" -ModelName $RawModel -BaseUrl "http://localhost:11434/v1/chat/completions"
}

if ($Case -eq "A1" -or $Case -eq "all") {
    Invoke-WithServer `
        -StartBlock { Start-PublicBenchServer -Mode "pipeline" -Alias "A1-split-b8" } `
        -RunBlock { Invoke-LmEvalRun -Name "A1-split-b8" -ModelName "A1-split-b8" -BaseUrl "http://127.0.0.1:$Port/v1/chat/completions" }
}

if ($Case -eq "A2" -or $Case -eq "all") {
    Invoke-WithServer `
        -StartBlock { Start-AdapterBenchServer -Mode "raw" -Alias "A2-raw-b8-adapter" -ResolvedAdapterDir $resolvedAdapterDir } `
        -RunBlock { Invoke-LmEvalRun -Name "A2-raw-b8-adapter" -ModelName "A2-raw-b8-adapter" -BaseUrl "http://127.0.0.1:$Port/v1/chat/completions" }
}

if ($Case -eq "A3" -or $Case -eq "all") {
    Invoke-WithServer `
        -StartBlock { Start-AdapterBenchServer -Mode "pipeline" -Alias "A3-split-b8-adapter" -ResolvedAdapterDir $resolvedAdapterDir } `
        -RunBlock { Invoke-LmEvalRun -Name "A3-split-b8-adapter" -ModelName "A3-split-b8-adapter" -BaseUrl "http://127.0.0.1:$Port/v1/chat/completions" }
}
