"""
Job Executor for HD-EMG Decomposition Scheduler

Handles job execution via subprocess with output capture and logging.
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple


class JobExecutor:
    """Executes decomposition jobs and manages logging."""

    def __init__(self):
        """Initialize JobExecutor."""
        pass

    def run_job(self, job: Dict) -> Tuple[int, float, str]:
        """
        Execute a single decomposition job.

        Args:
            job: Job dictionary with input_path, output_path, etc.

        Returns:
            Tuple of (return_code, duration_seconds, log_file_path)
        """
        job_id = job['id']
        job_name = job['name']
        input_path = job['input_path']
        output_path = job['output_path']

        # Create output directory
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create log file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file_path = output_dir / f"decomposition_{timestamp}.log"

        start_time = datetime.now()

        # Open log file
        with open(log_file_path, 'w', encoding='utf-8') as log_file:
            # Write log header
            self._write_log_header(log_file, job, start_time)

            # Execute main.py via subprocess
            try:
                # Determine python executable (python3 on Linux, python on Windows)
                python_exe = 'python3' if sys.platform != 'win32' else sys.executable

                process = subprocess.Popen(
                    [python_exe, 'main.py', '-i', input_path, '-o', output_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # Combine stderr with stdout
                    text=True,
                    bufsize=1,  # Line-buffered
                    cwd=Path.cwd()  # Ensure we're in the right directory
                )

                # Stream output to both console and log file
                for line in process.stdout:
                    print(line.rstrip())       # Console
                    log_file.write(line)       # File
                    log_file.flush()           # Flush immediately

                # Wait for process to complete
                return_code = process.wait()

            except KeyboardInterrupt:
                # Handle Ctrl+C gracefully
                print("\n\nJob interrupted by user (Ctrl+C)")
                log_file.write("\n\n[JOB INTERRUPTED BY USER]\n")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                return_code = -1

            except Exception as e:
                # Handle other errors
                error_msg = f"\n\nError executing job: {str(e)}\n"
                print(error_msg)
                log_file.write(error_msg)
                return_code = 1

            # Calculate duration
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Write log footer
            self._write_log_footer(log_file, end_time, duration, return_code)

        return return_code, duration, str(log_file_path)

    def _write_log_header(self, log_file, job: Dict, start_time: datetime):
        """
        Write header section to log file.

        Args:
            log_file: Open file handle
            job: Job dictionary
            start_time: Job start timestamp
        """
        header = f"""{'='*80}
JOB: {job['name']} ({job['id']})
Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}
Input Path:  {job['input_path']}
Output Path: {job['output_path']}
Command: python3 main.py -i {job['input_path']} -o {job['output_path']}
{'='*80}

"""
        log_file.write(header)
        log_file.flush()

    def _write_log_footer(self, log_file, end_time: datetime,
                         duration_seconds: float, return_code: int):
        """
        Write footer section to log file.

        Args:
            log_file: Open file handle
            end_time: Job end timestamp
            duration_seconds: Total duration in seconds
            return_code: Process return code
        """
        # Format duration nicely
        duration_str = self._format_duration(duration_seconds)

        # Determine status
        if return_code == 0:
            status = "SUCCESS"
        elif return_code == -1:
            status = "INTERRUPTED"
        else:
            status = f"FAILED (exit code: {return_code})"

        footer = f"""
{'='*80}
Completed: {end_time.strftime('%Y-%m-%d %H:%M:%S')}
Duration: {duration_str}
Status: {status}
{'='*80}
"""
        log_file.write(footer)
        log_file.flush()

    def _format_duration(self, seconds: float) -> str:
        """
        Format duration in seconds to human-readable string.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string (e.g., "1h 23m 45s")
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s ({int(seconds)} seconds)"
        elif minutes > 0:
            return f"{minutes}m {secs}s ({int(seconds)} seconds)"
        else:
            return f"{secs}s ({int(seconds)} seconds)"
