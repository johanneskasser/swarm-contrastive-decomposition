#!/usr/bin/env python3
"""
Background Job Orchestrator for Sequential Execution

This script runs independently from the scheduler and manages
sequential job execution in the background. It monitors jobs
and starts them one at a time, even if the scheduler is closed.

Author: Johannes Kasser with the assistance of Claude Code
"""

import subprocess
import sys
import time
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scheduler.job_manager import JobManager
from scheduler.executor import JobExecutor


def log_message(message):
    """Log a message with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")
    sys.stdout.flush()


def run_orchestrator(job_ids):
    """
    Run jobs sequentially in the background.

    Args:
        job_ids: List of job IDs to execute sequentially
    """
    log_message(f"Orchestrator started with {len(job_ids)} job(s)")

    job_manager = JobManager()
    executor = JobExecutor()

    for idx, job_id in enumerate(job_ids, 1):
        log_message(f"Processing job {idx}/{len(job_ids)} (ID: {job_id})")

        # Load current job data
        jobs = job_manager.load_jobs()
        job = next((j for j in jobs if j['id'] == job_id), None)

        if job is None:
            log_message(f"ERROR: Job {job_id} not found, skipping")
            continue

        # Check if job is still pending
        if job['status'] != 'pending':
            log_message(f"Job {job['name']} is {job['status']}, skipping")
            continue

        log_message(f"Starting job: {job['name']}")
        start_time = datetime.now()

        # Update status to running
        job_manager.update_job_status(
            job_id,
            'running',
            started_at=start_time.isoformat()
        )

        # Execute job in background
        try:
            pid, log_file, status_file = executor.run_job_background(job)
            log_message(f"Job started with PID: {pid}")
            log_message(f"Log file: {log_file}")
            log_message(f"Status file: {status_file}")

            # Update job with PID, log file, and status file
            job_manager.update_job_status(
                job_id,
                'running',
                pid=pid,
                log_file=log_file,
                status_file=status_file
            )

            # Wait for job to complete
            log_message(f"Waiting for job to complete...")

            # Initialize exit_code outside try block for proper scope
            exit_code = None

            try:
                import psutil
                process = psutil.Process(pid)

                # Poll until process completes
                check_interval = 10  # Check every 10 seconds
                while True:
                    try:
                        # Check if process is a zombie or terminated
                        status = process.status()
                        if status == psutil.STATUS_ZOMBIE:
                            log_message(f"Job completed (PID {pid} is zombie, waiting for exit code)")
                            # Wait for the process to be fully reaped and capture exit code
                            exit_code = process.wait(timeout=5)
                            break

                        if not process.is_running():
                            log_message(f"Job completed (PID {pid} terminated)")
                            break

                        time.sleep(check_interval)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        log_message(f"Job completed (PID {pid} no longer accessible)")
                        break
                    except psutil.TimeoutExpired:
                        log_message(f"Job completed (PID {pid} zombie cleanup timeout)")
                        break

            except ImportError:
                log_message("WARNING: psutil not available, cannot monitor job. Assuming success after 5 seconds.")
                time.sleep(5)

            # Determine final status from process exit code and log file
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Try to get exit code from process (may have been captured above)
            return_code = exit_code
            if return_code is None:
                try:
                    import psutil
                    proc = psutil.Process(pid)
                    return_code = proc.wait(timeout=1)
                except:
                    pass

            # If we couldn't get exit code from process, check log file
            if return_code is None and log_file and Path(log_file).exists():
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if 'Status: SUCCESS' in content:
                            return_code = 0
                        elif 'Traceback' in content or 'Error' in content:
                            return_code = 1
                except:
                    pass

            # Determine final status
            if return_code == 0:
                final_status = 'completed'
            elif return_code is not None:
                final_status = 'failed'
            else:
                # Couldn't determine exit code, assume success
                final_status = 'completed'

            # Update job status
            job_manager.update_job_status(
                job_id,
                final_status,
                completed_at=end_time.isoformat(),
                duration_seconds=duration,
                return_code=return_code,
                pid=None
            )

            log_message(f"Job {job['name']} finished with status: {final_status}")

        except Exception as e:
            log_message(f"ERROR executing job: {str(e)}")
            job_manager.update_job_status(
                job_id,
                'failed',
                completed_at=datetime.now().isoformat()
            )

    log_message(f"Orchestrator finished. All {len(job_ids)} job(s) processed.")

    # Execute completion hook if configured
    completion_hook = job_manager.get_completion_hook()
    if completion_hook:
        log_message(f"Executing completion hook: {completion_hook}")
        try:
            import subprocess
            result = subprocess.run(
                completion_hook,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            log_message(f"Hook completed with exit code: {result.returncode}")
            if result.stdout:
                log_message(f"Hook output: {result.stdout.strip()}")
            if result.stderr:
                log_message(f"Hook errors: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            log_message("ERROR: Completion hook timed out (60 seconds)")
        except Exception as e:
            log_message(f"ERROR executing completion hook: {str(e)}")
    else:
        log_message("No completion hook configured.")

    # Send Discord notification if a webhook URL is configured
    discord_url = job_manager.get_discord_webhook()
    if discord_url:
        log_message("Sending Discord notification...")
        notifier = Path(__file__).parent.parent / 'utils' / 'discord_notifier.py'
        try:
            result = subprocess.run(
                [sys.executable, str(notifier), '--job-ids'] + job_ids
                + ['--webhook-url', discord_url],
                timeout=30,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                log_message("Discord notification sent.")
            else:
                log_message(f"Discord notifier exited with code {result.returncode}: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            log_message("Discord notification timed out (30 s).")
        except Exception as e:
            log_message(f"Discord notification error: {e}")
    else:
        log_message("No Discord webhook configured.")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python orchestrator.py <job_id1> <job_id2> ...")
        sys.exit(1)

    job_ids = sys.argv[1:]

    try:
        run_orchestrator(job_ids)
    except Exception as e:
        log_message(f"FATAL ERROR: {str(e)}")
        sys.exit(1)
