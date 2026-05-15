"""
HD-EMG Decomposition Scheduler

A simple interactive CLI scheduler for running HD-EMG decomposition jobs sequentially.
"""

__version__ = "1.0.0"


def main() -> None:
    """Entry point for the scd-scheduler CLI command."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="HD-EMG Decomposition Scheduler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  scd-scheduler          # Launch modern TUI (default)
  scd-scheduler --cli    # Launch classic CLI interface
        """,
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Use classic CLI interface instead of TUI",
    )
    args = parser.parse_args()

    try:
        if args.cli:
            print("\nStarting HD-EMG Decomposition Scheduler (CLI mode)...\n")
            from scheduler.ui import main_loop
            main_loop()
        else:
            try:
                from scheduler.tui import main as tui_main
                tui_main()
            except ImportError:
                print("\nTUI not available, falling back to CLI mode...\n")
                from scheduler.ui import main_loop
                main_loop()
    except KeyboardInterrupt:
        print("\n\nScheduler interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
