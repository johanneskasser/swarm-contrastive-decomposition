"""
Job Manager for HD-EMG Decomposition Scheduler

Handles CRUD operations on jobs_config.json and job persistence.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


# Default algorithm parameters for decomposition
# These match the defaults in main.py train() function
DEFAULT_ALGORITHM_PARAMS = {
    "acceptance_silhouette": 0.88,
    "max_iterations": 250,
    "sampling_frequency": 2000,
    "remove_bad_fr": True,
    "low_pass_cutoff": 500,
    "high_pass_cutoff": 10,
    "extension_factor": 20,
    "peel_off_window_size_ms": 50,
    "notch_params": [50, 1.0, True],
    "time_differentiate": False,
    "use_coeff_var_fitness": True,
    "clamp_percentile": 0.999,
    "output_final_source_plot": False,
    # New parameters from scd/configs.json
    "square_sources_spike_det": False,
    "peel_off": True,
    "swarm": True,
    "electrode": "",
}

# Parameter metadata for UI display and validation
ALGORITHM_PARAMS_METADATA = {
    "acceptance_silhouette": {
        "type": "float",
        "min": 0.5,
        "max": 1.0,
        "description": "Quality threshold for accepting motor units (0.5-1.0)"
    },
    "max_iterations": {
        "type": "int",
        "min": 10,
        "max": 1000,
        "description": "Maximum decomposition iterations"
    },
    "sampling_frequency": {
        "type": "int",
        "min": 100,
        "max": 10000,
        "description": "Sampling frequency in Hz (often auto-detected)"
    },
    "remove_bad_fr": {
        "type": "bool",
        "description": "Filter sources by physiological firing rate (2-100 Hz)"
    },
    "low_pass_cutoff": {
        "type": "int",
        "min": 100,
        "max": 2000,
        "description": "Low-pass filter cutoff frequency in Hz"
    },
    "high_pass_cutoff": {
        "type": "int",
        "min": 1,
        "max": 100,
        "description": "High-pass filter cutoff frequency in Hz"
    },
    "extension_factor": {
        "type": "int",
        "min": 1,
        "max": 100,
        "description": "Temporal extension factor (typically 1000/num_channels)"
    },
    "peel_off_window_size_ms": {
        "type": "int",
        "min": 10,
        "max": 200,
        "description": "Window size for spike-triggered averaging in ms"
    },
    "notch_params": {
        "type": "list",
        "description": "Notch filter: [frequency Hz, bandwidth, filter_harmonics]"
    },
    "time_differentiate": {
        "type": "bool",
        "description": "Apply time differentiation preprocessing"
    },
    "use_coeff_var_fitness": {
        "type": "bool",
        "description": "Use coefficient of variation fitness metric"
    },
    "clamp_percentile": {
        "type": "float",
        "min": 0.9,
        "max": 1.0,
        "description": "Percentile for outlier clamping (0.9-1.0)"
    },
    "output_final_source_plot": {
        "type": "bool",
        "description": "Generate plots of accepted motor unit sources"
    },
    "square_sources_spike_det": {
        "type": "bool",
        "description": "Square sources before spike detection for better peak separation"
    },
    "peel_off": {
        "type": "bool",
        "description": "Remove identified source contributions from signal after each extraction (iterative deflation)"
    },
    "swarm": {
        "type": "bool",
        "description": "Use particle swarm optimisation update step (core SCD algorithm feature)"
    },
    "electrode": {
        "type": "string",
        "description": "Electrode type descriptor for labelling (e.g. 'surface grid', 'intramuscular')"
    },
}


class JobManager:
    """Manages job configuration and persistence."""

    def __init__(self, config_file: str = "jobs_config.json"):
        """
        Initialize JobManager.

        Args:
            config_file: Path to JSON configuration file
        """
        self.config_file = Path(config_file)
        self.jobs_data = self._load_or_create_config()

    def _load_or_create_config(self) -> Dict:
        """Load existing config or create new one."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: {self.config_file} is corrupted. Creating backup...")
                backup_file = self.config_file.with_suffix('.json.bak')
                self.config_file.rename(backup_file)
                return self._create_default_config()
        else:
            return self._create_default_config()

    def _create_default_config(self) -> Dict:
        """Create default configuration structure."""
        return {
            "version": "1.0",
            "jobs": [],
            "hooks": {
                "on_all_jobs_completed": None
            },
            "global_algorithm_params": None  # None means use DEFAULT_ALGORITHM_PARAMS
        }

    def save_jobs(self):
        """Save jobs to JSON file."""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.jobs_data, f, indent=2, ensure_ascii=False)

    def load_jobs(self) -> List[Dict]:
        """
        Load all jobs from configuration.

        Always reloads from file to ensure fresh data, especially when
        external processes (like the orchestrator) update job statuses.

        Returns:
            List of job dictionaries
        """
        # Reload from file to get latest changes
        self.jobs_data = self._load_or_create_config()
        return self.jobs_data.get("jobs", [])

    def add_job(self, name: str, input_path: str, output_path: str,
                description: str = "", algorithm_params: Optional[Dict[str, Any]] = None) -> Dict:
        """
        Add a new job to the configuration.

        Args:
            name: Human-readable job name
            input_path: Path to input directory with .mat files
            output_path: Path to output directory
            description: Optional job description
            algorithm_params: Optional dict of algorithm parameters (uses global params if not provided)

        Returns:
            The created job dictionary

        Raises:
            ValueError: If job name already exists or paths are invalid
        """
        # Validate job name is unique
        if any(job['name'] == name for job in self.jobs_data['jobs']):
            raise ValueError(f"Job with name '{name}' already exists")

        # Validate paths
        self.validate_paths(input_path, output_path)

        # Generate unique job ID
        job_id = self._generate_job_id()

        # Start with global params (which falls back to DEFAULT_ALGORITHM_PARAMS if not set)
        params = self.get_global_params()
        # Override with job-specific params if provided
        if algorithm_params:
            params.update(algorithm_params)

        # Create job object
        job = {
            "id": job_id,
            "name": name,
            "input_path": str(Path(input_path).resolve()),
            "output_path": str(Path(output_path).resolve()),
            "description": description,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "duration_seconds": None,
            "return_code": None,
            "log_file": None,
            "status_file": None,
            "pid": None,
            "files": [],  # List of files to process
            "files_processed": [],  # List of processed file results
            "current_file": None,  # Currently processing file
            "total_files": 0,
            "successful_files": 0,
            "failed_files": 0,
            "algorithm_params": params  # Algorithm parameters for decomposition
        }

        # Add to jobs list
        self.jobs_data['jobs'].append(job)
        self.save_jobs()

        return job

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a job from configuration.

        Args:
            job_id: Job ID to remove

        Returns:
            True if job was removed, False if not found
        """
        jobs = self.jobs_data['jobs']
        initial_count = len(jobs)
        self.jobs_data['jobs'] = [j for j in jobs if j['id'] != job_id]

        if len(self.jobs_data['jobs']) < initial_count:
            self.save_jobs()
            return True
        return False

    def get_job(self, job_id: str) -> Optional[Dict]:
        """
        Get a specific job by ID.

        Args:
            job_id: Job ID to retrieve

        Returns:
            Job dictionary or None if not found
        """
        for job in self.jobs_data['jobs']:
            if job['id'] == job_id:
                return job
        return None

    def list_jobs(self, status: Optional[str] = None) -> List[Dict]:
        """
        List all jobs, optionally filtered by status.

        Args:
            status: Optional status filter (pending, running, completed, failed)

        Returns:
            List of job dictionaries
        """
        jobs = self.jobs_data['jobs']
        if status:
            jobs = [j for j in jobs if j['status'] == status]
        return jobs

    def update_job_status(self, job_id: str, status: str, **kwargs):
        """
        Update job status and optionally other fields.

        Args:
            job_id: Job ID to update
            status: New status value
            **kwargs: Additional fields to update (started_at, completed_at, etc.)
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found")

        job['status'] = status
        for key, value in kwargs.items():
            if key in job:
                job[key] = value

        self.save_jobs()

    def validate_paths(self, input_path: str, output_path: str):
        """
        Validate input and output paths.

        Args:
            input_path: Path to input directory
            output_path: Path to output directory

        Raises:
            ValueError: If paths are invalid
        """
        input_p = Path(input_path)

        # Input path should exist
        if not input_p.exists():
            raise ValueError(f"Input path does not exist: {input_path}")

        if not input_p.is_dir():
            raise ValueError(f"Input path is not a directory: {input_path}")

        # Output path will be created if it doesn't exist, so just check parent
        output_p = Path(output_path)
        if output_p.exists() and not output_p.is_dir():
            raise ValueError(f"Output path exists but is not a directory: {output_path}")

    def clear_completed_jobs(self) -> int:
        """
        Remove all completed jobs from configuration.

        Returns:
            Number of jobs removed
        """
        initial_count = len(self.jobs_data['jobs'])
        self.jobs_data['jobs'] = [
            j for j in self.jobs_data['jobs']
            if j['status'] not in ['completed', 'failed']
        ]
        removed_count = initial_count - len(self.jobs_data['jobs'])

        if removed_count > 0:
            self.save_jobs()

        return removed_count

    def check_running_jobs(self):
        """
        Check all 'running' jobs to see if their processes are still alive.
        Updates status if process has terminated.
        """
        import psutil

        running_jobs = self.list_jobs(status='running')

        for job in running_jobs:
            pid = job.get('pid')
            if pid is None:
                # No PID recorded, mark as failed
                self.update_job_status(
                    job['id'],
                    'failed',
                    completed_at=datetime.now().isoformat()
                )
                continue

            # Check if process is still running
            try:
                process = psutil.Process(pid)
                # Process exists, check if it's actually our process
                if not process.is_running():
                    raise psutil.NoSuchProcess(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Process is dead, update status
                # Try to determine if it succeeded or failed
                log_file = job.get('log_file')
                return_code = None

                if log_file and Path(log_file).exists():
                    # Check log file for status
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

                self.update_job_status(
                    job['id'],
                    final_status,
                    completed_at=datetime.now().isoformat(),
                    return_code=return_code,
                    pid=None
                )

    def _generate_job_id(self) -> str:
        """
        Generate unique job ID based on timestamp.

        Returns:
            Unique job ID string
        """
        return f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def set_completion_hook(self, command: Optional[str]):
        """
        Set the command to execute after all jobs are completed.

        Args:
            command: Shell command to execute, or None to disable hook
        """
        if "hooks" not in self.jobs_data:
            self.jobs_data["hooks"] = {}

        self.jobs_data["hooks"]["on_all_jobs_completed"] = command
        self.save_jobs()

    def get_completion_hook(self) -> Optional[str]:
        """
        Get the completion hook command.

        Returns:
            Hook command string or None if not set
        """
        if "hooks" not in self.jobs_data:
            return None

        return self.jobs_data["hooks"].get("on_all_jobs_completed")

    def update_job_files(self, job_id: str, files: List[str]):
        """
        Update the list of files to process for a job.

        Args:
            job_id: Job ID to update
            files: List of file paths to process
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found")

        job['files'] = [str(f) for f in files]
        job['total_files'] = len(files)
        job['files_processed'] = []
        job['successful_files'] = 0
        job['failed_files'] = 0
        self.save_jobs()

    def add_processed_file(self, job_id: str, file_result: Dict):
        """
        Add a processed file result to a job.

        Args:
            job_id: Job ID to update
            file_result: Dictionary with file processing result
                {
                    'file_path': str,
                    'success': bool,
                    'grids_processed': List[Dict],
                    'error': str (optional)
                }
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found")

        job['files_processed'].append(file_result)
        if file_result.get('success'):
            job['successful_files'] = job.get('successful_files', 0) + 1
        else:
            job['failed_files'] = job.get('failed_files', 0) + 1

        job['current_file'] = None
        self.save_jobs()

    def set_current_file(self, job_id: str, file_path: Optional[str]):
        """
        Set the currently processing file for a job.

        Args:
            job_id: Job ID to update
            file_path: Path of file being processed, or None
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found")

        job['current_file'] = str(file_path) if file_path else None
        self.save_jobs()

    def update_job_params(self, job_id: str, params: Dict[str, Any]):
        """
        Update algorithm parameters for a job.

        Args:
            job_id: Job ID to update
            params: Dictionary of parameter names and values to update
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found")

        # Ensure algorithm_params exists (for backward compatibility with old jobs)
        if 'algorithm_params' not in job:
            job['algorithm_params'] = DEFAULT_ALGORITHM_PARAMS.copy()

        # Update only the provided parameters
        for key, value in params.items():
            if key in DEFAULT_ALGORITHM_PARAMS:
                job['algorithm_params'][key] = value
            else:
                raise ValueError(f"Unknown algorithm parameter: {key}")

        self.save_jobs()

    def get_job_params(self, job_id: str) -> Dict[str, Any]:
        """
        Get algorithm parameters for a job.

        Args:
            job_id: Job ID to retrieve params for

        Returns:
            Dictionary of algorithm parameters
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found")

        # Return existing params or defaults (for backward compatibility)
        return job.get('algorithm_params', DEFAULT_ALGORITHM_PARAMS.copy())

    def reset_job_params(self, job_id: str):
        """
        Reset algorithm parameters for a job to defaults.

        Args:
            job_id: Job ID to reset params for
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found")

        job['algorithm_params'] = DEFAULT_ALGORITHM_PARAMS.copy()
        self.save_jobs()

    # --- Global Algorithm Parameters ---

    def get_global_params(self) -> Dict[str, Any]:
        """
        Get global algorithm parameters.

        Returns:
            Dictionary of global algorithm parameters.
            Returns DEFAULT_ALGORITHM_PARAMS if no global params are set.
        """
        global_params = self.jobs_data.get('global_algorithm_params')
        if global_params is None:
            return DEFAULT_ALGORITHM_PARAMS.copy()
        # Merge with defaults to ensure all keys exist
        result = DEFAULT_ALGORITHM_PARAMS.copy()
        result.update(global_params)
        return result

    def set_global_params(self, params: Dict[str, Any]):
        """
        Set global algorithm parameters.

        Args:
            params: Dictionary of parameter names and values to set globally.
        """
        # Validate all keys
        for key in params:
            if key not in DEFAULT_ALGORITHM_PARAMS:
                raise ValueError(f"Unknown algorithm parameter: {key}")

        # Initialize if not exists
        if self.jobs_data.get('global_algorithm_params') is None:
            self.jobs_data['global_algorithm_params'] = DEFAULT_ALGORITHM_PARAMS.copy()

        # Update only provided parameters
        self.jobs_data['global_algorithm_params'].update(params)
        self.save_jobs()

    def update_global_param(self, param_key: str, value: Any):
        """
        Update a single global algorithm parameter.

        Args:
            param_key: Name of the parameter
            value: New value for the parameter
        """
        if param_key not in DEFAULT_ALGORITHM_PARAMS:
            raise ValueError(f"Unknown algorithm parameter: {param_key}")

        if self.jobs_data.get('global_algorithm_params') is None:
            self.jobs_data['global_algorithm_params'] = DEFAULT_ALGORITHM_PARAMS.copy()

        self.jobs_data['global_algorithm_params'][param_key] = value
        self.save_jobs()

    def reset_global_params(self):
        """
        Reset global algorithm parameters to defaults.

        This sets global_algorithm_params to None, meaning DEFAULT_ALGORITHM_PARAMS
        will be used.
        """
        self.jobs_data['global_algorithm_params'] = None
        self.save_jobs()

    def has_custom_global_params(self) -> bool:
        """
        Check if custom global parameters are set.

        Returns:
            True if global_algorithm_params is set (not None), False otherwise.
        """
        return self.jobs_data.get('global_algorithm_params') is not None
