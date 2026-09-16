# Stops all NOHTUS WMS related servers (desktop Streamlit app, mobile API).
# Finds processes by command line (not just image name) so it never touches
# unrelated python.exe processes on this machine.
# start_mobile_api.bat auto-restarts itself in a loop, so killing only the
# python (uvicorn) process would bring it back in ~5 seconds -- this also
# kills the cmd.exe running that loop.

$patterns = @(
    'streamlit run app\.py',
    'uvicorn nohtus\.mobile_api\.main',
    'run_wms\.bat',
    'start_mobile_api\.bat'
)

$procs = Get-CimInstance Win32_Process | Where-Object {
    $cmd = $_.CommandLine
    if (-not $cmd) { return $false }
    foreach ($p in $patterns) {
        if ($cmd -match $p) { return $true }
    }
    return $false
}

if (-not $procs) {
    Write-Host "No matching WMS server processes found (may already be stopped)."
} else {
    foreach ($p in $procs) {
        Write-Host ("Killing PID {0} ({1}) - {2}" -f $p.ProcessId, $p.Name, $p.CommandLine)
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Done."
}
