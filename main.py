import json
import os
import argparse
import traceback
from pathlib import Path

import numpy as np
import scipy.io as sio

from scd.pipeline import find_processable_files, process_single_file, train
from scd.processing.postprocess import save_results
from scd.utils.exporting import export_to_openhdemg_json, export_to_muedit_mat
from scd.utils.preprocessing import (
    load_channel_selection_json,
    get_grids_from_json,
    extract_raw_emg_metadata,
    extract_muscle_name_from_description,
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Swarm-Contrastive Decomposition for HD-EMG signal processing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py
  python main.py --input-path /path/to/input
  python main.py -i /path/to/input -o /path/to/output
        """
    )
    parser.add_argument('--input-path', '-i', type=str, default='data/input',
                        help='Path to directory containing input .mat files (default: data/input)')
    parser.add_argument('--output-path', '-o', type=str, default='data/output',
                        help='Path to directory for output files (default: data/output)')
    parser.add_argument('--status-file', '-s', type=str, default=None,
                        help='Path to status file for tracking progress (used by scheduler)')
    parser.add_argument('--params-file', '-p', type=str, default=None,
                        help='Path to JSON file containing algorithm parameters (used by scheduler)')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    INPUT_PATH = Path(args.input_path)
    OUTPUT_PATH = Path(args.output_path)
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

    print(f"\nInput directory: {INPUT_PATH.resolve()}")
    print(f"Output directory: {OUTPUT_PATH.resolve()}\n")

    status_tracker = None
    if args.status_file:
        from scd.utils.status_tracker import StatusTracker
        status_tracker = StatusTracker.load_from_file(Path(args.status_file), OUTPUT_PATH)
        file_paths = [f for f in INPUT_PATH.iterdir() if f.is_file() and f.suffix == '.mat']
        status_tracker.initialize(file_paths)

    algorithm_params = None
    if args.params_file:
        params_path = Path(args.params_file)
    else:
        candidates = sorted(OUTPUT_PATH.glob("algorithm_params*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        params_path = candidates[0] if candidates else None
        if params_path:
            print(f"Auto-detected algorithm parameters file: {params_path.name}")

    if params_path and params_path.exists():
        with open(params_path, 'r', encoding='utf-8') as f:
            algorithm_params = json.load(f)
        print(f"Loaded algorithm parameters from: {params_path}")
        print(f"  acceptance_silhouette: {algorithm_params.get('acceptance_silhouette', 'default')}")
        print(f"  max_iterations: {algorithm_params.get('max_iterations', 'default')}")
        print(f"  sampling_frequency: {algorithm_params.get('sampling_frequency', 'default')}")
    elif args.params_file:
        print(f"Warning: Parameters file not found: {params_path}")

    file_paths = [f for f in INPUT_PATH.iterdir() if f.is_file() and f.suffix == '.mat']
    if not file_paths:
        print(f'No .mat files in {INPUT_PATH}')

    for file_path in file_paths:
        file_name = file_path.name

        if status_tracker:
            status_tracker.set_processing(file_path)

        try:
            print(f"\n{'='*80}")
            print(f"Processing file: {file_name}")
            print('='*80)

            path = INPUT_PATH.joinpath(file_name).with_suffix(".mat")

            channel_selection = load_channel_selection_json(path)
            grids = get_grids_from_json(channel_selection)

            successful_grids = 0

            if grids:
                print(f"\nProcessing {len(grids)} grid(s) separately...")
                for grid_idx, grid_info in enumerate(grids):
                    try:
                        grid_key = grid_info.get('grid_key', f'grid_{grid_idx}')
                        print(f"\n{'-'*80}")
                        print(f"Processing grid {grid_idx + 1}/{len(grids)}: {grid_key}")
                        print('-'*80)

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

                        filename_base = file_name.replace('.mat', '')
                        filename_suffix = f'_{grid_key}_{muscle_name}' if muscle_name else f'_{grid_key}'
                        output_path = OUTPUT_PATH.joinpath(f'{filename_base}{filename_suffix}').with_suffix(".pkl")

                        dictionary, _, mat, config = train(path, grid_info=grid_info,
                                                           grid_suffix=f"_{grid_key}",
                                                           output_folder=OUTPUT_PATH,
                                                           algorithm_params=algorithm_params)

                        save_results(output_path, dictionary)
                        print(f"Saved results to {output_path}")

                        rawEMG_Channels, refSignal, fsamp, ied, extras = extract_raw_emg_metadata(path, config)
                        export_to_openhdemg_json(config, output_path, rawEMG_Channels, refSignal,
                                                 ied, fsamp, os.path.join(path), extras)
                        export_to_muedit_mat(str(output_path).replace('.pkl', '.json'))

                        print(f"Grid {grid_key} processing complete!")
                        successful_grids += 1

                    except Exception as e:
                        print(f"\n[ERROR] Failed to process grid {grid_key}: {str(e)}")
                        traceback.print_exc()
                        print(f"Continuing with next grid...\n")
                        continue
            else:
                print("\nNo channel selection JSON found. Using default channel configuration...")

                output_path = OUTPUT_PATH.joinpath(file_name).with_suffix(".pkl")
                dictionary, _, mat, config = train(path, output_folder=OUTPUT_PATH,
                                                   algorithm_params=algorithm_params)

                save_results(output_path, dictionary)
                print(f"Saved results to {output_path}")

                rawEMG_Channels, refSignal, fsamp, ied, extras = extract_raw_emg_metadata(path, config)
                export_to_openhdemg_json(config, output_path, rawEMG_Channels, refSignal,
                                         ied, fsamp, os.path.join(path), extras)
                export_to_muedit_mat(str(output_path).replace('.pkl', '.json'))
                successful_grids = 1

            if status_tracker:
                status_tracker.set_done(file_path, successful_grids)

        except Exception as e:
            print(f"\n[ERROR] Failed to process file {file_name}: {str(e)}")
            traceback.print_exc()
            print(f"Continuing with next file...\n")
            if status_tracker:
                status_tracker.set_failed(file_path, str(e))
            continue

    print('\n' + '='*80)
    print('--- ALL DONE ---')
    print('='*80)
