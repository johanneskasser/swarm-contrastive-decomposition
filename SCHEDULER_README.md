# HD-EMG Decomposition Scheduler

Interactive CLI tool for scheduling and running multiple HD-EMG decomposition jobs sequentially.

## Features

- ✅ Interactive menu-driven interface
- ✅ Add/remove/view jobs easily
- ✅ Run all pending jobs or individual jobs
- ✅ Real-time output streaming to console
- ✅ Comprehensive logging with timestamps
- ✅ Automatic error handling (continues on failure)
- ✅ Job status tracking (pending/running/completed/failed)

## Installation

No additional installation needed - the scheduler uses only Python standard library plus the existing project dependencies.

### Required: Process Tracking

For background job tracking, install `psutil`:

```bash
pip install psutil
```

This enables:
- **Background job execution** - jobs continue running even if you close the scheduler
- **Automatic status updates** for running jobs
- **Process monitoring** and cleanup

### Optional: Path Auto-Completion (Windows)

For better path auto-completion on Windows, install `pyreadline3`:

```bash
pip install pyreadline3
```

This enables:
- **TAB completion** for filesystem paths
- **Arrow keys** for command history and editing (no more `^[[C` characters!)
- Better interactive experience

On Linux/Mac, path completion works out of the box.

### Quick Install (All Features)

```bash
pip install psutil pyreadline3
```

## Quick Start

### 1. Start the Scheduler

```bash
python scheduler.py
```

### 2. Interactive Menu

Once started, you'll see the main menu:

```
================================================================================
                    HD-EMG Decomposition Scheduler
================================================================================

  1. View all jobs
  2. Add new job
  3. Remove job
  4. Run all pending jobs
  5. Run single job
  6. View job details
  7. View job log
  8. Clear completed jobs
  9. Exit
```

### 3. Add Your First Job

1. Select option `2` (Add new job)
2. Enter:
   - **Job Name**: A descriptive name (e.g., "Vastus_Lateralis_Before")
   - **Input Path**: Full path to input directory containing .mat files
   - **Output Path**: Full path where results should be saved
   - **Description**: Optional description

Example:
```
💡 Tip: Use TAB for path auto-completion, arrow keys to navigate

Job Name: Vastus_Lateralis_Before
Input Path: /mnt/data/Dateien/hdsemg/decomp/hp/before/    [TAB to auto-complete]
Output Path: /mnt/data/Dateien/hdsemg/decomp/hp/before/out  [TAB to auto-complete]
Description (optional): Pre-treatment dataset
```

### 4. Run Jobs

- Select option `4` to run all pending jobs sequentially
- Or select option `5` to run a single specific job

**Important**: Jobs run in the **background**! This means:
- ✅ Jobs continue running even if you close the scheduler
- ✅ You can start multiple jobs and close the terminal
- ✅ Re-open the scheduler anytime to check status
- ✅ No need to keep the scheduler window open

The scheduler will:
- Create output directories automatically
- Start jobs as background processes
- Save complete logs to `{output_path}/decomposition_{timestamp}.log`
- Update job status automatically when you reopen the scheduler

## Job Configuration File

Jobs are stored in `jobs_config.json` in the project root. This file is auto-generated and can also be edited manually if needed.

### Example jobs_config.json

```json
{
  "version": "1.0",
  "jobs": [
    {
      "id": "job_20251201_104523",
      "name": "Dataset_A",
      "input_path": "/mnt/data/Dateien/hdsemg/decomp/hp/before/",
      "output_path": "/mnt/data/Dateien/hdsemg/decomp/hp/before/out",
      "description": "Pre-treatment dataset",
      "status": "pending",
      "created_at": "2025-12-01T10:45:23",
      "started_at": null,
      "completed_at": null,
      "duration_seconds": null,
      "return_code": null,
      "log_file": null
    }
  ]
}
```

## Log Files

Each job execution creates a detailed log file in the output directory:

**Location**: `{output_path}/decomposition_{timestamp}.log`

**Contents**:
- Job metadata (name, ID, paths, command)
- Start time
- Complete console output from main.py
- End time, duration, status
- Return code

### Example Log

```
================================================================================
JOB: Dataset_A (job_20251201_104523)
Started: 2025-12-01 10:45:23
Input Path:  /mnt/data/Dateien/hdsemg/decomp/hp/before/
Output Path: /mnt/data/Dateien/hdsemg/decomp/hp/before/out
Command: python3 main.py -i /mnt/data/... -o /mnt/data/.../out
================================================================================

[Full console output here...]

================================================================================
Completed: 2025-12-01 11:23:45
Duration: 38m 22s (2302 seconds)
Status: SUCCESS
================================================================================
```

## Background Job Management

### How Background Jobs Work

When you start a job, it runs as a **detached background process**:
- The process continues even after closing the scheduler
- Process ID (PID) is tracked in the job configuration
- Logs are written in real-time to the output directory

### Checking Running Jobs

When you start the scheduler:
1. It automatically checks all "running" jobs
2. Updates their status if they've completed
3. Shows a notification if background jobs are found

```
================================================================================
BACKGROUND JOBS DETECTED
================================================================================

Found 2 job(s) running in the background:
  - Vastus_Lateralis_Before (PID: 12345)
  - Tibialis_Anterior_After (PID: 12346)

These jobs will continue running even if you close the scheduler.
Use option 1 to view their current status.
```

### Monitoring Background Jobs

**Option 1: Check status in scheduler**
- View all jobs (option 1) to see current status
- View job details (option 6) to see PID and log file location
- The scheduler automatically updates status on each menu display

**Option 2: Monitor log files directly**
```bash
# Watch live progress
tail -f /path/to/output/decomposition_*.log

# Or on Windows
Get-Content /path/to/output/decomposition_*.log -Wait
```

**Option 3: Check process directly**
```bash
# Linux/Mac
ps aux | grep "main.py"

# Windows
tasklist | findstr python
```

## Job Status Values

- **⏸ Pending**: Job is queued but not yet started
- **▶ Running**: Job is currently executing in the background
- **✓ Completed**: Job finished successfully (exit code 0)
- **✗ Failed**: Job failed or was interrupted

## Error Handling

- If a job fails, the scheduler logs the error and **continues with the next job**
- Logs are saved even for failed jobs
- Use option `7` (View job log) to see detailed error messages
- Ctrl+C during execution will gracefully stop the current job and mark it as failed

## Tips

1. **Path Auto-Completion**:
   - Press **TAB** while typing paths to auto-complete directories and files
   - Use **arrow keys** to navigate through completion options
   - Supports `~` for home directory (e.g., `~/Documents/data/`)
   - Install `pyreadline3` on Windows for best experience

2. **Batch Processing & Go**: Add multiple jobs, start them all (option `4`), then close the scheduler
   - Jobs will continue running in the background
   - Come back later to check results
   - Perfect for overnight processing

3. **Monitor Progress**: Logs are written in real-time - you can tail them while jobs run
   ```bash
   # In another terminal, monitor live progress:
   tail -f /path/to/output/decomposition_*.log
   ```

4. **Clean Up**: Use option `8` to remove completed/failed jobs from the list

5. **Check Logs**: Use option `7` to view the last 50 lines of a log file quickly

6. **Safety**: Jobs are isolated - crashing one job won't affect others

## File Structure

```
swarm-contrastive-decomposition/
├── scheduler.py              # Entry point - run this
├── scheduler/
│   ├── __init__.py
│   ├── job_manager.py       # Job CRUD operations
│   ├── executor.py          # Job execution & logging
│   └── ui.py                # Interactive menu
├── jobs_config.json         # Auto-generated job list
└── main.py                  # Called by scheduler for each job
```

## Troubleshooting

### Arrow keys showing `^[[C` or `^[[D` characters
This means readline is not available or not working properly.

**Solution for Windows:**
```bash
pip install pyreadline3
```

**Solution for Linux/Mac:**
Readline should be built-in. If not working, try:
```bash
pip install gnureadline  # Mac only
```

### Tab completion not working
Install `pyreadline3` (Windows) or verify readline is available:
```python
python -c "import readline; print('readline OK')"
```

### "No module named 'scheduler'"
Make sure you're running `python scheduler.py` from the project root directory.

### "Input path does not exist"
Verify the input path is correct and contains .mat files.

### Jobs stuck in "running" status
This can happen if:
1. The background process crashed without updating the log
2. The system was rebooted
3. The process was manually killed

**Solution**:
- Restart the scheduler - it will auto-detect that the process is dead and update status
- Or manually edit `jobs_config.json` and change the status to "failed" or "pending"

### Cannot track background jobs / "psutil not installed"
Install psutil for background job tracking:
```bash
pip install psutil
```

Without psutil, jobs can still run but:
- Won't be tracked across scheduler restarts
- Status won't auto-update
- Can't detect if background process crashed

### Background job not appearing after restart
Check if:
1. `psutil` is installed (`pip install psutil`)
2. Job status in `jobs_config.json` is "running"
3. PID is recorded in the job configuration

### Want to stop a running background job
**Option 1: Kill via scheduler** (future feature - not implemented yet)

**Option 2: Kill manually**
```bash
# Linux/Mac
kill <PID>

# Windows
taskkill /PID <PID> /F
```

Then restart scheduler to update status.

## Advanced Usage

### Manual JSON Editing

You can manually edit `jobs_config.json` to:
- Add multiple jobs at once
- Modify job parameters
- Reset job status

Just ensure the JSON syntax is valid.

### Backup Configuration

Before major changes, backup your job configuration:
```bash
cp jobs_config.json jobs_config.backup.json
```

## Support

For issues or questions:
1. Check the log files in the output directories
2. Ensure your input paths contain valid .mat files
3. Verify you're using the correct Python environment (conda activate decomposition)
