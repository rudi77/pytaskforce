# Ralph Loop Orchestrator
# PowerShell script that manages the agent's execution loop and git history
# Provides persistence and "fresh start" logic that defines the Ralph technique

# ============================================================================
# CONFIGURATION
# ============================================================================

# Maximum number of iterations before giving up
$max_iterations = 20

# Path to prd.json (default: current directory)
$prd_path = "prd.json"

# Profile to use for taskforce (default: ralph_plugin)
$taskforceProfile = "ralph_plugin"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN" { "Yellow" }
        "SUCCESS" { "Green" }
        default { "White" }
    }
    Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $color
}

function Test-Environment {
    # Check if taskforce is in PATH
    $taskforceCmd = Get-Command taskforce -ErrorAction SilentlyContinue
    if (-not $taskforceCmd) {
        Write-Log "ERROR: 'taskforce' command not found in PATH. Please ensure taskforce is installed and available." "ERROR"
        return $false
    }
    Write-Log "Found taskforce at: $($taskforceCmd.Source)" "SUCCESS"

    # Check if git is initialized
    git rev-parse --git-dir 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ERROR: Git repository not initialized. Please run 'git init' first." "ERROR"
        return $false
    }
    Write-Log "Git repository initialized" "SUCCESS"

    return $true
}

function Invoke-TaskforceCommand {
    param(
        [string]$Command,
        [string[]]$Arguments = @(),
        [switch]$JsonOutput
    )

    $cmdArgs = @("run", "command", $Command) + $Arguments
    if ($JsonOutput) {
        $cmdArgs += "--output-format", "json"
    }
    if ($taskforceProfile) {
        $cmdArgs += "--profile", $taskforceProfile
    }

    Write-Log "Executing: taskforce $($cmdArgs -join ' ')" "INFO"

    try {
        $output = & taskforce $cmdArgs 2>&1
        $exitCode = $LASTEXITCODE

        if ($exitCode -ne 0) {
            Write-Log "Taskforce command failed with exit code $exitCode" "ERROR"
            Write-Log "Output: $output" "ERROR"
            return @{
                Success = $false
                ExitCode = $exitCode
                Output = $output
            }
        }

        if ($JsonOutput) {
            try {
                # Try to extract JSON from output (might have other text before/after)
                $jsonText = $output
                # If output is an array, take the last element (most recent JSON)
                if ($output -is [array]) {
                    $jsonText = $output[-1]
                }
                # Try to find JSON object in output string if it's mixed with other text
                if ($jsonText -match '\{.*\}') {
                    $jsonText = $matches[0]
                }
                
                $jsonResult = $jsonText | ConvertFrom-Json
                return @{
                    Success = $true
                    ExitCode = 0
                    Output = $output
                    Json = $jsonResult
                }
            }
            catch {
                Write-Log "Failed to parse JSON output: $_" "ERROR"
                Write-Log "Raw output: $output" "ERROR"
                return @{
                    Success = $false
                    ExitCode = 0
                    Output = $output
                    ParseError = $_.Exception.Message
                }
            }
        }
        else {
            return @{
                Success = $true
                ExitCode = 0
                Output = $output
            }
        }
    }
    catch {
        Write-Log "Exception executing taskforce command: $_" "ERROR"
        return @{
            Success = $false
            ExitCode = -1
            Output = $_.Exception.Message
        }
    }
}

function Test-AllPRDTasksComplete {
    param([string]$PrdPath)

    if (-not (Test-Path $PrdPath)) {
        Write-Log "PRD file not found: $PrdPath" "WARN"
        return $false
    }

    try {
        $prdContent = Get-Content $PrdPath -Raw | ConvertFrom-Json
        $stories = $prdContent.stories

        if (-not $stories -or $stories.Count -eq 0) {
            Write-Log "No stories found in PRD" "WARN"
            return $false
        }

        $allComplete = $true
        foreach ($story in $stories) {
            if (-not $story.passes) {
                $allComplete = $false
                break
            }
        }

        if ($allComplete) {
            Write-Log "All PRD tasks are complete! ($($stories.Count) stories)" "SUCCESS"
        }
        else {
            $completed = ($stories | Where-Object { $_.passes -eq $true }).Count
            Write-Log "PRD progress: $completed/$($stories.Count) stories complete" "INFO"
        }

        return $allComplete
    }
    catch {
        Write-Log "Failed to read/parse PRD file: $_" "ERROR"
        return $false
    }
}

function Get-CurrentTaskTitle {
    param([string]$PrdPath)

    if (-not (Test-Path $PrdPath)) {
        return "Unknown Task"
    }

    try {
        $prdContent = Get-Content $PrdPath -Raw | ConvertFrom-Json
        $stories = $prdContent.stories

        # Find the last completed story (most recent)
        $completedStories = $stories | Where-Object { $_.passes -eq $true } | Sort-Object -Property id -Descending
        if ($completedStories.Count -gt 0) {
            return $completedStories[0].title
        }

        # Or find the current pending story
        $pendingStory = $stories | Where-Object { -not $_.passes } | Select-Object -First 1
        if ($pendingStory) {
            return $pendingStory.title
        }

        return "All Tasks Complete"
    }
    catch {
        return "Unknown Task"
    }
}

function Invoke-GitCommit {
    param(
        [int]$Iteration,
        [string]$TaskTitle
    )

    Write-Log "Staging all changes..." "INFO"
    git add . 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Warning: git add failed" "WARN"
        return $false
    }

    $commitMessage = "Ralph Loop: Iteration $Iteration - $TaskTitle"
    Write-Log "Committing: $commitMessage" "INFO"
    git commit -m $commitMessage 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        $gitHash = git rev-parse --short HEAD
        Write-Log "Committed successfully: $gitHash" "SUCCESS"
        return $true
    }
    else {
        # Check if there were no changes to commit
        $status = git status --porcelain
        if ([string]::IsNullOrWhiteSpace($status)) {
            Write-Log "No changes to commit" "INFO"
            return $true
        }
        Write-Log "Warning: git commit failed" "WARN"
        return $false
    }
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

Write-Log "========================================" "INFO"
Write-Log "Ralph Loop Orchestrator Starting" "INFO"
Write-Log "========================================" "INFO"

# Environment checks
if (-not (Test-Environment)) {
    Write-Log "Environment checks failed. Exiting." "ERROR"
    exit 1
}

# Initialize the workspace
# Check if prd.json already exists - if so, skip initialization
if (Test-Path $prd_path) {
    Write-Log "PRD file already exists: $prd_path. Skipping initialization." "INFO"
    Write-Log "If you want to reinitialize, delete the PRD file first." "INFO"
}
else {
    Write-Log "Initializing Ralph workspace..." "INFO"
    Write-Log "NOTE: ralph:init requires a task description as argument." "WARN"
    Write-Log "If initialization fails, run manually: taskforce run command ralph:init 'Your task description here'" "WARN"
    
    # Try to initialize - this will likely fail without arguments, but we try anyway
    # The user should run this manually with their task description
    $initResult = Invoke-TaskforceCommand -Command "ralph:init" -JsonOutput:$false

    if (-not $initResult.Success) {
        Write-Log "Failed to initialize Ralph workspace automatically." "ERROR"
        Write-Log "Please run manually with your task description:" "ERROR"
        Write-Log "  taskforce run command ralph:init 'Your task description here'" "ERROR"
        Write-Log "Then run this script again." "ERROR"
        exit 1
    }
    Write-Log "Workspace initialized successfully" "SUCCESS"
}

# Main loop
$iteration = 0
$lastFailedTask = $null
$sameTaskFailureCount = 0

while ($iteration -lt $max_iterations) {
    $iteration++
    Write-Log "========================================" "INFO"
    Write-Log "Iteration $iteration of $max_iterations" "INFO"
    Write-Log "========================================" "INFO"

    # Get current git hash for logging
    $currentGitHash = git rev-parse --short HEAD 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Log "Current git hash: $currentGitHash" "INFO"
    }

    # Get current task before execution for failure tracking
    $currentTask = Get-CurrentTaskTitle -PrdPath $prd_path

    # Execute ralph:step
    $stepResult = Invoke-TaskforceCommand -Command "ralph:step" -JsonOutput:$true

    if (-not $stepResult.Success) {
        # Track same-task failures
        if ($currentTask -eq $lastFailedTask) {
            $sameTaskFailureCount++
        }
        else {
            # Different task failed, reset same-task counter and track new task
            $sameTaskFailureCount = 1
            $lastFailedTask = $currentTask
        }

        Write-Log "Step execution failed (same task failures: $sameTaskFailureCount for task: $currentTask)" "ERROR"

        # Exit if same task failed 3 times consecutively
        if ($sameTaskFailureCount -ge 3) {
            Write-Log "Same task failed 3 times consecutively: $currentTask. Exiting loop." "ERROR"
            exit 1
        }

        Write-Log "Pausing before retry..." "WARN"
        Start-Sleep -Seconds 2
        continue
    }

    # Check execution status from JSON
    if (-not $stepResult.Json) {
        Write-Log "ERROR: JSON output expected but parsing failed. Cannot determine status." "ERROR"
        Write-Log "This is a critical error - JSON output is required for loop control." "ERROR"
        Write-Log "Pausing before retry..." "WARN"
        Start-Sleep -Seconds 2
        continue
    }

    $status = $stepResult.Json.status
    Write-Log "Execution status: $status" "INFO"

    if ($status -eq "completed") {
        Write-Log "Iteration completed successfully" "SUCCESS"

        # Reset failure counters on success
        $sameTaskFailureCount = 0
        $lastFailedTask = $null

        # Get current task title for commit message
        $taskTitle = Get-CurrentTaskTitle -PrdPath $prd_path
        Write-Log "Current task: $taskTitle" "INFO"

        # Commit to git
        $commitSuccess = Invoke-GitCommit -Iteration $iteration -TaskTitle $taskTitle
        if (-not $commitSuccess) {
            Write-Log "Warning: Git commit had issues, but continuing..." "WARN"
        }

        # Check if all PRD tasks are complete
        if (Test-AllPRDTasksComplete -PrdPath $prd_path) {
            Write-Log "========================================" "SUCCESS"
            Write-Log "ALL PRD TASKS COMPLETE!" "SUCCESS"
            Write-Log "Ralph Loop finished successfully after $iteration iterations" "SUCCESS"
            Write-Log "========================================" "SUCCESS"
            exit 0
        }
    }
    elseif ($status -eq "failed") {
        Write-Log "Iteration failed with status: failed" "ERROR"
        # Track same-task failures for status "failed"
        if ($currentTask -eq $lastFailedTask) {
            $sameTaskFailureCount++
        }
        else {
            $sameTaskFailureCount = 1
            $lastFailedTask = $currentTask
        }

        Write-Log "Step execution failed (same task failures: $sameTaskFailureCount for task: $currentTask)" "ERROR"

        # Exit if same task failed 3 times consecutively
        if ($sameTaskFailureCount -ge 3) {
            Write-Log "Same task failed 3 times consecutively: $currentTask. Exiting loop." "ERROR"
            exit 1
        }

        Write-Log "Pausing before retry..." "WARN"
        Start-Sleep -Seconds 2
        continue
    }
    else {
        Write-Log "Iteration status: $status (continuing...)" "INFO"
        # Reset failure counters for non-failed statuses
        $sameTaskFailureCount = 0
        $lastFailedTask = $null
    }

    # Brief pause between iterations
    Start-Sleep -Seconds 1
}

# Max iterations reached
Write-Log "========================================" "WARN"
Write-Log "Maximum iterations ($max_iterations) reached" "WARN"
Write-Log "Exiting loop." "WARN"
Write-Log "========================================" "WARN"

# Final status check
if (Test-AllPRDTasksComplete -PrdPath $prd_path) {
    Write-Log "All PRD tasks are complete despite reaching max iterations" "SUCCESS"
    exit 0
}
else {
    Write-Log "Not all PRD tasks are complete" "WARN"
    exit 1
}
