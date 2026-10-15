param(
    [Parameter(Mandatory = $true)]
    [string]$ExecutablePath
)

$ErrorActionPreference = "Stop"

$executable = (Resolve-Path -LiteralPath $ExecutablePath).Path
$workingDirectory = Split-Path -Parent $executable
$appDataRoot = Join-Path $env:RUNNER_TEMP "scumgui-smoke-$([guid]::NewGuid().ToString('N'))"
$lockPath = Join-Path $appDataRoot "ScumGUI\instance.lock"
$queuePath = Join-Path $appDataRoot "ScumGUI\queue.json"
$forwardedUrl = "https://example.com/scumgui-ci-forward"
$primary = $null
$secondary = $null

$env:APPDATA = $appDataRoot
$env:QT_QPA_PLATFORM = "offscreen"

try {
    $primary = Start-Process -FilePath $executable -WorkingDirectory $workingDirectory -WindowStyle Hidden -PassThru
    $startupDeadline = (Get-Date).AddSeconds(30)

    while ((Get-Date) -lt $startupDeadline -and -not (Test-Path -LiteralPath $lockPath)) {
        $primary.Refresh()
        if ($primary.HasExited) {
            throw "The packaged application exited during startup (code $($primary.ExitCode))."
        }
        Start-Sleep -Milliseconds 200
    }

    $primary.Refresh()
    if ($primary.HasExited) {
        throw "The packaged application exited before acquiring its instance lock (code $($primary.ExitCode))."
    }
    if (-not (Test-Path -LiteralPath $lockPath)) {
        throw "The packaged application did not acquire its instance lock within 30 seconds."
    }

    $secondary = Start-Process -FilePath $executable -ArgumentList @($forwardedUrl) -WorkingDirectory $workingDirectory -WindowStyle Hidden -PassThru
    if (-not $secondary.WaitForExit(15000)) {
        throw "The second packaged launch did not exit after submitting its URL."
    }
    $secondary.Refresh()
    if ($secondary.ExitCode -ne 0) {
        throw "The second packaged launch failed with exit code $($secondary.ExitCode)."
    }

    $queueDeadline = (Get-Date).AddSeconds(10)
    $urlPersisted = $false
    while ((Get-Date) -lt $queueDeadline -and -not $urlPersisted) {
        if (Test-Path -LiteralPath $queuePath) {
            try {
                $queue = Get-Content -LiteralPath $queuePath -Raw | ConvertFrom-Json
                $urlPersisted = @($queue | Where-Object { $_.url -eq $forwardedUrl }).Count -gt 0
            } catch {
                # The queue file may be between writes; retry until the deadline.
            }
        }
        if (-not $urlPersisted) {
            Start-Sleep -Milliseconds 200
        }
    }

    if (-not $urlPersisted) {
        throw "The forwarded URL was not written to the primary instance's queue."
    }

    $primary.Refresh()
    if ($primary.HasExited) {
        throw "The primary packaged application exited after the second launch."
    }

    Write-Host "Packaged startup succeeded; the second launch forwarded its URL to the still-running primary instance."
} finally {
    foreach ($process in @($secondary, $primary)) {
        if ($null -ne $process) {
            $process.Refresh()
            if (-not $process.HasExited) {
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                $process.WaitForExit(5000) | Out-Null
            }
        }
    }

    if (Test-Path -LiteralPath $appDataRoot) {
        Remove-Item -LiteralPath $appDataRoot -Recurse -Force
    }
}
