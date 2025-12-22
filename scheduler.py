#!/usr/bin/env python3
"""
HD-EMG Decomposition Scheduler

Modern TUI scheduler for running HD-EMG decomposition jobs with file-by-file processing.

Usage:
    python scheduler.py              # Launch TUI (default)
    python scheduler.py --cli        # Launch classic CLI

Features:
    - Modern Textual-based TUI interface
    - Add/remove/view jobs with intuitive interface
    - File-by-file processing with individual tracking
    - Real-time job status updates
    - Detailed file processing results
    - Comprehensive logging with timestamps
    - Automatic error isolation (failed files don't block others)

Author: Claude Code
Version: 2.0.0
"""

import sys
import argparse
from pathlib import Path

# Ensure we're in the right directory
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def main():
    """Main entry point for the scheduler."""
    parser = argparse.ArgumentParser(
        description='HD-EMG Decomposition Scheduler',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Launch modern TUI (default)
  python scheduler.py

  # Launch classic CLI interface
  python scheduler.py --cli
        """
    )

    parser.add_argument(
        '--cli',
        action='store_true',
        help='Use classic CLI interface instead of TUI'
    )

    args = parser.parse_args()

    try:
        if args.cli:
            # Classic CLI mode
            print("\nStarting HD-EMG Decomposition Scheduler (CLI mode)...\n")
            from scheduler.ui import main_loop
            main_loop()
        else:
            # Modern TUI mode (default)
            from scheduler.tui import main as tui_main
            tui_main()

    except KeyboardInterrupt:
        print("\n\nScheduler interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nUnexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        print("\nPlease check your configuration and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
