$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv-hindsight\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "The Hindsight Python environment is missing. Run the setup steps in README.md first."
}

$apiUrl = (Read-Host "Hindsight Cloud API base URL from your Cloud account").Trim().TrimEnd("/")
if ([string]::IsNullOrWhiteSpace($apiUrl)) {
    throw "Enter the Hindsight Cloud API base URL."
}

$parsedUrl = $null
if (-not [Uri]::TryCreate($apiUrl, [UriKind]::Absolute, [ref]$parsedUrl)) {
    throw "Enter a complete API URL such as https://your-api-host."
}
if (
    $parsedUrl.Scheme -ne "https" -or
    -not [string]::IsNullOrEmpty($parsedUrl.UserInfo) -or
    -not [string]::IsNullOrEmpty($parsedUrl.Query) -or
    -not [string]::IsNullOrEmpty($parsedUrl.Fragment)
) {
    throw "Use the HTTPS API base URL only. Do not put credentials in the URL."
}

$secureKey = Read-Host "Hindsight API key (hidden input; it will not be saved to a file)" -AsSecureString
if ($secureKey.Length -eq 0) {
    throw "An API key is required to start this live Hindsight connection."
}

$bankId = (Read-Host "Hindsight memory bank ID [shiftline-acme-logistics]").Trim()
if ([string]::IsNullOrWhiteSpace($bankId)) {
    $bankId = "shiftline-acme-logistics"
}
if ($bankId -notmatch "^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$") {
    throw "The bank ID may only contain letters, numbers, dots, underscores and hyphens."
}

$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($listener) {
    throw "Port 8000 is already in use (PID $($listener.OwningProcess)). Stop the existing Shiftline server, then rerun this script."
}

$pointer = [IntPtr]::Zero
$apiKey = $null
$environmentNames = @(
    "SHIFTLINE_MEMORY_MODE",
    "HINDSIGHT_API_URL",
    "HINDSIGHT_API_KEY",
    "HINDSIGHT_BANK_ID",
    "PORT"
)
$priorEnvironment = @{}
foreach ($name in $environmentNames) {
    $priorEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)

    $env:SHIFTLINE_MEMORY_MODE = "hindsight"
    $env:HINDSIGHT_API_URL = $apiUrl
    $env:HINDSIGHT_API_KEY = $apiKey
    $env:HINDSIGHT_BANK_ID = $bankId
    $env:PORT = "8000"

    Write-Host ""
    Write-Host "Starting Shiftline against live Hindsight."
    Write-Host "Memory bank: $bankId"
    Write-Host "The API key is used only by this process and is not written to a file."
    Write-Host "Open http://127.0.0.1:8000. Leave this terminal open while using the app."
    Write-Host ""
    Push-Location $projectRoot
    try {
        & $python "server.py"
        if ($LASTEXITCODE -ne 0) {
            throw "Shiftline exited with code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    $apiKey = $null
    $secureKey.Dispose()
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $priorEnvironment[$name], "Process")
    }
}
