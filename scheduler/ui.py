"""
Interactive UI for HD-EMG Decomposition Scheduler

Provides menu-driven interface for job management.
"""

import os
import glob
from datetime import datetime
from pathlib import Path
from typing import Optional

# Try to import readline for path completion (Unix/Linux/Mac)
# On Windows, this will work with pyreadline3 if installed
try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False
    print("Note: Install 'pyreadline3' for path auto-completion on Windows")

from .job_manager import JobManager
from .executor import JobExecutor


class SchedulerUI:
    """Interactive CLI for job scheduling."""

    def __init__(self):
        """Initialize SchedulerUI."""
        self.job_manager = JobManager()
        self.executor = JobExecutor()
        self._setup_readline()

        # Check for running background jobs on startup
        self._check_background_jobs_on_startup()

    def _check_background_jobs_on_startup(self):
        """Check for running background jobs when starting the scheduler."""
        try:
            # Update status of any background jobs
            self.job_manager.check_running_jobs()

            # Check if there are still running jobs
            running_jobs = self.job_manager.list_jobs(status='running')

            if running_jobs:
                print("\n" + "="*80)
                print("BACKGROUND JOBS DETECTED")
                print("="*80)
                print(f"\nFound {len(running_jobs)} job(s) running in the background:")
                for job in running_jobs:
                    print(f"  - {job['name']} (PID: {job.get('pid', 'unknown')})")
                print("\nThese jobs will continue running even if you close the scheduler.")
                print("Use option 1 to view their current status.")
                input("\nPress Enter to continue...")
        except ImportError:
            print("\nWarning: 'psutil' not installed. Cannot track background jobs.")
            print("Install with: pip install psutil")
            input("\nPress Enter to continue...")
        except Exception as e:
            print(f"\nWarning: Error checking background jobs: {e}")
            input("\nPress Enter to continue...")

    def main_loop(self):
        """Main interactive loop."""
        while True:
            # Update running job statuses before showing menu
            try:
                self.job_manager.check_running_jobs()
            except:
                pass  # Silently fail if psutil not available

            self._clear_screen()
            self._display_menu()

            choice = input("\nEnter choice (1-11): ").strip()

            if choice == '1':
                self._view_all_jobs()
            elif choice == '2':
                self._add_job_interactive()
            elif choice == '3':
                self._remove_job_interactive()
            elif choice == '4':
                self._run_all_pending_jobs()
            elif choice == '5':
                self._run_single_job()
            elif choice == '6':
                self._view_job_details()
            elif choice == '7':
                self._view_job_log()
            elif choice == '8':
                self._clear_completed_jobs()
            elif choice == '9':
                self._retry_failed_jobs()
            elif choice == '10':
                self._configure_completion_hook()
            elif choice == '11':
                print("\nExiting scheduler. Goodbye!")
                break
            else:
                print("\nInvalid choice. Please enter a number between 1 and 11.")
                self._pause()

    def _clear_screen(self):
        """Clear terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def _setup_readline(self):
        """Setup readline for path auto-completion."""
        if not READLINE_AVAILABLE:
            return

        # Set up tab completion for paths
        readline.set_completer_delims(' \t\n;')
        readline.parse_and_bind("tab: complete")

        # Platform-specific key bindings
        if os.name == 'nt':  # Windows
            readline.parse_and_bind("tab: complete")
        else:  # Unix/Linux/Mac
            readline.parse_and_bind("tab: complete")

    def _path_completer(self, text, state):
        """
        Path completion function for readline.

        Args:
            text: Current text to complete
            state: Iteration state

        Returns:
            Next completion match or None
        """
        # Expand user home directory
        if text.startswith('~'):
            text = os.path.expanduser(text)

        # If text is empty or just started, show current directory
        if not text:
            text = './'

        # Add trailing slash for directories
        if os.path.isdir(text) and not text.endswith(os.sep):
            text += os.sep

        # Get directory and prefix
        dirname = os.path.dirname(text) or '.'
        prefix = os.path.basename(text)

        # Find all matches
        try:
            matches = []
            for entry in os.listdir(dirname):
                if entry.startswith(prefix):
                    full_path = os.path.join(dirname, entry)
                    # Add trailing slash for directories
                    if os.path.isdir(full_path):
                        matches.append(full_path + os.sep)
                    else:
                        matches.append(full_path)

            # Return the match at the given state
            if state < len(matches):
                return matches[state]
            else:
                return None
        except (OSError, PermissionError):
            return None

    def _input_with_completion(self, prompt: str) -> str:
        """
        Input with path auto-completion enabled.

        Args:
            prompt: Input prompt text

        Returns:
            User input string
        """
        if READLINE_AVAILABLE:
            # Enable path completion
            readline.set_completer(self._path_completer)
            try:
                result = input(prompt)
            finally:
                # Disable completer after input
                readline.set_completer(None)
            return result
        else:
            # Fallback to regular input
            return input(prompt)

    def _display_menu(self):
        """Display main menu."""
        print("=" * 80)
        print(" " * 20 + "HD-EMG Decomposition Scheduler")
        print("=" * 80)
        print()
        print("  1. View all jobs")
        print("  2. Add new job")
        print("  3. Remove job")
        print("  4. Run all pending jobs")
        print("  5. Run single job")
        print("  6. View job details")
        print("  7. View job log")
        print("  8. Clear completed jobs")
        print("  9. Retry failed jobs")
        print(" 10. Configure completion hook")
        print(" 11. Exit")
        print()

    def _view_all_jobs(self):
        """Display all jobs in a formatted table."""
        jobs = self.job_manager.load_jobs()

        if not jobs:
            print("\nNo jobs found. Add a new job to get started!")
            self._pause()
            return

        print("\n" + "=" * 80)
        print("ALL JOBS")
        print("=" * 80)

        # Table header
        print(f"\n{'#':<4} {'Job Name':<25} {'Status':<12} {'Created':<20}")
        print("-" * 80)

        # Table rows
        for idx, job in enumerate(jobs, 1):
            status = self._format_status(job['status'])
            created = datetime.fromisoformat(job['created_at']).strftime('%Y-%m-%d %H:%M')
            name = job['name'][:24]  # Truncate if too long

            print(f"{idx:<4} {name:<25} {status:<12} {created:<20}")

        print()
        self._pause()

    def _add_job_interactive(self):
        """Interactive job creation."""
        print("\n" + "=" * 80)
        print("ADD NEW JOB")
        print("=" * 80)
        print()

        if READLINE_AVAILABLE:
            print("💡 Tip: Use TAB for path auto-completion, arrow keys to navigate")
            print()

        try:
            # Get job details from user
            name = input("Job Name: ").strip()
            if not name:
                print("\nError: Job name cannot be empty")
                self._pause()
                return

            input_path = self._input_with_completion("Input Path: ").strip()
            if not input_path:
                print("\nError: Input path cannot be empty")
                self._pause()
                return

            output_path = self._input_with_completion("Output Path: ").strip()
            if not output_path:
                print("\nError: Output path cannot be empty")
                self._pause()
                return

            description = input("Description (optional): ").strip()

            # Add job
            job = self.job_manager.add_job(name, input_path, output_path, description)

            print(f"\n✓ Job added successfully! (ID: {job['id']})")

        except ValueError as e:
            print(f"\nError: {str(e)}")
        except Exception as e:
            print(f"\nUnexpected error: {str(e)}")

        self._pause()

    def _remove_job_interactive(self):
        """Interactive job removal."""
        jobs = self.job_manager.load_jobs()

        if not jobs:
            print("\nNo jobs to remove.")
            self._pause()
            return

        # Show jobs with indices
        print("\n" + "=" * 80)
        print("REMOVE JOB")
        print("=" * 80)
        print()

        for idx, job in enumerate(jobs, 1):
            status = self._format_status(job['status'])
            print(f"  {idx}. {job['name']} ({status})")

        print()
        choice = input("Enter job number to remove (or 'c' to cancel): ").strip()

        if choice.lower() == 'c':
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(jobs):
                job = jobs[idx]
                confirm = input(f"\nAre you sure you want to remove '{job['name']}'? (y/n): ").strip().lower()

                if confirm == 'y':
                    self.job_manager.remove_job(job['id'])
                    print(f"\n✓ Job '{job['name']}' removed successfully.")
                else:
                    print("\nCancelled.")
            else:
                print("\nInvalid job number.")
        except ValueError:
            print("\nInvalid input.")

        self._pause()

    def _run_all_pending_jobs(self):
        """Run all pending jobs sequentially (one at a time, wait for completion)."""
        pending_jobs = self.job_manager.list_jobs(status='pending')

        if not pending_jobs:
            print("\nNo pending jobs to run.")
            self._pause()
            return

        print("\n" + "=" * 80)
        print("RUN ALL PENDING JOBS")
        print("=" * 80)
        print(f"\nFound {len(pending_jobs)} pending job(s):")
        for idx, job in enumerate(pending_jobs, 1):
            print(f"  {idx}. {job['name']}")

        # Ask for execution mode
        print("\nExecution mode:")
        print("  1. Sequential Foreground (wait for each job) - RECOMMENDED")
        print("  2. Sequential Background (jobs run one-by-one, can close scheduler)")
        print("  3. Parallel Background (all jobs start immediately)")
        mode = input("\nChoose mode (1/2/3) [1]: ").strip() or "1"

        if mode not in ['1', '2', '3']:
            print("\nInvalid choice. Cancelled.")
            self._pause()
            return

        confirm = input(f"\nStart execution? (y/n): ").strip().lower()
        if confirm != 'y':
            print("\nCancelled.")
            self._pause()
            return

        # Execute jobs based on mode
        total_jobs = len(pending_jobs)

        if mode == '1':
            # Mode 1: Sequential Foreground - wait for each job to finish
            for idx, job in enumerate(pending_jobs, 1):
                print("\n" + "=" * 80)
                print(f"[Job {idx}/{total_jobs}] {job['name']}")
                print("=" * 80)

                self._execute_job_foreground(job)

        elif mode == '2':
            # Mode 2: Sequential Background - use orchestrator to manage jobs
            print("\n💡 Sequential Background Mode:")
            print("   - Jobs will run one at a time in the background")
            print("   - You can close the scheduler and jobs will continue")
            print("   - A background orchestrator will manage sequential execution")
            print()

            # Start orchestrator in background with all job IDs
            self._start_orchestrator(pending_jobs)

        else:
            # Mode 3: Parallel Background - start all jobs immediately
            print("\n⚠ Parallel Background Mode:")
            print("   - All jobs will start immediately in parallel")
            print("   - May cause resource competition and slower performance")
            print("   - Jobs continue running if you close the scheduler")
            print()

            for idx, job in enumerate(pending_jobs, 1):
                print("\n" + "=" * 80)
                print(f"[Job {idx}/{total_jobs}] {job['name']}")
                print("=" * 80)

                self._execute_job(job)

        print("\n" + "=" * 80)
        if mode == '1':
            print("ALL JOBS COMPLETED")
        elif mode == '2':
            print("ALL JOBS STARTED SEQUENTIALLY")
        else:
            print("ALL JOBS STARTED IN PARALLEL")
        print("=" * 80)
        self._pause()

    def _run_single_job(self):
        """Run a single selected job."""
        jobs = self.job_manager.load_jobs()

        if not jobs:
            print("\nNo jobs available to run.")
            self._pause()
            return

        # Show jobs with indices
        print("\n" + "=" * 80)
        print("RUN SINGLE JOB")
        print("=" * 80)
        print()

        for idx, job in enumerate(jobs, 1):
            status = self._format_status(job['status'])
            print(f"  {idx}. {job['name']} ({status})")

        print()
        choice = input("Enter job number to run (or 'c' to cancel): ").strip()

        if choice.lower() == 'c':
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(jobs):
                job = jobs[idx]

                # Ask for execution mode
                print("\nExecution mode:")
                print("  1. Foreground (wait for completion) - RECOMMENDED")
                print("  2. Background (continue immediately)")
                mode = input("\nChoose mode (1/2) [1]: ").strip() or "1"

                if mode not in ['1', '2']:
                    print("\nInvalid choice. Cancelled.")
                    self._pause()
                    return

                print("\n" + "=" * 80)
                print(f"Running: {job['name']}")
                print("=" * 80)

                if mode == '1':
                    self._execute_job_foreground(job)
                    print("\n" + "=" * 80)
                    print("JOB COMPLETED")
                    print("=" * 80)
                else:
                    self._execute_job(job)
                    print("\n" + "=" * 80)
                    print("JOB STARTED IN BACKGROUND")
                    print("=" * 80)
            else:
                print("\nInvalid job number.")
        except ValueError:
            print("\nInvalid input.")

        self._pause()

    def _execute_job_foreground(self, job: dict):
        """
        Execute a single job in foreground (wait for completion).
        Full performance - no resource competition with other jobs.

        Args:
            job: Job dictionary
        """
        job_id = job['id']
        start_time = datetime.now()

        # Update status to running
        self.job_manager.update_job_status(
            job_id,
            'running',
            started_at=start_time.isoformat()
        )

        print(f"\nInput:  {job['input_path']}")
        print(f"Output: {job['output_path']}")
        print(f"\nStarted: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 80)
        print()

        try:
            # Execute job and WAIT for completion (blocking)
            return_code, duration, log_file = self.executor.run_job(job)

            # Determine final status
            end_time = datetime.now()
            if return_code == 0:
                final_status = 'completed'
                status_text = "✓ SUCCESS"
            elif return_code == -1:
                final_status = 'failed'
                status_text = "✗ INTERRUPTED"
            else:
                final_status = 'failed'
                status_text = f"✗ FAILED (exit code: {return_code})"

            # Update job status
            self.job_manager.update_job_status(
                job_id,
                final_status,
                completed_at=end_time.isoformat(),
                duration_seconds=duration,
                return_code=return_code,
                log_file=log_file
            )

            # Display summary
            print()
            print("-" * 80)
            print(f"Completed: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Duration: {self._format_duration(duration)}")
            print(f"Status: {status_text}")
            print(f"Log: {log_file}")

        except Exception as e:
            print(f"\n✗ Failed to execute job: {str(e)}")
            self.job_manager.update_job_status(
                job_id,
                'failed',
                completed_at=datetime.now().isoformat()
            )

    def _execute_job(self, job: dict):
        """
        Execute a single job in the background (non-blocking).
        Job will continue running even if scheduler is closed.

        Args:
            job: Job dictionary
        """
        job_id = job['id']
        start_time = datetime.now()

        print(f"\nInput:  {job['input_path']}")
        print(f"Output: {job['output_path']}")
        print(f"\nStarting job in background...")
        print("-" * 80)

        try:
            # Execute job in background (non-blocking)
            pid, log_file = self.executor.run_job_background(job)

            # Update status to running with PID
            self.job_manager.update_job_status(
                job_id,
                'running',
                started_at=start_time.isoformat(),
                log_file=log_file,
                pid=pid
            )

            print(f"\n✓ Job started in background")
            print(f"  PID: {pid}")
            print(f"  Log: {log_file}")
            print(f"\nThe job will continue running even if you close the scheduler.")
            print(f"You can monitor progress by viewing the log file (option 7).")

        except Exception as e:
            print(f"\n✗ Failed to start job: {str(e)}")
            self.job_manager.update_job_status(
                job_id,
                'failed',
                completed_at=datetime.now().isoformat()
            )

    def _start_orchestrator(self, jobs):
        """
        Start the background orchestrator to manage sequential job execution.
        The orchestrator runs independently and continues even if scheduler is closed.

        Args:
            jobs: List of job dictionaries to execute sequentially
        """
        import subprocess
        import sys

        if not jobs:
            print("\nNo jobs to start.")
            return

        # Extract job IDs
        job_ids = [job['id'] for job in jobs]

        print(f"\nStarting background orchestrator for {len(job_ids)} job(s)...")
        for idx, job in enumerate(jobs, 1):
            print(f"  {idx}. {job['name']}")

        # Get path to orchestrator script
        orchestrator_path = Path(__file__).parent / 'orchestrator.py'

        # Build command
        python_exe = sys.executable
        cmd = [python_exe, '-u', str(orchestrator_path)] + job_ids

        # Create log file for orchestrator output
        orchestrator_log = Path.cwd() / f"orchestrator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        try:
            # Start orchestrator as detached background process
            if sys.platform == 'win32':
                # Windows: Use CREATE_NEW_PROCESS_GROUP and CREATE_NO_WINDOW
                CREATE_NEW_PROCESS_GROUP = 0x00000200
                CREATE_NO_WINDOW = 0x08000000

                process = subprocess.Popen(
                    cmd,
                    stdout=open(orchestrator_log, 'w', encoding='utf-8'),
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    cwd=Path.cwd(),
                    creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
                    close_fds=True
                )
            else:
                # Unix/Linux/Mac: Use start_new_session
                process = subprocess.Popen(
                    cmd,
                    stdout=open(orchestrator_log, 'w', encoding='utf-8'),
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    cwd=Path.cwd(),
                    start_new_session=True,
                    close_fds=True
                )

            orchestrator_pid = process.pid

            print(f"\n✓ Orchestrator started successfully!")
            print(f"  PID: {orchestrator_pid}")
            print(f"  Log: {orchestrator_log}")
            print(f"\nThe orchestrator will:")
            print(f"  - Execute jobs one at a time in sequence")
            print(f"  - Continue running even if you close this scheduler")
            print(f"  - Monitor job completion and start next job automatically")
            print(f"\nYou can safely close the scheduler now.")
            print(f"Jobs will continue in the background.")

        except Exception as e:
            print(f"\n✗ Failed to start orchestrator: {str(e)}")
            print("\nJobs were not started.")

    def _execute_job_sequential_background(self, job: dict, job_num: int, total_jobs: int):
        """
        Execute a job in background but wait for it to complete before returning.
        This allows sequential execution while running in background (can close scheduler).

        Args:
            job: Job dictionary
            job_num: Current job number (for display)
            total_jobs: Total number of jobs (for display)
        """
        import time
        try:
            import psutil
        except ImportError:
            print("\n✗ psutil not installed. Sequential background mode requires psutil.")
            print("  Install with: pip install psutil")
            print("\n  Falling back to parallel background mode...")
            self._execute_job(job)
            return

        job_id = job['id']
        start_time = datetime.now()

        print(f"\nInput:  {job['input_path']}")
        print(f"Output: {job['output_path']}")
        print(f"\nStarting job in background...")
        print("-" * 80)

        try:
            # Execute job in background (non-blocking)
            pid, log_file = self.executor.run_job_background(job)

            # Update status to running with PID
            self.job_manager.update_job_status(
                job_id,
                'running',
                started_at=start_time.isoformat(),
                log_file=log_file,
                pid=pid
            )

            print(f"\n✓ Job started in background")
            print(f"  PID: {pid}")
            print(f"  Log: {log_file}")
            print(f"\nWaiting for job to complete before starting next job...")
            print(f"(You can close this scheduler - the job will continue running)")
            print("-" * 80)

            # Poll the process until it completes
            last_check = time.time()
            check_interval = 5  # Check every 5 seconds

            while True:
                try:
                    process = psutil.Process(pid)
                    if not process.is_running():
                        break

                    # Show status update every 30 seconds
                    if time.time() - last_check >= 30:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        elapsed_str = self._format_duration(elapsed)
                        print(f"  [Job {job_num}/{total_jobs}] Still running... (elapsed: {elapsed_str})")
                        last_check = time.time()

                    time.sleep(check_interval)

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # Process has terminated
                    break

            # Job completed - determine final status from log file
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            return_code = None
            if log_file and Path(log_file).exists():
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if 'Status: SUCCESS' in content:
                            return_code = 0
                        elif 'Status: FAILED' in content or 'Status: INTERRUPTED' in content:
                            return_code = 1
                except:
                    pass

            final_status = 'completed' if return_code == 0 else 'failed'
            status_text = "✓ SUCCESS" if return_code == 0 else "✗ FAILED"

            self.job_manager.update_job_status(
                job_id,
                final_status,
                completed_at=end_time.isoformat(),
                return_code=return_code,
                duration_seconds=duration,
                pid=None
            )

            print()
            print("-" * 80)
            print(f"Completed: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Duration: {self._format_duration(duration)}")
            print(f"Status: {status_text}")
            print(f"Log: {log_file}")

        except Exception as e:
            print(f"\n✗ Failed to execute job: {str(e)}")
            self.job_manager.update_job_status(
                job_id,
                'failed',
                completed_at=datetime.now().isoformat()
            )

    def _view_job_details(self):
        """Display detailed information about a specific job."""
        jobs = self.job_manager.load_jobs()

        if not jobs:
            print("\nNo jobs available.")
            self._pause()
            return

        # Show jobs with indices
        print("\n" + "=" * 80)
        print("VIEW JOB DETAILS")
        print("=" * 80)
        print()

        for idx, job in enumerate(jobs, 1):
            status = self._format_status(job['status'])
            print(f"  {idx}. {job['name']} ({status})")

        print()
        choice = input("Enter job number to view (or 'c' to cancel): ").strip()

        if choice.lower() == 'c':
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(jobs):
                job = jobs[idx]

                print("\n" + "=" * 80)
                print("JOB DETAILS")
                print("=" * 80)
                print(f"\nID:          {job['id']}")
                print(f"Name:        {job['name']}")
                print(f"Status:      {self._format_status(job['status'])}")
                print(f"Description: {job.get('description', 'N/A')}")
                print(f"\nInput Path:  {job['input_path']}")
                print(f"Output Path: {job['output_path']}")
                print(f"\nCreated:     {self._format_datetime(job['created_at'])}")
                print(f"Started:     {self._format_datetime(job.get('started_at'))}")
                print(f"Completed:   {self._format_datetime(job.get('completed_at'))}")

                if job.get('pid'):
                    print(f"Process PID: {job['pid']} (running in background)")

                if job.get('duration_seconds'):
                    print(f"Duration:    {self._format_duration(job['duration_seconds'])}")

                if job.get('return_code') is not None:
                    print(f"Exit Code:   {job['return_code']}")

                if job.get('log_file'):
                    print(f"Log File:    {job['log_file']}")

            else:
                print("\nInvalid job number.")
        except ValueError:
            print("\nInvalid input.")

        self._pause()

    def _view_job_log(self):
        """View log file for a completed job."""
        jobs = [j for j in self.job_manager.load_jobs() if j.get('log_file')]

        if not jobs:
            print("\nNo jobs with log files available.")
            self._pause()
            return

        # Show jobs with logs
        print("\n" + "=" * 80)
        print("VIEW JOB LOG")
        print("=" * 80)
        print()

        for idx, job in enumerate(jobs, 1):
            status = self._format_status(job['status'])
            print(f"  {idx}. {job['name']} ({status})")

        print()
        choice = input("Enter job number to view log (or 'c' to cancel): ").strip()

        if choice.lower() == 'c':
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(jobs):
                job = jobs[idx]
                log_file = Path(job['log_file'])

                if not log_file.exists():
                    print(f"\nError: Log file not found: {log_file}")
                    self._pause()
                    return

                # Ask for full or tail
                view_option = input("\nView (f)ull log or (t)ail (last 50 lines)? [t]: ").strip().lower()

                print("\n" + "=" * 80)
                print(f"LOG: {job['name']}")
                print("=" * 80)
                print()

                with open(log_file, 'r', encoding='utf-8') as f:
                    if view_option == 'f':
                        # Full log
                        print(f.read())
                    else:
                        # Tail (last 50 lines)
                        lines = f.readlines()
                        tail_lines = lines[-50:] if len(lines) > 50 else lines
                        print(''.join(tail_lines))

            else:
                print("\nInvalid job number.")
        except ValueError:
            print("\nInvalid input.")

        self._pause()

    def _clear_completed_jobs(self):
        """Remove all completed/failed jobs from configuration."""
        print("\n" + "=" * 80)
        print("CLEAR COMPLETED JOBS")
        print("=" * 80)

        completed = [j for j in self.job_manager.load_jobs()
                     if j['status'] in ['completed', 'failed']]

        if not completed:
            print("\nNo completed or failed jobs to clear.")
            self._pause()
            return

        print(f"\nFound {len(completed)} completed/failed job(s):")
        for job in completed:
            status = self._format_status(job['status'])
            print(f"  - {job['name']} ({status})")

        confirm = input(f"\nRemove these jobs? (y/n): ").strip().lower()
        if confirm == 'y':
            removed = self.job_manager.clear_completed_jobs()
            print(f"\n✓ Removed {removed} job(s).")
        else:
            print("\nCancelled.")

        self._pause()

    def _retry_failed_jobs(self):
        """Reset failed jobs to pending status so they can be run again."""
        print("\n" + "=" * 80)
        print("RETRY FAILED JOBS")
        print("=" * 80)

        failed_jobs = self.job_manager.list_jobs(status='failed')

        if not failed_jobs:
            print("\nNo failed jobs found.")
            self._pause()
            return

        print(f"\nFound {len(failed_jobs)} failed job(s):")
        for idx, job in enumerate(failed_jobs, 1):
            print(f"  {idx}. {job['name']}")
            if job.get('log_file'):
                print(f"     Log: {job['log_file']}")

        print("\nOptions:")
        print("  1. Retry all failed jobs")
        print("  2. Select specific jobs to retry")
        print("  3. Cancel")

        choice = input("\nEnter choice (1-3): ").strip()

        jobs_to_retry = []

        if choice == '1':
            # Retry all failed jobs
            jobs_to_retry = failed_jobs
        elif choice == '2':
            # Select specific jobs
            print("\nEnter job numbers to retry (comma-separated, e.g., 1,3,5):")
            selection = input("Jobs: ").strip()

            try:
                indices = [int(x.strip()) - 1 for x in selection.split(',')]
                jobs_to_retry = [failed_jobs[i] for i in indices if 0 <= i < len(failed_jobs)]

                if not jobs_to_retry:
                    print("\nNo valid jobs selected.")
                    self._pause()
                    return
            except (ValueError, IndexError):
                print("\nInvalid selection.")
                self._pause()
                return
        elif choice == '3':
            print("\nCancelled.")
            self._pause()
            return
        else:
            print("\nInvalid choice.")
            self._pause()
            return

        # Confirm retry
        print(f"\nWill retry {len(jobs_to_retry)} job(s):")
        for job in jobs_to_retry:
            print(f"  - {job['name']}")

        confirm = input(f"\nReset these jobs to 'pending' status? (y/n): ").strip().lower()

        if confirm != 'y':
            print("\nCancelled.")
            self._pause()
            return

        # Reset jobs to pending
        reset_count = 0
        for job in jobs_to_retry:
            try:
                # Reset status to pending and clear ALL execution metadata
                # This includes log_file so a new log will be created on retry
                self.job_manager.update_job_status(
                    job['id'],
                    'pending',
                    started_at=None,
                    completed_at=None,
                    duration_seconds=None,
                    return_code=None,
                    pid=None,
                    log_file=None
                )
                reset_count += 1
            except Exception as e:
                print(f"\n✗ Failed to reset job '{job['name']}': {str(e)}")

        print(f"\n✓ Reset {reset_count} job(s) to 'pending' status.")
        print("\nYou can now run them using option 4 (Run all pending jobs) or option 5 (Run single job).")

        self._pause()

    def _configure_completion_hook(self):
        """Configure the command to run after all jobs complete."""
        print("\n" + "=" * 80)
        print("CONFIGURE COMPLETION HOOK")
        print("=" * 80)
        print()
        print("A completion hook is a shell command that runs automatically")
        print("after ALL jobs finish (when using Sequential Background mode).")
        print()
        print("Example uses:")
        print("  - Send Discord/Slack notification")
        print("  - Trigger another script")
        print("  - Send email notification")
        print()

        # Show current hook
        current_hook = self.job_manager.get_completion_hook()
        if current_hook:
            print(f"Current hook: {current_hook}")
        else:
            print("Current hook: (not set)")
        print()

        print("Options:")
        print("  1. Set new hook command")
        print("  2. Test current hook")
        print("  3. Disable hook")
        print("  4. Cancel")
        print()

        choice = input("Enter choice (1-4): ").strip()

        if choice == '1':
            # Set new hook
            print("\n" + "-" * 80)
            print("EXAMPLE DISCORD WEBHOOK:")
            print()
            print('curl -H "Content-Type: application/json" \\')
            print('     -X POST \\')
            print('     -d \'{"content": "Jobs sind fertig!!"}\' \\')
            print('     https://discord.com/api/webhooks/YOUR_WEBHOOK_URL')
            print("-" * 80)
            print()
            print("Enter your hook command (or press Enter to cancel):")
            print()

            # Read multi-line input
            lines = []
            print("(Enter an empty line when done)")
            while True:
                line = input()
                if not line:
                    break
                lines.append(line)

            if lines:
                command = ' '.join(lines)
                self.job_manager.set_completion_hook(command)
                print(f"\nHook configured successfully!")
                print(f"Command: {command}")
            else:
                print("\nCancelled.")

        elif choice == '2':
            # Test current hook
            if not current_hook:
                print("\nNo hook configured to test.")
            else:
                print(f"\nTesting hook: {current_hook}")
                confirm = input("Execute this command now? (y/n): ").strip().lower()

                if confirm == 'y':
                    print("\nExecuting hook...")
                    print("-" * 80)
                    try:
                        import subprocess
                        result = subprocess.run(
                            current_hook,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        print(f"Exit code: {result.returncode}")
                        if result.stdout:
                            print(f"Output:\n{result.stdout}")
                        if result.stderr:
                            print(f"Errors:\n{result.stderr}")
                    except subprocess.TimeoutExpired:
                        print("Hook timed out (30 seconds)")
                    except Exception as e:
                        print(f"Error executing hook: {str(e)}")
                    print("-" * 80)
                else:
                    print("\nCancelled.")

        elif choice == '3':
            # Disable hook
            if current_hook:
                confirm = input("\nAre you sure you want to disable the hook? (y/n): ").strip().lower()
                if confirm == 'y':
                    self.job_manager.set_completion_hook(None)
                    print("\nHook disabled.")
                else:
                    print("\nCancelled.")
            else:
                print("\nNo hook configured.")

        elif choice == '4':
            print("\nCancelled.")
        else:
            print("\nInvalid choice.")

        self._pause()

    def _format_status(self, status: str) -> str:
        """Format status with visual indicators."""
        status_map = {
            'pending': '⏸ Pending',
            'running': '▶ Running',
            'completed': '✓ Completed',
            'failed': '✗ Failed'
        }
        return status_map.get(status, status)

    def _format_datetime(self, dt_str: Optional[str]) -> str:
        """Format ISO datetime string for display."""
        if not dt_str:
            return 'N/A'
        try:
            dt = datetime.fromisoformat(dt_str)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return dt_str

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to readable string."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def _pause(self):
        """Pause and wait for user input."""
        input("\nPress Enter to continue...")


def main_loop():
    """Entry point for the scheduler UI."""
    ui = SchedulerUI()
    ui.main_loop()
