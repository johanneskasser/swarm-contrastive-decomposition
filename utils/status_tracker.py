"""
Status File Tracker for HD-EMG Decomposition

Manages a status file that tracks which files have been processed and which are waiting.
The status file is stored in the output folder and updated as processing progresses.
"""

from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import json


class StatusTracker:
    """Tracks processing status of files and writes updates to a status file."""

    def __init__(self, output_folder: Path, job_name: Optional[str] = None):
        """
        Initialize StatusTracker.

        Args:
            output_folder: Path to the output folder where status file will be created
            job_name: Optional job name to include in status filename
        """
        self.output_folder = Path(output_folder)
        self.output_folder.mkdir(parents=True, exist_ok=True)

        # Create status file name
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if job_name:
            # Sanitize job name for filename
            safe_job_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in job_name)
            status_filename = f"status_{safe_job_name}_{timestamp}.txt"
        else:
            status_filename = f"status_{timestamp}.txt"

        self.status_file = self.output_folder / status_filename

        # Internal tracking
        self.files_status: List[Dict] = []
        self.total_files = 0

    def initialize(self, file_paths: List[Path]):
        """
        Initialize the status tracker with a list of files to process.

        Args:
            file_paths: List of file paths to be processed
        """
        self.total_files = len(file_paths)
        self.files_status = [
            {
                'file_path': file_path,
                'file_name': file_path.name,
                'status': 'waiting',
                'output_count': 0,
                'error': None,
                'started_at': None,
                'completed_at': None
            }
            for file_path in file_paths
        ]

        # Write initial status
        self._write_status()

    def set_processing(self, file_path: Path):
        """
        Mark a file as currently being processed.

        Args:
            file_path: Path to the file being processed
        """
        for file_status in self.files_status:
            if file_status['file_path'] == file_path:
                file_status['status'] = 'processing'
                file_status['started_at'] = datetime.now().isoformat()
                break

        self._write_status()

    def set_done(self, file_path: Path, output_count: int):
        """
        Mark a file as successfully processed.

        Args:
            file_path: Path to the processed file
            output_count: Number of output files generated (e.g., number of grids)
        """
        for file_status in self.files_status:
            if file_status['file_path'] == file_path:
                file_status['status'] = 'done'
                file_status['output_count'] = output_count
                file_status['completed_at'] = datetime.now().isoformat()
                break

        self._write_status()

    def set_failed(self, file_path: Path, error: str):
        """
        Mark a file as failed.

        Args:
            file_path: Path to the failed file
            error: Error message describing the failure
        """
        for file_status in self.files_status:
            if file_status['file_path'] == file_path:
                file_status['status'] = 'failed'
                file_status['error'] = error
                file_status['completed_at'] = datetime.now().isoformat()
                break

        self._write_status()

    def _write_status(self):
        """Write the current status to the status file."""
        with open(self.status_file, 'w', encoding='utf-8') as f:
            # Header
            f.write("=" * 80 + "\n")
            f.write("HD-EMG DECOMPOSITION - FILE PROCESSING STATUS\n")
            f.write("=" * 80 + "\n")
            f.write(f"Status file: {self.status_file.name}\n")
            f.write(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Output folder: {self.output_folder}\n")
            f.write("=" * 80 + "\n\n")

            # Summary
            done_count = sum(1 for fs in self.files_status if fs['status'] == 'done')
            failed_count = sum(1 for fs in self.files_status if fs['status'] == 'failed')
            processing_count = sum(1 for fs in self.files_status if fs['status'] == 'processing')
            waiting_count = sum(1 for fs in self.files_status if fs['status'] == 'waiting')

            f.write("SUMMARY:\n")
            f.write(f"  Total files:      {self.total_files}\n")
            f.write(f"  Done:             {done_count}\n")
            f.write(f"  Failed:           {failed_count}\n")
            f.write(f"  Processing:       {processing_count}\n")
            f.write(f"  Waiting:          {waiting_count}\n")
            f.write("\n" + "=" * 80 + "\n\n")

            # Detailed file list
            f.write("FILES:\n\n")
            for idx, file_status in enumerate(self.files_status, 1):
                status_symbol = {
                    'waiting': '[ ]',
                    'processing': '[~]',
                    'done': '[✓]',
                    'failed': '[✗]'
                }.get(file_status['status'], '[?]')

                file_name = file_status['file_name']
                status_text = file_status['status'].upper()

                # Format status line
                if file_status['status'] == 'done':
                    output_info = f"-- {status_text} ({file_status['output_count']} output file(s))"
                elif file_status['status'] == 'failed':
                    output_info = f"-- {status_text}"
                elif file_status['status'] == 'processing':
                    output_info = f"-- {status_text}"
                else:  # waiting
                    output_info = f"-- {status_text}"

                f.write(f"{status_symbol} [{idx:2d}] {file_name} {output_info}\n")

                # Add error message for failed files
                if file_status['status'] == 'failed' and file_status['error']:
                    # Truncate long error messages
                    error_msg = file_status['error']
                    if len(error_msg) > 200:
                        error_msg = error_msg[:200] + "..."
                    f.write(f"         Error: {error_msg}\n")

                # Add timing info if available
                if file_status['started_at'] and file_status['completed_at']:
                    try:
                        started = datetime.fromisoformat(file_status['started_at'])
                        completed = datetime.fromisoformat(file_status['completed_at'])
                        duration = (completed - started).total_seconds()
                        f.write(f"         Duration: {self._format_duration(duration)}\n")
                    except:
                        pass

                f.write("\n")

            # Footer
            f.write("=" * 80 + "\n")
            f.write("Status file updated continuously during processing\n")
            f.write("=" * 80 + "\n")

    def _format_duration(self, seconds: float) -> str:
        """
        Format duration in seconds to human-readable string.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def get_status_file_path(self) -> Path:
        """
        Get the path to the status file.

        Returns:
            Path to the status file
        """
        return self.status_file

    def get_summary(self) -> Dict:
        """
        Get a summary of processing status.

        Returns:
            Dictionary with counts of files in each status
        """
        return {
            'total': self.total_files,
            'done': sum(1 for fs in self.files_status if fs['status'] == 'done'),
            'failed': sum(1 for fs in self.files_status if fs['status'] == 'failed'),
            'processing': sum(1 for fs in self.files_status if fs['status'] == 'processing'),
            'waiting': sum(1 for fs in self.files_status if fs['status'] == 'waiting')
        }

    @classmethod
    def load_from_file(cls, status_file_path: Path, output_folder: Path) -> 'StatusTracker':
        """
        Load an existing StatusTracker from a status file.

        Args:
            status_file_path: Path to existing status file
            output_folder: Output folder path

        Returns:
            StatusTracker instance with loaded state
        """
        tracker = cls.__new__(cls)
        tracker.output_folder = output_folder
        tracker.status_file = status_file_path
        tracker.files_status = []
        tracker.total_files = 0

        # Try to reconstruct files_status from the directory
        # Since the status file text format isn't easily parseable,
        # we'll just reinitialize with the file list
        # The status file itself will continue to be updated

        return tracker
