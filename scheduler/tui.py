"""
Textual TUI for HD-EMG Decomposition Scheduler

Modern terminal user interface using Textual framework.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, List

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Static, DataTable, Button, Input, Label,
    ListView, ListItem, TabbedContent, TabPane, Tree, Log, ProgressBar
)
from textual.binding import Binding
from textual.screen import Screen, ModalScreen
from textual import on
from textual.reactive import reactive

from .job_manager import JobManager
from .executor import JobExecutor


class JobDetailsScreen(Screen):
    """Modal screen showing detailed job information and file processing status."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("q", "dismiss", "Close", show=False),
    ]

    def __init__(self, job: dict, job_manager: JobManager):
        super().__init__()
        self.job = job
        self.job_manager = job_manager

    def compose(self) -> ComposeResult:
        """Compose the job details screen."""
        with Container(id="job-details-container"):
            yield Static(f"[bold cyan]Job Details: {self.job['name']}[/]", id="job-details-header")

            # Job metadata
            metadata = f"""
[bold]ID:[/] {self.job['id']}
[bold]Status:[/] {self._format_status(self.job['status'])}
[bold]Description:[/] {self.job.get('description', 'N/A')}

[bold]Input Path:[/] {self.job['input_path']}
[bold]Output Path:[/] {self.job['output_path']}

[bold]Created:[/] {self._format_datetime(self.job['created_at'])}
[bold]Started:[/] {self._format_datetime(self.job.get('started_at'))}
[bold]Completed:[/] {self._format_datetime(self.job.get('completed_at'))}
[bold]Duration:[/] {self._format_duration(self.job.get('duration_seconds'))}
"""
            yield Static(metadata, id="job-metadata")

            # File processing stats
            total = self.job.get('total_files', 0)
            successful = self.job.get('successful_files', 0)
            failed = self.job.get('failed_files', 0)
            current = self.job.get('current_file')

            if total > 0:
                stats = f"""
[bold]File Processing Status:[/]
  Total files: {total}
  Successful: [green]{successful}[/]
  Failed: [red]{failed}[/]
  In progress: {len(self.job.get('files_processed', [])) - (successful + failed)}
"""
                if current:
                    stats += f"  [yellow]Currently processing:[/] {Path(current).name}\n"

                yield Static(stats, id="file-stats")

                # Processed files table
                yield Static("[bold]Processed Files:[/]", id="files-header")

                table = DataTable(id="files-table")
                table.add_columns("File", "Status", "Grids", "Error")

                for file_result in self.job.get('files_processed', []):
                    file_path = Path(file_result['file_path'])
                    status = "[green]✓ Success[/]" if file_result['success'] else "[red]✗ Failed[/]"
                    grids = str(len(file_result.get('grids_processed', [])))
                    error = file_result.get('error', '')[:50] if file_result.get('error') else ''

                    table.add_row(file_path.name, status, grids, error)

                yield table

            yield Button("Close [dim](ESC)[/]", variant="primary", id="close-button")

    def _format_status(self, status: str) -> str:
        """Format status with colors."""
        status_map = {
            'pending': '[yellow]⏸ Pending[/]',
            'running': '[cyan]▶ Running[/]',
            'completed': '[green]✓ Completed[/]',
            'failed': '[red]✗ Failed[/]'
        }
        return status_map.get(status, status)

    def _format_datetime(self, dt_str: Optional[str]) -> str:
        """Format ISO datetime string."""
        if not dt_str:
            return 'N/A'
        try:
            dt = datetime.fromisoformat(dt_str)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return dt_str

    def _format_duration(self, seconds: Optional[float]) -> str:
        """Format duration."""
        if seconds is None:
            return 'N/A'

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    @on(Button.Pressed, "#close-button")
    def action_dismiss(self) -> None:
        """Dismiss the screen."""
        self.dismiss()


class AddJobScreen(ModalScreen[Optional[dict]]):
    """Modal screen for adding a new job."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def compose(self) -> ComposeResult:
        """Compose the add job screen."""
        with Container(id="add-job-container"):
            yield Static("[bold cyan]Add New Job[/]", id="add-job-header")

            yield Label("Job Name:")
            yield Input(placeholder="Enter job name...", id="job-name-input")

            yield Label("Input Path:")
            yield Input(placeholder="Path to .mat file or directory...", id="input-path-input")

            yield Label("Output Path:")
            yield Input(placeholder="Output directory path...", id="output-path-input")

            yield Label("Description (optional):")
            yield Input(placeholder="Job description...", id="description-input")

            with Horizontal(id="add-job-buttons"):
                yield Button("Add Job", variant="success", id="add-button")
                yield Button("Cancel", variant="default", id="cancel-button")

    @on(Button.Pressed, "#add-button")
    def add_job(self) -> None:
        """Add the job."""
        name = self.query_one("#job-name-input", Input).value.strip()
        input_path = self.query_one("#input-path-input", Input).value.strip()
        output_path = self.query_one("#output-path-input", Input).value.strip()
        description = self.query_one("#description-input", Input).value.strip()

        if not name or not input_path or not output_path:
            self.app.notify("Please fill in all required fields", severity="error")
            return

        self.dismiss({
            'name': name,
            'input_path': input_path,
            'output_path': output_path,
            'description': description
        })

    @on(Button.Pressed, "#cancel-button")
    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(None)


class SchedulerTUI(App):
    """HD-EMG Decomposition Scheduler TUI Application."""

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        width: 100%;
        height: 100%;
        padding: 1;
    }

    #jobs-table {
        height: 1fr;
        border: solid $primary;
    }

    #actions-panel {
        height: auto;
        padding: 1;
        border: solid $accent;
        margin-top: 1;
    }

    #job-details-container {
        width: 90%;
        height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 2;
    }

    #job-details-header {
        text-align: center;
        margin-bottom: 1;
    }

    #job-metadata {
        margin-bottom: 1;
    }

    #file-stats {
        margin-bottom: 1;
        padding: 1;
        background: $boost;
    }

    #files-header {
        margin-top: 1;
        margin-bottom: 1;
    }

    #files-table {
        height: 20;
        margin-bottom: 1;
    }

    #close-button {
        dock: bottom;
        width: 100%;
        margin-top: 1;
    }

    #add-job-container {
        width: 70;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 2;
    }

    #add-job-header {
        text-align: center;
        margin-bottom: 1;
    }

    Label {
        margin-top: 1;
        margin-bottom: 0;
    }

    Input {
        margin-bottom: 1;
    }

    #add-job-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #add-job-buttons Button {
        margin: 0 1;
    }

    .status-pending {
        color: $warning;
    }

    .status-running {
        color: $accent;
    }

    .status-completed {
        color: $success;
    }

    .status-failed {
        color: $error;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("a", "add_job", "Add Job", show=True),
        Binding("r", "run_job", "Run Job", show=True),
        Binding("d", "view_details", "Details", show=True),
        Binding("x", "remove_job", "Remove Job", show=True),
        Binding("c", "clear_completed", "Clear Completed", show=True),
        Binding("f5", "refresh", "Refresh", show=True),
    ]

    TITLE = "HD-EMG Decomposition Scheduler"
    SUB_TITLE = "File-by-File Processing"

    def __init__(self):
        super().__init__()
        self.job_manager = JobManager()
        self.executor = JobExecutor()
        self.selected_job_id: Optional[str] = None

    def compose(self) -> ComposeResult:
        """Compose the app layout."""
        yield Header(show_clock=True)

        with Container(id="main-container"):
            # Jobs table
            jobs_table = DataTable(id="jobs-table", cursor_type="row")
            jobs_table.add_columns("ID", "Name", "Status", "Files", "Success", "Failed", "Created")
            yield jobs_table

            # Action buttons panel
            with Container(id="actions-panel"):
                with Horizontal():
                    yield Button("Add Job (A)", variant="success", id="btn-add")
                    yield Button("Run Job (R)", variant="primary", id="btn-run")
                    yield Button("Details (D)", variant="default", id="btn-details")
                    yield Button("Remove (X)", variant="error", id="btn-remove")
                    yield Button("Clear Completed (C)", variant="default", id="btn-clear")
                    yield Button("Refresh (F5)", variant="default", id="btn-refresh")

        yield Footer()

    def on_mount(self) -> None:
        """Handle mount event."""
        self.refresh_jobs_table()
        self.set_interval(2, self.refresh_jobs_table)  # Auto-refresh every 2 seconds

    def refresh_jobs_table(self) -> None:
        """Refresh the jobs table with latest data."""
        table = self.query_one("#jobs-table", DataTable)

        # Store current cursor position
        cursor_row = table.cursor_row if table.cursor_row < len(table.rows) else 0

        # Clear and repopulate
        table.clear()

        try:
            self.job_manager.check_running_jobs()
        except:
            pass  # Ignore errors if psutil not available

        jobs = self.job_manager.load_jobs()

        for job in jobs:
            job_id = job['id'][-8:]  # Show last 8 chars
            name = job['name'][:20]  # Truncate name
            status = self._format_status_short(job['status'])
            files = str(job.get('total_files', 0))
            success = str(job.get('successful_files', 0))
            failed = str(job.get('failed_files', 0))
            created = datetime.fromisoformat(job['created_at']).strftime('%Y-%m-%d %H:%M')

            table.add_row(job_id, name, status, files, success, failed, created, key=job['id'])

        # Restore cursor position
        if len(table.rows) > 0:
            table.move_cursor(row=min(cursor_row, len(table.rows) - 1))

    def _format_status_short(self, status: str) -> str:
        """Format status for table display."""
        status_map = {
            'pending': '⏸ Pending',
            'running': '▶ Running',
            'completed': '✓ Done',
            'failed': '✗ Failed'
        }
        return status_map.get(status, status)

    @on(DataTable.RowSelected, "#jobs-table")
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        self.selected_job_id = event.row_key.value if event.row_key else None

    @on(DataTable.RowHighlighted, "#jobs-table")
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row highlighting."""
        self.selected_job_id = event.row_key.value if event.row_key else None

    @on(Button.Pressed, "#btn-add")
    def action_add_job(self) -> None:
        """Show add job screen."""
        def handle_result(result: Optional[dict]) -> None:
            if result:
                try:
                    self.job_manager.add_job(
                        result['name'],
                        result['input_path'],
                        result['output_path'],
                        result['description']
                    )
                    self.notify(f"Job '{result['name']}' added successfully", severity="information")
                    self.refresh_jobs_table()
                except ValueError as e:
                    self.notify(str(e), severity="error")

        self.push_screen(AddJobScreen(), handle_result)

    @on(Button.Pressed, "#btn-run")
    def action_run_job(self) -> None:
        """Run selected job."""
        if not self.selected_job_id:
            self.notify("Please select a job first", severity="warning")
            return

        job = self.job_manager.get_job(self.selected_job_id)
        if not job:
            self.notify("Job not found", severity="error")
            return

        if job['status'] not in ['pending', 'failed']:
            self.notify("Job is not in pending or failed state", severity="warning")
            return

        # Run job in foreground with file tracking
        self.notify(f"Starting job '{job['name']}'...", severity="information")

        # Update status
        self.job_manager.update_job_status(
            self.selected_job_id,
            'running',
            started_at=datetime.now().isoformat()
        )

        try:
            # Execute with file tracking
            return_code, duration, log_file = self.executor.run_job_with_file_tracking(job, self.job_manager)

            # Update final status
            final_status = 'completed' if return_code == 0 else 'failed'
            self.job_manager.update_job_status(
                self.selected_job_id,
                final_status,
                completed_at=datetime.now().isoformat(),
                duration_seconds=duration,
                return_code=return_code,
                log_file=log_file
            )

            if return_code == 0:
                self.notify(f"Job completed successfully!", severity="information")
            else:
                self.notify(f"Job failed. Check log: {log_file}", severity="error")

        except Exception as e:
            self.notify(f"Error running job: {str(e)}", severity="error")
            self.job_manager.update_job_status(
                self.selected_job_id,
                'failed',
                completed_at=datetime.now().isoformat()
            )

        self.refresh_jobs_table()

    @on(Button.Pressed, "#btn-details")
    def action_view_details(self) -> None:
        """View selected job details."""
        if not self.selected_job_id:
            self.notify("Please select a job first", severity="warning")
            return

        job = self.job_manager.get_job(self.selected_job_id)
        if not job:
            self.notify("Job not found", severity="error")
            return

        self.push_screen(JobDetailsScreen(job, self.job_manager))

    @on(Button.Pressed, "#btn-remove")
    def action_remove_job(self) -> None:
        """Remove selected job."""
        if not self.selected_job_id:
            self.notify("Please select a job first", severity="warning")
            return

        job = self.job_manager.get_job(self.selected_job_id)
        if not job:
            self.notify("Job not found", severity="error")
            return

        self.job_manager.remove_job(self.selected_job_id)
        self.notify(f"Job '{job['name']}' removed", severity="information")
        self.selected_job_id = None
        self.refresh_jobs_table()

    @on(Button.Pressed, "#btn-clear")
    def action_clear_completed(self) -> None:
        """Clear all completed jobs."""
        removed = self.job_manager.clear_completed_jobs()
        self.notify(f"Removed {removed} completed/failed job(s)", severity="information")
        self.selected_job_id = None
        self.refresh_jobs_table()

    @on(Button.Pressed, "#btn-refresh")
    def action_refresh(self) -> None:
        """Manually refresh jobs table."""
        self.refresh_jobs_table()
        self.notify("Jobs refreshed", severity="information")


def main():
    """Entry point for the Textual TUI."""
    app = SchedulerTUI()
    app.run()


if __name__ == "__main__":
    main()
