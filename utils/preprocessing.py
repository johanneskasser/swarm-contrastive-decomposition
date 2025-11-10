import scipy.io as sio
import numpy as np
import pandas as pd
import json
from pathlib import Path
global PLOTQ # REF_IDX, CHANNELS
#REF_IDX = 70 # is using 1x 32 CH and 1x 64 CH grids # !!!OTBio Muovi/Muovi+/Syncstation specific!!!
#CHANNELS = [0, 64]# if Grid 1 is 32 CH [36,100] # if 1st grid is 32 CH and 2nd is 64 CH # !!!OTBio Muovi/Muovi+/Syncstation specific!!!
PLOTQ = False # !!set!!
def extract_raw_emg_metadata(mat_path, config, mat_source='otb+'):
    """
    Extracts and structures raw EMG metadata and signals from a .mat file.

    This function reads a `.mat` neurophysiological dataset and extracts:
    - Sampling frequency
    - Inter-electrode distance (IED)
    - Number of EMG channels
    - Reference signal
    - Raw EMG data
    
    Extracts from config:
    - channel_range (list of size 1,2): EMG channel indices from ... to
    - ref_path_measured_idx (int): index of the measured performed path of the force/torque reference
    
    Args:
        mat_path (str or Path): Path to the .mat file.
        config (Config): Configuration object containing settings such as start_time and sampling_frequency.
        mat_source (str, optional): Specifies the `.mat` file format ('otb+' only currently). Defaults to 'otb+'.

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame, float, float, pd.DataFrame]: 
        - `rawEMG_Channels` (pd.DataFrame): Extracted EMG signal.
        - `refSignal` (pd.DataFrame): Extracted reference force/torque signal.
        - `fsamp` (float): Sampling frequency.
        - `ied` (float): Inter-electrode distance in mm.
        - `extras` (pd.DataFrame): Additional metadata extracted from the file.
    
    Raises:
        FileNotFoundError: If the provided `.mat` file is not found.
        ValueError: If the file format is incorrect or does not contain expected fields.

    Example:
        >>> rawEMG, refSignal, fsamp, ied, extras = extract_raw_emg_metadata("data.mat", config)
        >>> print(fsamp, ied)
    """
    try:
        mat = sio.loadmat(mat_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"MAT file not found at {mat_path}")
    channel_range = config.channel_range
    ref_path_measured_idx = config.ref_path_measured_idx
    if mat_source == 'otb+':
        # OTBiolab+ Specific Structure
        idxFrom = int(np.round(config.start_time * config.sampling_frequency))
        idxTo = int(np.round(config.end_time * config.sampling_frequency))

        # Extract reference signal
        refSignal = pd.DataFrame(mat['Data'][idxFrom:idxTo, ref_path_measured_idx])

        # Extract number of channels from the description
        try:
            description0 = mat['Description'][channel_range[0]][0][0]
            # Convert numpy array to string if necessary
            if isinstance(description0, np.ndarray):
                description0 = str(description0[0]) if description0.size > 0 else str(description0)
            nCh = int(description0.split(' - ')[2].split(' ')[0][6:8]) * int(description0.split(' - ')[2].split(' ')[0][8:10])
            print(f"Description used: {description0}")
            if nCh%2 == 1:
                nCh = nCh - 1
            print(f" ... exporting {nCh} channels")
        except (KeyError, IndexError, ValueError):
            raise ValueError("Failed to parse channel count from the .mat file description.")

        # Extract raw EMG signal
        rawEMG_Channels = pd.DataFrame(mat["Data"][idxFrom:idxTo, channel_range[0]:channel_range[1]])

        # Extract sampling frequency and inter-electrode distance
        fsamp = mat['SamplingFrequency'][0][0]

        # Try to get IED from grid_info if available, otherwise from description
        if hasattr(config, 'grid_info') and config.grid_info is not None:
            ied = config.grid_info.get('inter_electrode_distance_mm', 8)
            print(f" ... IED from grid_info: {ied}")
        else:
            ied = float(description0.split(' - ')[2].split(' ')[0][2:4])
            print(f" ... IED from description: {ied}")

        # Extract additional metadata
        extras = pd.DataFrame([
            description0.replace('(1)', ''), 
            mat['Description'][ref_path_measured_idx][0][0], 
            str(config)
        ])
    
    else:
        raise ValueError(f"Unsupported mat_source: {mat_source}. Only 'otb+' is implemented currently.")

    return rawEMG_Channels, refSignal, fsamp, ied, extras

def loadEMG_updConfig(mat, config, channel_range, ref_path_target_idx, ref_path_measured_idx, bad_channels = [], mat_source='otb+', n_std=7, sFrom=1, sTo=3, PLOTQ=False, grid_info=None):
    """
    Extract raw EMG data from source file and update decomposition configurations.

    This function reads neurophysiological data and adapts the configuration parameters based
    on the recording metadata (e.g., sampling rate, signal trimming thresholds).

    Args:
        mat (dict): Dictionary containing .mat file data.
        config (Config): Existing configuration object to update.
        channel_range (list of size 1,2): EMG channel indices from ... to.
                      Can be overridden by grid_info if provided.
        ref_path_target_idx (int): index to target path.
        ref_path_measured_idx (int): index to performed path.
        bad_channels (list): channel number to be removed. Defaults to [].
                           Can be overridden by grid_info if provided.
        mat_source (str, optional): Specifies the source format ('otb+' or 'original'). Defaults to 'otb+'.
        n_std (int, optional): Number of standard deviations for thresholding. Defaults to 7.
        sFrom (int, optional): Baseline force calculation start (in sec). Defaults to 1.
        sTo (int, optional): Baseline force calculation end (in sec). Defaults to 3.
        grid_info (dict, optional): Grid information from channel selection JSON.
                                   If provided, overrides channel_range and bad_channels.

    Returns:
        Tuple[dict, Config]: Updated `.mat` data and modified configuration.

    Raises:
        ValueError: If `mat_source` is unsupported.

    Note:
        If grid_info is provided, channel_range and bad_channels from grid_info will override
        the function parameters, ensuring compatibility with hdsemg-select channel selection.
    """
    if mat_source == 'otb+':
        # If grid_info is provided, use it to override channel_range and bad_channels
        if grid_info is not None:
            _, bad_channels, channel_range, grid_ied = get_good_channels_from_grid(grid_info)
            print(f"Using channel selection from JSON (grid: {grid_info.get('grid_key', 'unknown')})")
            # Store grid_info in config for later use (e.g., in extract_raw_emg_metadata)
            config.grid_info = grid_info

        # Create the full list of channels
        all_channels = list(range(channel_range[0], channel_range[1]))
        # Filter out channels at indices specified in bad_channels
        good_channels = [ch for idx, ch in enumerate(all_channels) if idx not in bad_channels]
        print(f"Good channels used:\n {good_channels}")
        fsamp = int(mat['SamplingFrequency'][0][0])
        ref_path_target = mat['Data'][:, ref_path_target_idx]
        ref_path_measured = mat['Data'][:, ref_path_measured_idx]
        if PLOTQ:
            import matplotlib.pyplot as plt
            plt.plot(ref_path_target)
            plt.plot(ref_path_measured)
            plt.show()
            for i, goodCh in enumerate(good_channels):
                plt.plot(i+mat['Data'][:, goodCh]/(max(mat['Data'][:, goodCh])*1.3))
            plt.show()
        # Compute thresholds
        baseline_start = ref_path_measured[int(fsamp) * sFrom:int(fsamp * sTo)]
        threshold_start = baseline_start.mean() + baseline_start.std() * n_std

        baseline_end = ref_path_measured[::-1][int(fsamp) * sFrom:int(fsamp * sTo)]
        threshold_end = baseline_end.mean() + baseline_end.std() * n_std

        force_threshold = (threshold_start + threshold_end) / 2

        # Adjust config
        if sum(ref_path_target)==0:
            config.start_time = 0
            config.end_time = ref_path_target.shape[0]
        else:
            config.end_time = (1 + ref_path_target.shape[0] - np.where(ref_path_target[::-1] > force_threshold)[0][0]) / fsamp
            config.start_time = np.where(ref_path_target > force_threshold)[0][0] / fsamp
        config.sampling_frequency = fsamp
        n_good_channels = len(good_channels)
        config.extension_factor = int(np.round(1000 / n_good_channels))
        config.channel_range = channel_range
        config.ref_path_target_idx = ref_path_target_idx
        config.ref_path_measured_idx = ref_path_measured_idx
        config.bad_channels = bad_channels
        # ToDo Add all other decomposition settings to config to be saved in openhdemg EXTRAS later on
        print(f"EF: {round(config.extension_factor,2)}")

        # Load neural data
        mat["emg"] = mat["Data"][:, good_channels].transpose()  # needs update based on bad channels

    elif mat_source == 'original':
        # Load neural data from original source
        config.start_time = sFrom
        config.end_time = sTo

    return mat, config

def load_channel_selection_json(mat_path):
    """
    Load channel selection JSON file created by hdsemg-select app.

    Args:
        mat_path (str or Path): Path to the .mat file.

    Returns:
        dict or None: JSON data if file exists, None otherwise.
    """
    mat_path = Path(mat_path)
    json_path = mat_path.with_suffix('.json')

    if json_path.exists():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"Loaded channel selection from: {json_path}")
            return data
        except Exception as e:
            print(f"Warning: Could not load channel selection JSON: {e}")
            return None
    else:
        print(f"No channel selection JSON found at: {json_path}")
        return None

def get_grids_from_json(json_data):
    """
    Extract grid information from channel selection JSON.

    Args:
        json_data (dict): Channel selection JSON data.

    Returns:
        list: List of grid dictionaries, each containing grid metadata and channels.
    """
    if json_data is None or 'grids' not in json_data:
        return []

    grids = []
    for grid in json_data['grids']:
        grid_info = {
            'grid_key': grid.get('grid_key', 'unknown'),
            'rows': grid.get('rows', 0),
            'columns': grid.get('columns', 0),
            'inter_electrode_distance_mm': grid.get('inter_electrode_distance_mm', 8),
            'channels': grid.get('channels', [])
        }
        grids.append(grid_info)

    print(f"Found {len(grids)} grid(s) in channel selection JSON:")
    for grid in grids:
        n_channels = len(grid['channels'])
        n_selected = sum(1 for ch in grid['channels'] if ch.get('selected', False))
        print(f"  - {grid['grid_key']}: {n_selected}/{n_channels} channels selected")

    return grids

def get_good_channels_from_grid(grid_info):
    """
    Extract good (selected) channels from a grid.

    Args:
        grid_info (dict): Grid dictionary with channel information.

    Returns:
        tuple: (channel_indices, bad_channel_indices, channel_range, ied)
            - channel_indices: List of global channel indices that are selected (good)
            - bad_channel_indices: List of indices within channel_range that are bad
            - channel_range: [first_channel_index, last_channel_index + 1]
            - ied: Inter-electrode distance in mm
    """
    channels = grid_info['channels']
    if not channels:
        return [], [], [0, 0], 8

    # Get all channel indices and filter for selected ones
    all_indices = [ch['channel_index'] for ch in channels]
    good_indices = [ch['channel_index'] for ch in channels if ch.get('selected', False)]

    # Calculate channel range
    min_idx = min(all_indices)
    max_idx = max(all_indices)
    channel_range = [min_idx, max_idx + 1]

    # Calculate bad channel indices (relative to channel_range start)
    bad_indices = []
    for ch in channels:
        if not ch.get('selected', False):
            relative_idx = ch['channel_index'] - min_idx
            bad_indices.append(relative_idx)

    ied = grid_info.get('inter_electrode_distance_mm', 8)

    print(f"\nGrid '{grid_info['grid_key']}':")
    print(f"  Channel range: {channel_range}")
    print(f"  Good channels: {len(good_indices)}/{len(channels)}")
    print(f"  Bad channel indices (relative): {bad_indices}")
    print(f"  IED: {ied} mm")

    return good_indices, bad_indices, channel_range, ied