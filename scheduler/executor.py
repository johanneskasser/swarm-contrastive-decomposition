"""
Job Executor for HD-EMG Decomposition Scheduler

Handles job execution via subprocess with output capture and logging.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Any
import json

# Import status tracker
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.status_tracker import StatusTracker
from .job_manager import DEFAULT_ALGORITHM_PARAMS


class JobExecutor:
    """Executes decomposition jobs and manages logging."""

    def __init__(self):
        """Initialize JobExecutor."""
        pass

    def run_job_with_file_tracking(self, job: Dict, job_manager) -> Tuple[int, float, str]:
        """
        Execute a job processing files individually with tracking.

        Args:
            job: Job dictionary with input_path, output_path, etc.
            job_manager: JobManager instance for updating job status

        Returns:
            Tuple of (return_code, duration_seconds, log_file_path)
        """
        job_id = job['id']
        job_name = job['name']
        input_path = Path(job['input_path'])
        output_path = Path(job['output_path'])

        # Create output directory
        output_path.mkdir(parents=True, exist_ok=True)

        # Create log file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file_path = output_path / f"decomposition_{timestamp}.log"

        start_time = datetime.now()

        # Find all processable files
        sys.path.insert(0, str(Path.cwd()))
        from main import find_processable_files, process_single_file

        files = find_processable_files(input_path)
        if not files:
            error_msg = f"No processable .mat files found in {input_path}"
            with open(log_file_path, 'w', encoding='utf-8') as log_file:
                self._write_log_header(log_file, job, start_time)
                log_file.write(f"\n[ERROR] {error_msg}\n")
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                self._write_log_footer(log_file, end_time, duration, 1)
            return 1, duration, str(log_file_path)

        # Initialize status tracker
        status_tracker = StatusTracker(output_path, job_name=job_name)
        status_tracker.initialize(files)

        # Update job with file list and status file path
        job_manager.update_job_files(job_id, [str(f) for f in files])
        job_manager.update_job_status(job_id, 'running', status_file=str(status_tracker.get_status_file_path()))

        # Get algorithm parameters (use defaults if not set)
        algorithm_params = job.get('algorithm_params', DEFAULT_ALGORITHM_PARAMS.copy())

        # Open log file
        with open(log_file_path, 'w', encoding='utf-8') as log_file:
            # Write log header
            self._write_log_header(log_file, job, start_time)
            log_file.write(f"\nFound {len(files)} file(s) to process:\n")
            for f in files:
                log_file.write(f"  - {f.name}\n")
            log_file.write("\n" + "="*80 + "\n\n")
            log_file.flush()

            # Process each file individually
            all_success = True
            for idx, file_path in enumerate(files, 1):
                try:
                    print(f"\n{'='*80}")
                    print(f"[File {idx}/{len(files)}] Processing: {file_path.name}")
                    print('='*80)
                    log_file.write(f"\n{'='*80}\n")
                    log_file.write(f"[File {idx}/{len(files)}] Processing: {file_path.name}\n")
                    log_file.write('='*80 + "\n\n")
                    log_file.flush()

                    # Update current file in job
                    job_manager.set_current_file(job_id, str(file_path))

                    # Mark file as processing in status tracker
                    status_tracker.set_processing(file_path)

                    # Process the file
                    file_start = datetime.now()
                    result = process_single_file(file_path, output_path, algorithm_params=algorithm_params)
                    file_end = datetime.now()
                    file_duration = (file_end - file_start).total_seconds()

                    # Log result
                    if result['success']:
                        status_msg = f"[OK] Successfully processed {file_path.name} ({self._format_duration(file_duration)})"
                        print(status_msg)
                        log_file.write(f"\n{status_msg}\n")
                        log_file.write(f"Grids processed: {len(result['grids_processed'])}\n")
                        for grid in result['grids_processed']:
                            log_file.write(f"  - {grid['grid_key']}: {grid['output_file']}\n")

                        # Update status tracker with success
                        output_count = len(result['grids_processed'])
                        status_tracker.set_done(file_path, output_count)
                    else:
                        status_msg = f"[ERROR] Failed to process {file_path.name}: {result.get('error', 'Unknown error')}"
                        print(status_msg)
                        log_file.write(f"\n{status_msg}\n")
                        all_success = False

                        # Update status tracker with failure
                        status_tracker.set_failed(file_path, result.get('error', 'Unknown error'))

                    log_file.write("\n")
                    log_file.flush()

                    # Add result to job
                    job_manager.add_processed_file(job_id, result)

                except KeyboardInterrupt:
                    print("\n\nJob interrupted by user (Ctrl+C)")
                    log_file.write("\n\n[JOB INTERRUPTED BY USER]\n")
                    status_tracker.set_failed(file_path, "Job interrupted by user")
                    all_success = False
                    break

                except Exception as e:
                    error_msg = f"\n[ERROR] Unexpected error processing {file_path.name}: {str(e)}\n"
                    print(error_msg)
                    log_file.write(error_msg)

                    import traceback
                    traceback_str = traceback.format_exc()
                    log_file.write(f"\n{traceback_str}\n")
                    log_file.flush()

                    # Update status tracker with failure
                    status_tracker.set_failed(file_path, str(e))

                    # Record failed file
                    result = {
                        'success': False,
                        'file_path': str(file_path),
                        'grids_processed': [],
                        'error': str(e)
                    }
                    job_manager.add_processed_file(job_id, result)
                    all_success = False
                    # IMPORTANT: Continue to next file instead of breaking

            # Calculate duration
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Write summary
            job_data = job_manager.get_job(job_id)
            successful = job_data.get('successful_files', 0)
            failed = job_data.get('failed_files', 0)
            total = job_data.get('total_files', 0)

            summary = f"\n{'='*80}\nPROCESSING SUMMARY\n{'='*80}\n"
            summary += f"Total files: {total}\n"
            summary += f"Successful: {successful}\n"
            summary += f"Failed: {failed}\n"
            summary += f"Status file: {status_tracker.get_status_file_path()}\n"
            summary += f"{'='*80}\n"
            print(summary)
            log_file.write(summary)
            log_file.flush()

            # Determine return code
            return_code = 0 if all_success and failed == 0 else 1

            # Write log footer
            self._write_log_footer(log_file, end_time, duration, return_code)

        return return_code, duration, str(log_file_path)

    def run_job_background(self, job: Dict) -> Tuple[int, str, str]:
        """
        Execute a job in the background (detached from this process).

        Args:
            job: Job dictionary with input_path, output_path, etc.

        Returns:
            Tuple of (pid, log_file_path, status_file_path)
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

        # Initialize status tracker and create status file
        status_tracker = StatusTracker(output_dir, job_name=job_name)

        # Find all processable files
        sys.path.insert(0, str(Path.cwd()))
        from main import find_processable_files
        input_path_obj = Path(input_path)
        files = find_processable_files(input_path_obj)

        # Initialize status file with file list
        if files:
            status_tracker.initialize(files)

        status_file_path = str(status_tracker.get_status_file_path())

        # Get algorithm parameters (use defaults if not set)
        algorithm_params = job.get('algorithm_params', DEFAULT_ALGORITHM_PARAMS.copy())

        # Save algorithm parameters to JSON file
        params_file_path = output_dir / f"algorithm_params_{timestamp}.json"
        with open(params_file_path, 'w', encoding='utf-8') as f:
            json.dump(algorithm_params, f, indent=2)

        # Write initial log header
        with open(log_file_path, 'w', encoding='utf-8') as log_file:
            self._write_log_header(log_file, job, start_time)

        # Determine python executable
        python_exe = 'python3' if sys.platform != 'win32' else sys.executable

        # Prepare command (with -u for unbuffered output for real-time logging)
        # Pass status file path and params file to main.py
        cmd = [python_exe, '-u', 'main.py', '-i', input_path, '-o', output_path,
               '--status-file', status_file_path, '--params-file', str(params_file_path)]

        # Start process in background (detached)
        # Platform-specific detachment
        if sys.platform == 'win32':
            # Windows: Use CREATE_NEW_PROCESS_GROUP without DETACHED_PROCESS
            # DETACHED_PROCESS can cause lower priority - we want full performance
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            CREATE_NO_WINDOW = 0x08000000

            process = subprocess.Popen(
                cmd,
                stdout=open(log_file_path, 'a', encoding='utf-8'),
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=Path.cwd(),
                creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
                close_fds=True
            )
        else:
            # Unix/Linux/Mac: Use start_new_session with nice level 0 (normal priority)
            process = subprocess.Popen(
                cmd,
                stdout=open(log_file_path, 'a', encoding='utf-8'),
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=Path.cwd(),
                start_new_session=True,
                close_fds=True
            )

        pid = process.pid

        # Set process priority to NORMAL/HIGH for full performance
        try:
            import psutil
            proc = psutil.Process(pid)

            if sys.platform == 'win32':
                # Windows: Set to ABOVE_NORMAL or HIGH priority
                proc.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)  # Higher than normal
            else:
                # Unix/Linux: Set nice value to 0 (normal) or negative (higher priority)
                proc.nice(0)  # Normal priority
        except:
            pass  # If psutil not available or permission denied, continue anyway

        return pid, str(log_file_path), status_file_path

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
                    [python_exe, '-u', 'main.py', '-i', input_path, '-o', output_path],
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
        # Get algorithm parameters
        params = job.get('algorithm_params', DEFAULT_ALGORITHM_PARAMS.copy())

        header = f"""{'='*80}
JOB: {job['name']} ({job['id']})
Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}
Input Path:  {job['input_path']}
Output Path: {job['output_path']}
Command: python3 -u main.py -i {job['input_path']} -o {job['output_path']}
{'='*80}

ALGORITHM PARAMETERS:
{'-'*80}
  acceptance_silhouette:    {params.get('acceptance_silhouette', 0.88)}
  max_iterations:           {params.get('max_iterations', 250)}
  sampling_frequency:       {params.get('sampling_frequency', 2000)}
  remove_bad_fr:            {params.get('remove_bad_fr', True)}
  low_pass_cutoff:          {params.get('low_pass_cutoff', 500)}
  high_pass_cutoff:         {params.get('high_pass_cutoff', 10)}
  extension_factor:         {params.get('extension_factor', 20)}
  peel_off_window_size_ms:  {params.get('peel_off_window_size_ms', 50)}
  notch_params:             {params.get('notch_params', [50, 1.0, True])}
  time_differentiate:       {params.get('time_differentiate', False)}
  use_coeff_var_fitness:    {params.get('use_coeff_var_fitness', True)}
  clamp_percentile:         {params.get('clamp_percentile', 0.999)}
  output_final_source_plot: {params.get('output_final_source_plot', False)}
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
