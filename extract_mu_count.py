import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any


def parse_algorithm_params(content: str) -> Optional[Dict[str, Any]]:
    """
    Parse algorithm parameters from log file header.

    Args:
        content: Full log file content

    Returns:
        Dictionary of algorithm parameters or None if not found
    """
    # Check if ALGORITHM PARAMETERS section exists
    if 'ALGORITHM PARAMETERS:' not in content:
        return None

    params = {}

    # Pattern for each parameter line: "  param_name:    value"
    param_patterns = {
        'acceptance_silhouette': r'acceptance_silhouette:\s+([\d.]+)',
        'max_iterations': r'max_iterations:\s+(\d+)',
        'sampling_frequency': r'sampling_frequency:\s+(\d+)',
        'remove_bad_fr': r'remove_bad_fr:\s+(True|False)',
        'low_pass_cutoff': r'low_pass_cutoff:\s+(\d+)',
        'high_pass_cutoff': r'high_pass_cutoff:\s+(\d+)',
        'extension_factor': r'extension_factor:\s+(\d+)',
        'peel_off_window_size_ms': r'peel_off_window_size_ms:\s+(\d+)',
        'notch_params': r'notch_params:\s+\[([^\]]+)\]',
        'time_differentiate': r'time_differentiate:\s+(True|False)',
        'use_coeff_var_fitness': r'use_coeff_var_fitness:\s+(True|False)',
        'clamp_percentile': r'clamp_percentile:\s+([\d.]+)',
        'output_final_source_plot': r'output_final_source_plot:\s+(True|False)',
    }

    for param_name, pattern in param_patterns.items():
        match = re.search(pattern, content)
        if match:
            value_str = match.group(1)
            # Convert to appropriate type
            if param_name in ('remove_bad_fr', 'time_differentiate', 'use_coeff_var_fitness', 'output_final_source_plot'):
                params[param_name] = value_str == 'True'
            elif param_name in ('max_iterations', 'sampling_frequency', 'low_pass_cutoff', 'high_pass_cutoff', 'extension_factor', 'peel_off_window_size_ms'):
                params[param_name] = int(value_str)
            elif param_name in ('acceptance_silhouette', 'clamp_percentile'):
                params[param_name] = float(value_str)
            elif param_name == 'notch_params':
                # Parse list: "50, 1.0, True"
                parts = [p.strip() for p in value_str.split(',')]
                if len(parts) == 3:
                    params[param_name] = [int(parts[0]), float(parts[1]), parts[2].strip() == 'True']
            else:
                params[param_name] = value_str

    return params if params else None


def parse_log_file(log_path) -> Tuple[List[Dict], Optional[Dict[str, Any]]]:
    """
    Parse log file and extract MU counts per file and grid, plus algorithm parameters.

    Args:
        log_path: Path to the log file

    Returns:
        Tuple of (results_list, algorithm_params_dict)
        results_list: list of dicts with structure:
            [{'file': 'bl1_trap1.mat', 'grid': '10mm_4x8', 'mus': 0, 'status': 'success'},
             {'file': 'bl1_trap1.mat', 'grid': '8mm_5x13', 'mus': 4, 'status': 'success'},
             {'file': 'bl4_pyr1.mat', 'grid': '8mm_5x13', 'mus': None, 'status': 'failed'}]
        algorithm_params_dict: Dict of algorithm parameters or None if not found
    """
    with open(log_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse algorithm parameters from header
    algorithm_params = parse_algorithm_params(content)

    results = []

    # Find all file processing blocks
    file_pattern = r'Processing file: ([\w_]+\.mat)'
    file_matches = list(re.finditer(file_pattern, content))

    for i, file_match in enumerate(file_matches):
        filename = file_match.group(1)

        # Determine the end of this file's block (start of next file or end of log)
        start_pos = file_match.start()
        end_pos = file_matches[i + 1].start() if i + 1 < len(file_matches) else len(content)
        file_block = content[start_pos:end_pos]

        # Find all grid processing blocks within this file
        grid_pattern = r'Processing grid \d+/\d+: ([\w_]+)'
        grid_matches = list(re.finditer(grid_pattern, file_block))

        for j, grid_match in enumerate(grid_matches):
            grid_name = grid_match.group(1)

            # Determine grid block boundaries
            grid_start = grid_match.start()
            grid_end = grid_matches[j + 1].start() if j + 1 < len(grid_matches) else len(file_block)
            grid_block = file_block[grid_start:grid_end]

            # Check if grid processing failed
            if '[ERROR] Failed to process grid' in grid_block:
                results.append({
                    'file': filename,
                    'grid': grid_name,
                    'mus': None,
                    'status': 'failed'
                })
            else:
                # Count "accept new source" occurrences
                accept_pattern = r'\d+: accept new source\.'
                mu_count = len(re.findall(accept_pattern, grid_block))

                results.append({
                    'file': filename,
                    'grid': grid_name,
                    'mus': mu_count,
                    'status': 'success'
                })

    return results, algorithm_params

def write_results(results, output_path, algorithm_params=None):
    """Write results to a text file with clear formatting.

    Args:
        results: List of result dictionaries
        output_path: Path to output file
        algorithm_params: Optional dict of algorithm parameters
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        # Write header
        f.write("=" * 80 + "\n")
        f.write("HD-sEMG Motor Unit Extraction Summary\n")
        f.write("=" * 80 + "\n\n")

        # Write algorithm parameters section if available
        if algorithm_params:
            f.write("Algorithm Parameters:\n")
            f.write("-" * 80 + "\n")
            # Sort parameters for consistent output
            param_order = [
                'acceptance_silhouette', 'max_iterations', 'sampling_frequency',
                'remove_bad_fr', 'low_pass_cutoff', 'high_pass_cutoff',
                'extension_factor', 'peel_off_window_size_ms', 'notch_params',
                'time_differentiate', 'use_coeff_var_fitness', 'clamp_percentile',
                'output_final_source_plot'
            ]
            for param in param_order:
                if param in algorithm_params:
                    f.write(f"  {param:<28s}: {algorithm_params[param]}\n")
            f.write("\n")

        # Group by file
        files = {}
        for r in results:
            if r['file'] not in files:
                files[r['file']] = []
            files[r['file']].append(r)

        # Write file-by-file summary
        total_mus = 0
        total_grids = 0
        failed_grids = 0

        for filename in sorted(files.keys()):
            f.write(f"File: {filename}\n")
            f.write("-" * 80 + "\n")

            file_mus = 0
            for grid_result in files[filename]:
                grid_name = grid_result['grid']
                total_grids += 1

                if grid_result['status'] == 'failed':
                    f.write(f"  Grid: {grid_name:20s} - FAILED\n")
                    failed_grids += 1
                else:
                    mus = grid_result['mus']
                    f.write(f"  Grid: {grid_name:20s} - {mus:3d} MUs\n")
                    file_mus += mus
                    total_mus += mus

            f.write(f"  {'Subtotal:':<20s}   {file_mus:3d} MUs\n")
            f.write("\n")

        # Write summary statistics
        f.write("=" * 80 + "\n")
        f.write("Summary Statistics\n")
        f.write("=" * 80 + "\n")
        f.write(f"Total files processed:  {len(files)}\n")
        f.write(f"Total grids processed:  {total_grids}\n")
        f.write(f"Failed grids:           {failed_grids}\n")
        f.write(f"Successful grids:       {total_grids - failed_grids}\n")
        f.write(f"Total MUs extracted:    {total_mus}\n")

def write_csv(results, output_path):
    """Write results as CSV for further analysis."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("File,Grid,MUs,Status\n")
        for r in results:
            mus = r['mus'] if r['mus'] is not None else 'N/A'
            f.write(f"{r['file']},{r['grid']},{mus},{r['status']}\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_mu_counts.py <log_file_path>")
        print("Example: python extract_mu_counts.py log.txt")
        sys.exit(1)

    log_path = Path(sys.argv[1])

    if not log_path.exists():
        print(f"Error: File '{log_path}' not found!")
        sys.exit(1)

    print(f"Parsing log file: {log_path}")
    results, algorithm_params = parse_log_file(log_path)

    # Generate output filenames
    output_txt = log_path.parent / f"{log_path.stem}_mu_summary.txt"
    output_csv = log_path.parent / f"{log_path.stem}_mu_summary.csv"

    # Write outputs (include algorithm parameters in txt summary)
    write_results(results, output_txt, algorithm_params)
    write_csv(results, output_csv)

    print(f"\nResults written to:")
    print(f"  - {output_txt}")
    print(f"  - {output_csv}")

    if algorithm_params:
        print(f"\nAlgorithm parameters found in log:")
        print(f"  acceptance_silhouette: {algorithm_params.get('acceptance_silhouette', 'N/A')}")
        print(f"  max_iterations: {algorithm_params.get('max_iterations', 'N/A')}")

    print(f"\nTotal MUs extracted: {sum(r['mus'] for r in results if r['mus'] is not None)}")
    print(f"Total grids: {len(results)}")
    print(f"Failed grids: {sum(1 for r in results if r['status'] == 'failed')}")

if __name__ == "__main__":
    main()