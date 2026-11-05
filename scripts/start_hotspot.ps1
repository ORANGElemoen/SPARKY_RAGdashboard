# Turns on the Windows Mobile Hotspot, including with no internet connection. The Settings page refuses
# when there is nothing to share, but Windows accepts the same request from a program when it's
# pointed at a connection that has no internet. Same hotspot name and password as in Settings.
# Exits 0 when the hotspot is on, and 1 when it couldn't be turned on.
$ErrorActionPreference = 'Stop'
try {
    [void][Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType = WindowsRuntime]
    [void][Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime]
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    } | Select-Object -First 1

    $info = [Windows.Networking.Connectivity.NetworkInformation]
    $profile = $info::GetInternetConnectionProfile()
    if (-not $profile) { $profile = $info::GetConnectionProfiles() | Select-Object -First 1 }
    if (-not $profile) { throw 'Windows has no network connections listed.' }

    $manager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
    if ($manager.TetheringOperationalState -eq 'On') {
        Write-Host 'The hotspot is already on.'
        exit 0
    }
    $type = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult]
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($manager.StartTetheringAsync()))
    if (-not $task.Wait(30000)) { throw 'Windows took too long to answer.' }
    if ($task.Result.Status -ne 'Success') { throw "Windows said: $($task.Result.Status) $($task.Result.AdditionalErrorMessage)" }
    Write-Host "The hotspot is on (using connection: $($profile.ProfileName))."
    exit 0
}
catch {
    Write-Host "Couldn't turn on the hotspot: $($_.Exception.Message)"
    exit 1
}
