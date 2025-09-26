import scipy.io as sio
import numpy as np
import pandas as pd
global REF_IDX, CHANNELS, PLOTQ
REF_IDX = 106 # is using 1x 32 CH and 1x 64 CH grids # !!!OTBio Muovi/Muovi+/Syncstation specific!!!
CHANNELS = [0, 32]# if Grid 1 is 32 CH [36,100] # if 1st grid is 32 CH and 2nd is 64 CH # !!!OTBio Muovi/Muovi+/Syncstation specific!!!
PLOTQ = False
def extract_raw_emg_metadata(mat_path, config, mat_source='otb+'):
    """
    Extracts and structures raw EMG metadata and signals from a .mat file.

    This function reads a `.mat` neurophysiological dataset and extracts:
    - Sampling frequency
    - Inter-electrode distance (IED)
    - Number of EMG channels
    - Reference signal
    - Raw EMG data
    
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

    if mat_source == 'otb+':
        # OTBiolab+ Specific Structure
        ref_path_measured_idx = REF_IDX#106
        idxFrom = int(np.round(config.start_time * config.sampling_frequency))
        idxTo = int(np.round(config.end_time * config.sampling_frequency))

        # Extract reference signal
        refSignal = pd.DataFrame(mat['Data'][idxFrom:idxTo, ref_path_measured_idx])

        # Extract number of channels from the description
        try:
            description0 = mat['Description'][CHANNELS[0]][0][0]
            nCh = int(description0.split(' - ')[2].split(' ')[0][6:8]) * int(description0.split(' - ')[2].split(' ')[0][8:10])
            print(f"Description used: {description0}")
            if nCh%2 == 1:
                nCh = nCh - 1
            print(f" ... exporting {nCh} channels")
        except (KeyError, IndexError, ValueError):
            raise ValueError("Failed to parse channel count from the .mat file description.")

        # Extract raw EMG signal
        rawEMG_Channels = pd.DataFrame(mat["Data"][idxFrom:idxTo, CHANNELS[0]:CHANNELS[1]])

        # Extract sampling frequency and inter-electrode distance
        fsamp = mat['SamplingFrequency'][0][0]
        ied = float(description0.split(' - ')[2].split(' ')[0][2:4])
        print(f" ... IED: {ied}")

        # Extract additional metadata
        extras = pd.DataFrame([
            description0.replace('(1)', ''), 
            mat['Description'][ref_path_measured_idx][0][0], 
            str(config)
        ])
    
    else:
        raise ValueError(f"Unsupported mat_source: {mat_source}. Only 'otb+' is implemented currently.")

    return rawEMG_Channels, refSignal, fsamp, ied, extras

def loadEMG_updConfig(mat, config, mat_source='otb+', n_std=7, sFrom=1, sTo=3):
    """
    Extract raw EMG data from source file and update decomposition configurations.

    This function reads neurophysiological data and adapts the configuration parameters based 
    on the recording metadata (e.g., sampling rate, signal trimming thresholds).

    Args:
        mat (dict): Dictionary containing .mat file data.
        config (Config): Existing configuration object to update.
        mat_source (str, optional): Specifies the source format ('otb+' or 'original'). Defaults to 'otb+'.
        n_std (int, optional): Number of standard deviations for thresholding. Defaults to 7.
        sFrom (int, optional): Baseline force calculation start (in sec). Defaults to 1.
        sTo (int, optional): Baseline force calculation end (in sec). Defaults to 3.

    Returns:
        Tuple[dict, Config]: Updated `.mat` data and modified configuration.
        
    ToDo:
        Implement the selection of good channels.

    Raises:
        ValueError: If `mat_source` is unsupported.
    """
    if mat_source == 'otb+':
        channel_range = CHANNELS # mat reference
        bad_channels = [] # grid reference #10, 11, 24, 37
        ref_path_target_idx = REF_IDX+1#107
        ref_path_measured_idx = REF_IDX#106
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
        print(f"EF: {round(config.extension_factor,2)}")

        # Load neural data
        mat["emg"] = mat["Data"][:, good_channels].transpose()  # needs update based on bad channels

    elif mat_source == 'original':
        # Load neural data from original source
        config.start_time = sFrom
        config.end_time = sTo

    return mat, config