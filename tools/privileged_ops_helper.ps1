#!/usr/bin/env powershell
<#
.SYNOPSIS
    Privileged Operations Helper for FryNetworks Miner GUI Service

.DESCRIPTION
    This PowerShell script runs the privileged operations Python module with admin privileges.
    The NSSM service (which runs as SYSTEM) can call this to perform admin-required tasks
    like adding firewall rules or killing processes.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File privileged_ops_helper.ps1 -Operation SetupMysteryumFirewall
    powershell -ExecutionPolicy Bypass -File privileged_ops_helper.ps1 -Operation AddFirewallRule -Port 4050 -Protocol tcp
    powershell -ExecutionPolicy Bypass -File privileged_ops_helper.ps1 -Operation KillProcess -PID 12345

.NOTES
    Requires admin privileges to run.
    The Python environment must have miner_GUI package installed.
#>

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('SetupMysteryumFirewall', 'AddFirewallRule', 'RemoveFirewallRule', 'KillProcess')]
    [string]$Operation,
    
    [Parameter(Mandatory=$false)]
    [int]$Port,
    
    [Parameter(Mandatory=$false)]
    [ValidateSet('tcp', 'udp')]
    [string]$Protocol = 'tcp',
    
    [Parameter(Mandatory=$false)]
    [ValidateSet('in', 'out', 'in,out')]
    [string]$Direction = 'in',
    
    [Parameter(Mandatory=$false)]
    [int]$PID,
    
    [Parameter(Mandatory=$false)]
    [string]$RuleName,
    
    [Parameter(Mandatory=$false)]
    [string]$PythonInterpreter = 'python'
)

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Error "This script must be run as Administrator"
    exit 1
}

# Build Python command
$pythonArgs = @("-m", "miner_GUI.services.privileged_ops")

switch ($Operation) {
    'SetupMysteryumFirewall' {
        $pythonArgs += "--setup-mysterium-firewall"
    }
    'AddFirewallRule' {
        if ($Port -eq 0) {
            Write-Error "Port is required for AddFirewallRule operation"
            exit 1
        }
        $pythonArgs += @("--add-firewall-rule", "--port", $Port.ToString(), "--protocol", $Protocol, "--direction", $Direction)
        if ($RuleName) {
            $pythonArgs += @("--rule-name", $RuleName)
        }
    }
    'RemoveFirewallRule' {
        if ($Port -eq 0) {
            Write-Error "Port is required for RemoveFirewallRule operation"
            exit 1
        }
        $pythonArgs += @("--remove-firewall-rule", "--port", $Port.ToString(), "--protocol", $Protocol)
        if ($RuleName) {
            $pythonArgs += @("--rule-name", $RuleName)
        }
    }
    'KillProcess' {
        if ($PID -eq 0) {
            Write-Error "PID is required for KillProcess operation"
            exit 1
        }
        $pythonArgs += @("--kill-process", "--pid", $PID.ToString(), "--force")
    }
}

# Execute Python module
Write-Host "Executing privileged operation: $Operation"
Write-Host "Command: $PythonInterpreter $($pythonArgs -join ' ')"

& $PythonInterpreter @pythonArgs

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Error "Privileged operation failed with exit code $exitCode"
}

exit $exitCode
