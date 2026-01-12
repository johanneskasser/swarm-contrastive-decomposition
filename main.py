import os
import numpy as np
import torch
from pathlib import Path
import scipy.io as sio
import argparse
from typing import List, Dict, Optional, Tuple

from config.structures import set_random_seed, Config
from models.scd import SwarmContrastiveDecomposition
from processing.postprocess import save_results
from utils.exporting import export_to_openhdemg_json, export_to_muedit_mat
from utils.preprocessing import loadEMG_updConfig, extract_raw_emg_metadata, load_channel_selection_json, get_grids_from_json

set_random_seed(seed=42)


def find_processable_files(input_path: Path) -> List[Path]:
    """
    Find all processable .mat files in a directory.

    Args:
        input_path: Path to directory or single file

    Returns:
        List of processable .mat file paths
    """
    if input_path.is_file():
        # Single file provided
        if input_path.suffix == '.mat':
            return [input_path]
        else:
            return []
    elif input_path.is_dir():
        # Directory provided - find all .mat files
        return sorted([f for f in input_path.iterdir() if f.is_file() and f.suffix == '.mat'])
    else:
        return []


def process_single_file(file_path: Path, output_folder: Path,
                       config_overrides: Optional[Dict] = None) -> Dict:
    """
    Process a single .mat file through the SCD algorithm.

    Args:
        file_path: Path to the .mat file to process
        output_folder: Output directory for results
        config_overrides: Optional configuration overrides

    Returns:
        Dictionary with processing results:
        {
            'success': bool,
            'file_path': str,
            'grids_processed': List[Dict],  # Info about each grid processed
            'error': str (if failed)
        }
    """
    result = {
        'success': False,
        'file_path': str(file_path),
        'grids_processed': [],
        'error': None
    }

    try:
        print(f"\n{'='*80}")
        print(f"Processing file: {file_path.name}")
        print('='*80)

        # Try to load channel selection JSON
        channel_selection = load_channel_selection_json(file_path)
        grids = get_grids_from_json(channel_selection)

        # If grids are found in JSON, process each grid separately
        if grids:
            print(f"\nProcessing {len(grids)} grid(s) separately...")
            for grid_idx, grid_info in enumerate(grids):
                grid_key = grid_info.get('grid_key', f'grid_{grid_idx}')
                print(f"\n{'-'*80}")
                print(f"Processing grid {grid_idx + 1}/{len(grids)}: {grid_key}")
                print('-'*80)

                # Try to extract muscle name from description for filename
                muscle_name = None
                try:
                    from utils.preprocessing import extract_muscle_name_from_description
                    mat_data = sio.loadmat(file_path)
                    channel_range = [
                        min(ch['channel_index'] for ch in grid_info['channels']),
                        max(ch['channel_index'] for ch in grid_info['channels']) + 1
                    ]
                    if 'Description' in mat_data and len(mat_data['Description']) > channel_range[0]:
                        description = mat_data['Description'][channel_range[0]][0][0]
                        if isinstance(description, np.ndarray):
                            description = str(description[0]) if description.size > 0 else str(description)
                        muscle_name = extract_muscle_name_from_description(description)
                        if muscle_name:
                            print(f"Muscle detected: {muscle_name}")
                except Exception as e:
                    print(f"Warning: Could not extract muscle name: {e}")

                # Create output path with grid suffix and optional muscle name
                filename_base = file_path.stem
                if muscle_name:
                    filename_suffix = f'_{grid_key}_{muscle_name}'
                else:
                    filename_suffix = f'_{grid_key}'
                output_path = output_folder.joinpath(
                    f'{filename_base}{filename_suffix}'
                ).with_suffix(".pkl")

                # Train model for this grid
                dictionary, _, mat, config = train(file_path, grid_info=grid_info,
                                                  grid_suffix=f"_{grid_key}",
                                                  output_folder=output_folder)

                # Save results
                save_results(output_path, dictionary)
                print(f"Saved results to {output_path}")

                # Prepare Raw Data Info for openHDEMG
                rawEMG_Channels, refSignal, fsamp, ied, extras = extract_raw_emg_metadata(file_path, config)
                # Save decomposition result to openhdemg compressed json format
                export_to_openhdemg_json(config, output_path, rawEMG_Channels, refSignal, ied, fsamp, str(file_path), extras)
                # Save decomposition result to muEdit compatible .mat format for manual cleaning
                export_to_muedit_mat(str(output_path).replace('.pkl', '.json'))

                print(f"Grid {grid_key} processing complete!")

                # Record grid processing success
                result['grids_processed'].append({
                    'grid_key': grid_key,
                    'muscle_name': muscle_name,
                    'output_file': str(output_path),
                    'success': True
                })
        else:
            # No channel selection JSON found - use original behavior (backward compatibility)
            print("\nNo channel selection JSON found. Using default channel configuration...")

            output_path = output_folder.joinpath(file_path.stem).with_suffix(".pkl")

            dictionary, _, mat, config = train(file_path, output_folder=output_folder)

            save_results(output_path, dictionary)
            print(f"Saved results to {output_path}")

            # Prepare Raw Data Info for openHDEMG
            rawEMG_Channels, refSignal, fsamp, ied, extras = extract_raw_emg_metadata(file_path, config)
            # Save decomposition result to openhdemg compressed json format
            export_to_openhdemg_json(config, output_path, rawEMG_Channels, refSignal, ied, fsamp, str(file_path), extras)
            # Save decomposition result to muEdit compatible .mat format for manual cleaning
            export_to_muedit_mat(str(output_path).replace('.pkl', '.json'))

            # Record single file processing success
            result['grids_processed'].append({
                'grid_key': 'default',
                'muscle_name': None,
                'output_file': str(output_path),
                'success': True
            })

        result['success'] = True
        print(f"\n[OK] Successfully processed: {file_path.name}")

    except Exception as e:
        result['error'] = str(e)
        print(f"\n[ERROR] Failed to process {file_path.name}: {str(e)}")
        import traceback
        traceback.print_exc()

    return result


def train(path, grid_info=None, grid_suffix="", output_folder=None):
    print(path)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    acceptance_silhouette = 0.88
    extension_factor = 20 # will be updated
    time_differentiate = False
    notch_params = [50, 1.0, True] # powerline frequency, bandwidth, filter harmonics
    low_pass_cutoff = 500
    high_pass_cutoff = 10
    start_time = 0 # will be updated
    end_time = -1 # will be updated
    max_iterations = 250
    sampling_frequency = 2000 # will be updated
    peel_off_window_size_ms = 50 # 20 # ms
    output_final_source_plot = False
    use_coeff_var_fitness = True
    remove_bad_fr = True
    clamp_percentile = 0.999

    config = Config(
        device=device,
        acceptance_silhouette=acceptance_silhouette,
        extension_factor=extension_factor,
        time_differentiate=time_differentiate,
        notch_params=notch_params,
        low_pass_cutoff=low_pass_cutoff,
        high_pass_cutoff=high_pass_cutoff,
        sampling_frequency=sampling_frequency,
        start_time=start_time,
        end_time=end_time,
        max_iterations=max_iterations,
        peel_off_window_size_ms=peel_off_window_size_ms,
        output_final_source_plot=output_final_source_plot,
        use_coeff_var_fitness=use_coeff_var_fitness,
        remove_bad_fr=remove_bad_fr,
        clamp_percentile=clamp_percentile,
    )

    # Load data
    # Default values (will be overridden by grid_info if provided)
    channel_range = [0,64] # Can be overridden by grid_info
    ref_path_measured_idx = 70 # Can be set via grid_info or use default
    ref_path_target_idx = 71 # Can be set via grid_info or use default
    bad_channels = [] # Will be overridden by grid_info if provided

    # Extract reference signal indices from grid_info if available
    if grid_info is not None and 'reference_signals' in grid_info:
        ref_signals = grid_info['reference_signals']
        if ref_signals:
            # Look for "Performed Path" and "Original Path" in reference signals
            for ref_sig in ref_signals:
                name = ref_sig.get('name', '').lower()
                if 'performed' in name or 'measured' in name:
                    ref_path_measured_idx = ref_sig['ref_index']
                    print(f"Using ref_path_measured_idx from JSON: {ref_path_measured_idx} ({ref_sig.get('name', 'unknown')})")
                elif 'original' in name or 'target' in name:
                    ref_path_target_idx = ref_sig['ref_index']
                    print(f"Using ref_path_target_idx from JSON: {ref_path_target_idx} ({ref_sig.get('name', 'unknown')})")

    if path.suffix == ".mat":
        mat = sio.loadmat(path)
        mat, config = loadEMG_updConfig(mat, config, channel_range, ref_path_target_idx, ref_path_measured_idx, bad_channels, grid_info=grid_info, output_folder=output_folder)
        neural_data = (
            torch.from_numpy(mat["emg"]).t().to(device=device, dtype=torch.float32)
        )  # time, channels
    elif path.suffix == ".npy":
        npy_data = np.load(path)
        neural_data = torch.from_numpy(npy_data).to(device=device, dtype=torch.float32)
    else:
        raise ValueError(
            "Data format not supported. Please provide data in .mat or .npy format."
        )
    start_index = int(config.start_time * sampling_frequency)
    end_index = int(config.end_time * sampling_frequency)
    neural_data = neural_data[start_index : end_index, : ]
#    if config.end_time == -1:
#        neural_data = neural_data[config.start_time * sampling_frequency : , :]
#    else:
#        neural_data = neural_data[config.start_time * sampling_frequency : config.end_time * sampling_frequency, :]

    # Initiate the model and run
    model = SwarmContrastiveDecomposition()
    predicted_timestamps, dictionary = model.run(neural_data, config)

    return dictionary, predicted_timestamps, mat, config


def parse_arguments():
    """
    Parse command-line arguments for input and output paths.

    Returns:
        argparse.Namespace: Parsed arguments containing input_path and output_path
    """
    parser = argparse.ArgumentParser(
        description='Swarm-Contrastive Decomposition for HD-EMG signal processing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default paths (data/input and data/output)
  python main.py

  # Specify custom input path
  python main.py --input-path /path/to/input

  # Specify both input and output paths
  python main.py --input-path /path/to/input --output-path /path/to/output

  # Use short options
  python main.py -i /path/to/input -o /path/to/output
        """
    )

    parser.add_argument(
        '--input-path', '-i',
        type=str,
        default='data/input',
        help='Path to directory containing input .mat files (default: data/input)'
    )

    parser.add_argument(
        '--output-path', '-o',
        type=str,
        default='data/output',
        help='Path to directory for output files (default: data/output)'
    )

    parser.add_argument(
        '--status-file', '-s',
        type=str,
        default=None,
        help='Path to status file for tracking progress (used by scheduler)'
    )

    return parser.parse_args()


if __name__ == "__main__":
    # # Uncomment the next three lines to run in interactive window
    # import sys
    # sys.argv=['']
    # del sys

    # Parse command-line arguments
    args = parse_arguments()

    # Set up input and output paths
    INPUT_PATH = Path(args.input_path)
    OUTPUT_PATH = Path(args.output_path)

    # Create output directory if it doesn't exist
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

    print(f"\nInput directory: {INPUT_PATH.resolve()}")
    print(f"Output directory: {OUTPUT_PATH.resolve()}\n")

    # Initialize status tracker if status file path provided
    status_tracker = None
    if args.status_file:
        from utils.status_tracker import StatusTracker
        status_tracker = StatusTracker.load_from_file(Path(args.status_file), OUTPUT_PATH)
        # Reinitialize with current file list
        file_paths = [f for f in INPUT_PATH.iterdir() if f.is_file() and f.suffix == '.mat']
        status_tracker.initialize(file_paths)

    # Get list of .mat files in input directory
    file_paths = [f for f in INPUT_PATH.iterdir() if f.is_file() and f.suffix == '.mat']
    file_names = [f.name for f in file_paths]
    if len(file_names) == 0:
        print(f'No .mat files in {INPUT_PATH}')

    for file_path in file_paths:
        file_name = file_path.name

        # Update status tracker - mark file as processing
        if status_tracker:
            status_tracker.set_processing(file_path)

        try:
            print(f"\n{'='*80}")
            print(f"Processing file: {file_name}")
            print('='*80)

            path = INPUT_PATH.joinpath(file_name).with_suffix(".mat")

            # Try to load channel selection JSON
            channel_selection = load_channel_selection_json(path)
            grids = get_grids_from_json(channel_selection)

            # Track successful grid count for status tracker
            successful_grids = 0

            # If grids are found in JSON, process each grid separately
            if grids:
                print(f"\nProcessing {len(grids)} grid(s) separately...")
                for grid_idx, grid_info in enumerate(grids):
                    try:
                        grid_key = grid_info.get('grid_key', f'grid_{grid_idx}')
                        print(f"\n{'-'*80}")
                        print(f"Processing grid {grid_idx + 1}/{len(grids)}: {grid_key}")
                        print('-'*80)

                        # Try to extract muscle name from description for filename
                        muscle_name = None
                        try:
                            from utils.preprocessing import extract_muscle_name_from_description
                            mat_data = sio.loadmat(path)
                            channel_range = [
                                min(ch['channel_index'] for ch in grid_info['channels']),
                                max(ch['channel_index'] for ch in grid_info['channels']) + 1
                            ]
                            if 'Description' in mat_data and len(mat_data['Description']) > channel_range[0]:
                                description = mat_data['Description'][channel_range[0]][0][0]
                                if isinstance(description, np.ndarray):
                                    description = str(description[0]) if description.size > 0 else str(description)
                                muscle_name = extract_muscle_name_from_description(description)
                                if muscle_name:
                                    print(f"Muscle detected: {muscle_name}")
                        except Exception as e:
                            print(f"Warning: Could not extract muscle name: {e}")

                        # Create output path with grid suffix and optional muscle name
                        filename_base = file_name.replace('.mat', '')
                        if muscle_name:
                            filename_suffix = f'_{grid_key}_{muscle_name}'
                        else:
                            filename_suffix = f'_{grid_key}'
                        output_path = OUTPUT_PATH.joinpath(
                            f'{filename_base}{filename_suffix}'
                        ).with_suffix(".pkl")

                        # Train model for this grid
                        dictionary, _, mat, config = train(path, grid_info=grid_info, grid_suffix=f"_{grid_key}", output_folder=OUTPUT_PATH)

                        # Save results
                        save_results(output_path, dictionary)
                        print(f"Saved results to {output_path}")

                        # Prepare Raw Data Info for openHDEMG
                        rawEMG_Channels, refSignal, fsamp, ied, extras = extract_raw_emg_metadata(path, config)
                        # Save decomposition result to openhdemg compressed json format
                        export_to_openhdemg_json(config, output_path, rawEMG_Channels, refSignal, ied, fsamp, os.path.join(path), extras)
                        # Save decomposition result to muEdit compatible .mat format for manual cleaning
                        export_to_muedit_mat(str(output_path).replace('.pkl', '.json'))

                        print(f"Grid {grid_key} processing complete!")
                        successful_grids += 1

                    except Exception as e:
                        print(f"\n[ERROR] Failed to process grid {grid_key}: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        print(f"Continuing with next grid...\n")
                        continue

            else:
                # No channel selection JSON found - use original behavior (backward compatibility)
                print("\nNo channel selection JSON found. Using default channel configuration...")

                output_path = OUTPUT_PATH.joinpath(file_name).with_suffix(".pkl")

                dictionary, _, mat, config = train(path, output_folder=OUTPUT_PATH)

                save_results(output_path, dictionary)
                print(f"Saved results to {output_path}")

                # Prepare Raw Data Info for openHDEMG
                rawEMG_Channels, refSignal, fsamp, ied, extras = extract_raw_emg_metadata(path, config)
                # Save decomposition result to openhdemg compressed json format
                export_to_openhdemg_json(config, output_path, rawEMG_Channels, refSignal, ied, fsamp, os.path.join(path), extras)
                # Save decomposition result to muEdit compatible .mat format for manual cleaning
                export_to_muedit_mat(str(output_path).replace('.pkl', '.json'))

                successful_grids = 1  # Single output for non-grid case

            # Mark file as done in status tracker
            if status_tracker:
                status_tracker.set_done(file_path, successful_grids)

        except Exception as e:
            print(f"\n[ERROR] Failed to process file {file_name}: {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"Continuing with next file...\n")

            # Mark file as failed in status tracker
            if status_tracker:
                status_tracker.set_failed(file_path, str(e))

            continue

    print('\n' + '='*80)
    print('--- ALL DONE ---')
    print('='*80)