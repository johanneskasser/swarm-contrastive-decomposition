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
Job Name: Vastus_Lateralis_Before
Input Path: /mnt/data/Dateien/hdsemg/decomp/hp/before/
Output Path: /mnt/data/Dateien/hdsemg/decomp/hp/before/out
Description (optional): Pre-treatment dataset
```

### 4. Run Jobs

- Select option `4` to run all pending jobs sequentially
- Or select option `5` to run a single specific job

The scheduler will:
- Create output directories automatically
- Show real-time output from the decomposition process
- Save complete logs to `{output_path}/decomposition_{timestamp}.log`
- Update job status automatically

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

## Job Status Values

- **⏸ Pending**: Job is queued but not yet started
- **▶ Running**: Job is currently executing
- **✓ Completed**: Job finished successfully (exit code 0)
- **✗ Failed**: Job failed or was interrupted

## Error Handling

- If a job fails, the scheduler logs the error and **continues with the next job**
- Logs are saved even for failed jobs
- Use option `7` (View job log) to see detailed error messages
- Ctrl+C during execution will gracefully stop the current job and mark it as failed

## Tips

1. **Batch Processing**: Add multiple jobs, then use option `4` to run them all overnight
2. **Monitor Progress**: Logs are written in real-time - you can tail them while jobs run
3. **Clean Up**: Use option `8` to remove completed/failed jobs from the list
4. **Check Logs**: Use option `7` to view the last 50 lines of a log file quickly

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

### "No module named 'scheduler'"
Make sure you're running `python scheduler.py` from the project root directory.

### "Input path does not exist"
Verify the input path is correct and contains .mat files.

### Jobs stuck in "running" status
If the scheduler crashed, manually edit `jobs_config.json` and change the status to "failed" or "pending".

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
