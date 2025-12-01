"""
Job Manager for HD-EMG Decomposition Scheduler

Handles CRUD operations on jobs_config.json and job persistence.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


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
            "jobs": []
        }

    def save_jobs(self):
        """Save jobs to JSON file."""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.jobs_data, f, indent=2, ensure_ascii=False)

    def load_jobs(self) -> List[Dict]:
        """
        Load all jobs from configuration.

        Returns:
            List of job dictionaries
        """
        return self.jobs_data.get("jobs", [])

    def add_job(self, name: str, input_path: str, output_path: str,
                description: str = "") -> Dict:
        """
        Add a new job to the configuration.

        Args:
            name: Human-readable job name
            input_path: Path to input directory with .mat files
            output_path: Path to output directory
            description: Optional job description

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
            "log_file": None
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

    def _generate_job_id(self) -> str:
        """
        Generate unique job ID based on timestamp.

        Returns:
            Unique job ID string
        """
        return f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
