import json
import os
import numpy as np
import torch
from datetime import datetime
from pathlib import Path
import scipy.io as sio
import argparse
from typing import List, Dict, Optional, Tuple

from scd.config.structures import set_random_seed, Config
from scd.models.scd import SwarmContrastiveDecomposition
from scd.processing.postprocess import save_results
from scd.utils.exporting import export_to_openhdemg_json, export_to_muedit_mat
from scd.utils.preprocessing import loadEMG_updConfig, extract_raw_emg_metadata, load_channel_selection_json, get_grids_from_json, extract_muscle_name_from_description

set_random_seed(seed=42)


def _save_grid_outputs(dictionary, config, file_path: Path, output_path: Path,
                       rawEMG_Channels, refSignal, fsamp, ied, extras):
    """Save .pkl, .json, and _muedit.mat outputs for a single grid result."""
    save_results(output_path, dictionary)
    export_to_openhdemg_json(config, output_path, rawEMG_Channels, refSignal,
                             ied, fsamp, str(file_path), extras)
    export_to_muedit_mat(str(output_path).replace('.pkl', '.json'))


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
                       algorithm_params: Optional[Dict] = None) -> Dict:
    """
    Process a single .mat file through the SCD algorithm.

    When repair_enabled is True in algorithm_params and a grid yields fewer MUs
    than repair_mu_threshold, the decomposition is retried with progressively
    higher extension_factor values. Intermediate (sub-optimal) attempts are
    stored under output_folder/repair_artefacts/<file_stem>/ and a
    repair_report.json summary is written there.

    Returns:
        {
            'success': bool,
            'file_path': str,
            'grids_processed': List[Dict],
            'error': str (if failed)
        }
    """
    params = algorithm_params or {}
    repair_enabled = params.get('repair_enabled', False)
    repair_mu_threshold = params.get('repair_mu_threshold', 2)
    repair_max_retries = params.get('repair_max_retries', 3)
    repair_extension_increment = params.get('repair_extension_increment', 5)
    repair_extension_max = params.get('repair_extension_max', 60)

    result = {
        'success': False,
        'file_path': str(file_path),
        'grids_processed': [],
        'error': None
    }

    # Collects repair info per grid label; used to write repair_report.json at the end.
    file_repair_info: Dict[str, dict] = {}

    try:
        print(f"\n{'='*80}")
        print(f"Processing file: {file_path.name}")
        print('='*80)

        channel_selection = load_channel_selection_json(file_path)
        grids = get_grids_from_json(channel_selection)

        if grids:
            print(f"\nProcessing {len(grids)} grid(s) separately...")
            for grid_idx, grid_info in enumerate(grids):
                grid_key = grid_info.get('grid_key', f'grid_{grid_idx}')
                print(f"\n{'-'*80}")
                print(f"Processing grid {grid_idx + 1}/{len(grids)}: {grid_key}")
                print('-'*80)

                muscle_name = None
                try:
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

                filename_base = file_path.stem
                filename_suffix = f'_{grid_key}_{muscle_name}' if muscle_name else f'_{grid_key}'
                output_path = output_folder.joinpath(f'{filename_base}{filename_suffix}').with_suffix(".pkl")
                grid_label = output_path.stem  # e.g. "recording_GR1_Biceps"

                # First decomposition attempt
                dictionary, _, _, config = train(file_path, grid_info=grid_info,
                                                 grid_suffix=f"_{grid_key}",
                                                 output_folder=output_folder,
                                                 algorithm_params=algorithm_params)
                rawEMG_Channels, refSignal, fsamp, ied, extras = extract_raw_emg_metadata(file_path, config)
                mu_count = len(dictionary.get('silhouettes', []))
                actual_ef = config.extension_factor  # resolved value (may have been 'auto')

                if repair_enabled and mu_count < repair_mu_threshold:
                    print(f"  [REPAIR] MU yield {mu_count} < threshold {repair_mu_threshold} — starting repair loop")

                    repair_base = output_folder / 'repair_artefacts' / file_path.stem / grid_label
                    repair_base.mkdir(parents=True, exist_ok=True)

                    attempts = []

                    # Save first attempt as attempt_1
                    attempt_folder = repair_base / f'attempt_1_ef{actual_ef}'
                    attempt_folder.mkdir(parents=True, exist_ok=True)
                    _save_grid_outputs(dictionary, config, file_path,
                                       attempt_folder / output_path.name,
                                       rawEMG_Channels, refSignal, fsamp, ied, extras)
                    attempts.append({
                        'attempt': 1,
                        'extension_factor': actual_ef,
                        'mu_count': mu_count,
                        'folder': str(attempt_folder),
                    })

                    best_dictionary, best_config, best_mu_count = dictionary, config, mu_count
                    current_ef = actual_ef

                    for retry in range(1, repair_max_retries + 1):
                        current_ef = actual_ef + retry * repair_extension_increment
                        if current_ef > repair_extension_max:
                            print(f"  [REPAIR] extension_factor {current_ef} would exceed max {repair_extension_max}, stopping.")
                            break
                        print(f"  [REPAIR] Attempt {retry + 1}: extension_factor = {current_ef}")
                        retry_params = {**params, 'extension_factor': current_ef}
                        try:
                            new_dict, _, _, new_config = train(file_path, grid_info=grid_info,
                                                               grid_suffix=f"_{grid_key}",
                                                               output_folder=output_folder,
                                                               algorithm_params=retry_params)
                            new_mu_count = len(new_dict.get('silhouettes', []))
                            print(f"  [REPAIR]   → {new_mu_count} MU(s) found")

                            attempt_folder = repair_base / f'attempt_{retry + 1}_ef{current_ef}'
                            attempt_folder.mkdir(parents=True, exist_ok=True)
                            _save_grid_outputs(new_dict, new_config, file_path,
                                               attempt_folder / output_path.name,
                                               rawEMG_Channels, refSignal, fsamp, ied, extras)
                            attempts.append({
                                'attempt': retry + 1,
                                'extension_factor': current_ef,
                                'mu_count': new_mu_count,
                                'folder': str(attempt_folder),
                            })

                            if new_mu_count > best_mu_count:
                                best_dictionary, best_config, best_mu_count = new_dict, new_config, new_mu_count
                        except Exception as repair_err:
                            print(f"  [REPAIR]   → attempt {retry + 1} failed: {repair_err}")
                            attempts.append({
                                'attempt': retry + 1,
                                'extension_factor': current_ef,
                                'mu_count': 0,
                                'error': str(repair_err),
                            })

                    # Save best result to the normal output location
                    _save_grid_outputs(best_dictionary, best_config, file_path, output_path,
                                       rawEMG_Channels, refSignal, fsamp, ied, extras)
                    best_attempt = max(attempts, key=lambda a: a.get('mu_count', 0))
                    print(f"  [REPAIR] Best: {best_mu_count} MU(s) at ef={best_attempt['extension_factor']}")
                    print(f"Saved best result to {output_path}")

                    file_repair_info[grid_label] = {
                        'trigger': f'MU yield {mu_count} < threshold {repair_mu_threshold}',
                        'attempts': attempts,
                        'best_attempt': best_attempt,
                        'improved': best_mu_count > mu_count,
                        'final_output': str(output_path),
                    }
                else:
                    _save_grid_outputs(dictionary, config, file_path, output_path,
                                       rawEMG_Channels, refSignal, fsamp, ied, extras)
                    print(f"Saved results to {output_path}")

                print(f"Grid {grid_key} processing complete!")
                result['grids_processed'].append({
                    'grid_key': grid_key,
                    'muscle_name': muscle_name,
                    'output_file': str(output_path),
                    'success': True,
                })
        else:
            # No channel selection JSON — backward-compatible single-grid path
            print("\nNo channel selection JSON found. Using default channel configuration...")

            output_path = output_folder.joinpath(file_path.stem).with_suffix(".pkl")
            grid_label = output_path.stem

            dictionary, _, _, config = train(file_path, output_folder=output_folder,
                                             algorithm_params=algorithm_params)
            rawEMG_Channels, refSignal, fsamp, ied, extras = extract_raw_emg_metadata(file_path, config)
            mu_count = len(dictionary.get('silhouettes', []))
            actual_ef = config.extension_factor

            if repair_enabled and mu_count < repair_mu_threshold:
                print(f"  [REPAIR] MU yield {mu_count} < threshold {repair_mu_threshold} — starting repair loop")

                repair_base = output_folder / 'repair_artefacts' / file_path.stem / grid_label
                repair_base.mkdir(parents=True, exist_ok=True)

                attempts = []
                attempt_folder = repair_base / f'attempt_1_ef{actual_ef}'
                attempt_folder.mkdir(parents=True, exist_ok=True)
                _save_grid_outputs(dictionary, config, file_path,
                                   attempt_folder / output_path.name,
                                   rawEMG_Channels, refSignal, fsamp, ied, extras)
                attempts.append({
                    'attempt': 1,
                    'extension_factor': actual_ef,
                    'mu_count': mu_count,
                    'folder': str(attempt_folder),
                })

                best_dictionary, best_config, best_mu_count = dictionary, config, mu_count
                current_ef = actual_ef

                for retry in range(1, repair_max_retries + 1):
                    current_ef = actual_ef + retry * repair_extension_increment
                    if current_ef > repair_extension_max:
                        print(f"  [REPAIR] extension_factor {current_ef} would exceed max {repair_extension_max}, stopping.")
                        break
                    print(f"  [REPAIR] Attempt {retry + 1}: extension_factor = {current_ef}")
                    retry_params = {**params, 'extension_factor': current_ef}
                    try:
                        new_dict, _, _, new_config = train(file_path, output_folder=output_folder,
                                                           algorithm_params=retry_params)
                        new_mu_count = len(new_dict.get('silhouettes', []))
                        print(f"  [REPAIR]   → {new_mu_count} MU(s) found")

                        attempt_folder = repair_base / f'attempt_{retry + 1}_ef{current_ef}'
                        attempt_folder.mkdir(parents=True, exist_ok=True)
                        _save_grid_outputs(new_dict, new_config, file_path,
                                           attempt_folder / output_path.name,
                                           rawEMG_Channels, refSignal, fsamp, ied, extras)
                        attempts.append({
                            'attempt': retry + 1,
                            'extension_factor': current_ef,
                            'mu_count': new_mu_count,
                            'folder': str(attempt_folder),
                        })

                        if new_mu_count > best_mu_count:
                            best_dictionary, best_config, best_mu_count = new_dict, new_config, new_mu_count
                    except Exception as repair_err:
                        print(f"  [REPAIR]   → attempt {retry + 1} failed: {repair_err}")
                        attempts.append({
                            'attempt': retry + 1,
                            'extension_factor': current_ef,
                            'mu_count': 0,
                            'error': str(repair_err),
                        })

                _save_grid_outputs(best_dictionary, best_config, file_path, output_path,
                                   rawEMG_Channels, refSignal, fsamp, ied, extras)
                best_attempt = max(attempts, key=lambda a: a.get('mu_count', 0))
                print(f"  [REPAIR] Best: {best_mu_count} MU(s) at ef={best_attempt['extension_factor']}")
                print(f"Saved best result to {output_path}")

                file_repair_info[grid_label] = {
                    'trigger': f'MU yield {mu_count} < threshold {repair_mu_threshold}',
                    'attempts': attempts,
                    'best_attempt': best_attempt,
                    'improved': best_mu_count > mu_count,
                    'final_output': str(output_path),
                }
            else:
                _save_grid_outputs(dictionary, config, file_path, output_path,
                                   rawEMG_Channels, refSignal, fsamp, ied, extras)
                print(f"Saved results to {output_path}")

            result['grids_processed'].append({
                'grid_key': 'default',
                'muscle_name': None,
                'output_file': str(output_path),
                'success': True,
            })

        # Write per-file repair report if any grid triggered the repair loop
        if file_repair_info:
            repair_report_dir = output_folder / 'repair_artefacts' / file_path.stem
            repair_report_dir.mkdir(parents=True, exist_ok=True)
            report = {
                'file': str(file_path),
                'generated_at': datetime.now().isoformat(),
                'repair_settings': {
                    'mu_threshold': repair_mu_threshold,
                    'max_retries': repair_max_retries,
                    'extension_increment': repair_extension_increment,
                    'extension_max': repair_extension_max,
                },
                'grids': file_repair_info,
            }
            report_path = repair_report_dir / 'repair_report.json'
            with open(report_path, 'w', encoding='utf-8') as fh:
                json.dump(report, fh, indent=2)
            print(f"\n[REPAIR] Report written to {report_path}")

        result['success'] = True
        print(f"\n[OK] Successfully processed: {file_path.name}")

    except Exception as e:
        result['error'] = str(e)
        print(f"\n[ERROR] Failed to process {file_path.name}: {str(e)}")
        import traceback
        traceback.print_exc()

    return result


def train(path, grid_info=None, grid_suffix="", output_folder=None, algorithm_params=None):
    """
    Train the Swarm-Contrastive Decomposition model on EMG data.

    Args:
        path: Path to the .mat or .npy file
        grid_info: Optional grid configuration from channel selection JSON
        grid_suffix: Optional suffix for output filenames
        output_folder: Output directory for results
        algorithm_params: Optional dict of algorithm parameters (uses defaults if not provided)
    """
    print(path)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    # Default parameters
    acceptance_silhouette = 0.88
    extension_factor = None  # None → auto-calculated in scd.run() via Negro 2016
    time_differentiate = False
    notch_params = [50, 1.0, True]
    low_pass_cutoff = 500
    high_pass_cutoff = 10
    start_time = 0
    end_time = -1
    max_iterations = 250
    sampling_frequency = 2000  # overridden by loadEMG_updConfig
    peel_off_window_size_ms = 50
    output_final_source_plot = False
    use_coeff_var_fitness = True
    remove_bad_fr = True
    max_firing_rate_hz = 50.0
    reset_peak_separation_ms = 4.0
    clamp_sources = True
    square_sources_spike_det = True
    peel_off = True
    swarm = True
    electrode = None

    # Override with provided algorithm parameters
    if algorithm_params:
        acceptance_silhouette = algorithm_params.get('acceptance_silhouette', acceptance_silhouette)
        extension_factor = algorithm_params.get('extension_factor', extension_factor)
        time_differentiate = algorithm_params.get('time_differentiate', time_differentiate)
        notch_params = algorithm_params.get('notch_params', notch_params)
        low_pass_cutoff = algorithm_params.get('low_pass_cutoff', low_pass_cutoff)
        high_pass_cutoff = algorithm_params.get('high_pass_cutoff', high_pass_cutoff)
        max_iterations = algorithm_params.get('max_iterations', max_iterations)
        sampling_frequency = algorithm_params.get('sampling_frequency', sampling_frequency)
        peel_off_window_size_ms = algorithm_params.get('peel_off_window_size_ms', peel_off_window_size_ms)
        output_final_source_plot = algorithm_params.get('output_final_source_plot', output_final_source_plot)
        use_coeff_var_fitness = algorithm_params.get('use_coeff_var_fitness', use_coeff_var_fitness)
        remove_bad_fr = algorithm_params.get('remove_bad_fr', remove_bad_fr)
        max_firing_rate_hz = algorithm_params.get('max_firing_rate_hz', max_firing_rate_hz)
        reset_peak_separation_ms = algorithm_params.get('reset_peak_separation_ms', reset_peak_separation_ms)
        clamp_sources = algorithm_params.get('clamp_sources', clamp_sources)
        square_sources_spike_det = algorithm_params.get('square_sources_spike_det', square_sources_spike_det)
        peel_off = algorithm_params.get('peel_off', peel_off)
        swarm = algorithm_params.get('swarm', swarm)
        electrode = algorithm_params.get('electrode', electrode) or None

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
        max_firing_rate_hz=max_firing_rate_hz,
        reset_peak_separation_ms=reset_peak_separation_ms,
        clamp_sources=clamp_sources,
        square_sources_spike_det=square_sources_spike_det,
        peel_off=peel_off,
        swarm=swarm,
        electrode=electrode,
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

    parser.add_argument(
        '--params-file', '-p',
        type=str,
        default=None,
        help='Path to JSON file containing algorithm parameters (used by scheduler)'
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

    # Load algorithm parameters from JSON file if provided, or auto-detect newest in output folder
    algorithm_params = None
    import json
    if args.params_file:
        params_path = Path(args.params_file)
    else:
        # Find newest algorithm_params*.json in output folder
        candidates = sorted(OUTPUT_PATH.glob("algorithm_params*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        params_path = candidates[0] if candidates else None
        if params_path:
            print(f"Auto-detected algorithm parameters file: {params_path.name}")

    if params_path and params_path.exists():
        with open(params_path, 'r', encoding='utf-8') as f:
            algorithm_params = json.load(f)
        print(f"Loaded algorithm parameters from: {params_path}")
        # Print key parameters
        print(f"  acceptance_silhouette: {algorithm_params.get('acceptance_silhouette', 'default')}")
        print(f"  max_iterations: {algorithm_params.get('max_iterations', 'default')}")
        print(f"  sampling_frequency: {algorithm_params.get('sampling_frequency', 'default')}")
    elif args.params_file:
        print(f"Warning: Parameters file not found: {params_path}")

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
                        dictionary, _, mat, config = train(path, grid_info=grid_info, grid_suffix=f"_{grid_key}",
                                                          output_folder=OUTPUT_PATH, algorithm_params=algorithm_params)

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

                dictionary, _, mat, config = train(path, output_folder=OUTPUT_PATH,
                                                  algorithm_params=algorithm_params)

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