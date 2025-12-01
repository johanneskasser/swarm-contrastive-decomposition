#!/usr/bin/env python3
"""
HD-EMG Decomposition Scheduler

Interactive CLI scheduler for running HD-EMG decomposition jobs sequentially.

Usage:
    python scheduler.py

Features:
    - Add/remove/view jobs
    - Run all pending jobs or individual jobs
    - Real-time output streaming
    - Comprehensive logging with timestamps
    - Automatic error handling

Author: Claude Code
Version: 1.0.0
"""

import sys
from pathlib import Path

# Ensure we're in the right directory
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from scheduler.ui import main_loop


def main():
    """Main entry point for the scheduler."""
    try:
        print("\nStarting HD-EMG Decomposition Scheduler...\n")
        main_loop()
    except KeyboardInterrupt:
        print("\n\nScheduler interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nUnexpected error: {str(e)}")
        print("Please check your configuration and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
