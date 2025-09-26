"""Functions for exporting decomposition outputs"""

import os
import sys
import pickle
import numpy as np
import pandas as pd
import scipy.io as sio
from pathlib import Path


def allocate_openhdemg_file_structure():
    """
    Allocates and returns a dictionary of the openhdemg file structure.
    
    This file structure is used for storing high-density surface electromyography (HD-sEMG) data
    decomposed into single motor unit firings. The dictionary contains various types of data
    including raw HDEMG signals, reference signals, accuracy metrics, and more.

    The dictionary contains the following keys:
    - 'SOURCE': str, any length. Context: Decomposition tool used.
    - 'FILENAME': str, any length. Context: Filename of the data file that was decomposed.
    - 'RAW_SIGNAL': pandas DataFrame, each with shape (nSamp, nCh). Context: Raw sEMG signals.
    - 'REF_SIGNAL': pandas DataFrame, each with shape (nSamp, 1). Context: Reference force/torque signal.
    - 'ACCURACY': pandas DataFrame, each with shape (nMU, 1). Context: Accuracy of motor unit decomposition, i.e., SIL.
    - 'IPTS': pandas DataFrame, each with shape (nSamp, nMU). Context: Motor unit spike trains.
    - 'MUPULSES': list of numpy arrays, each entry a numpy array of int32 with shape (nFirings,). Context: Motor unit pulse timings as indices.
    - 'FSAMP': float, each with one value. Context: sEMG sampling frequency [Hz].
    - 'IED': float, each with one value. Context: Inter-electrode distance [mm].
    - 'EMG_LENGTH': int, each with one value corresponding to nSamp. Context: Length of the EMG signal.
    - 'NUMBER_OF_MUS': int, each with one value corresponding to nMU. Context: Number of motor units.
    - 'BINARY_MUS_FIRING': pandas DataFrame, each with shape (nSamp, nMU). Context: Binary matrix of motor unit firings.
    - 'EXTRAS': pandas DataFrame, each with shape (nExtras, 1). Context: Any additional information.
    (nSamp ... number of samples, nMU ... number of motor units, nCH ... number of sEMG channels)
    
    Returns:
        dict: A dictionary with the specified structure and empty lists for each key.
        
    by Harald Penasso 2024-11 (with some help of ChatGPT 4o)
    """
    decompfile = {
        'SOURCE': [],  # str (any length)
        'FILENAME': [],  # str (any length)
        'RAW_SIGNAL': [],  # DataFrame (nSamp, nCh)
        'REF_SIGNAL': [],  # DataFrame (nSamp, 1)
        'ACCURACY': [],  # DataFrame (nMU, 1)
        'IPTS': [],  # DataFrame (nSamp, nMU)
        'MUPULSES': [],  # list nMU (each entry a numpy array of int32 (nFirings,))
        'FSAMP': [],  # float 1
        'IED': [],  # float 1
        'EMG_LENGTH': [],  # int 1 (one value corresponding to nSamp)
        'NUMBER_OF_MUS': [],  # int 1 (one value corresponding to nMU)
        'BINARY_MUS_FIRING': [],  # DataFrame (nSamp, nMU)
        'EXTRAS': []  # DataFrame (nExtras, 1)
    }
    
    return decompfile

def export_to_openhdemg_json(config, out_path, rawEMG_Channels, refSignal, ied, fsamp, fn, extras = '', device_from = 'OTB'):
    """
    Export the decomposition results to the OpenHD-EMG JSON format.
    
    This function converts the decomposition outputs from the Swarm-Contrastive Decomposition pipeline 
    into the standardized OpenHD-EMG format for further analysis.

    Args:
        config (Config): Configuration object containing settings like start_time, sampling_frequency, etc.
        out_path (str): Path to the `.pkl` file containing decomposition results.
        rawEMG_Channels (pd.DataFrame): EMG channel signals extracted from the dataset.
        refSignal (pd.DataFrame): The reference signal, typically force or torque.
        ied (float): Inter-electrode distance in mm.
        fsamp (float): Sampling frequency in Hz.
        fn (str): Filename of the processed dataset.
        extras (str, optional): Additional metadata. Defaults to an empty string.
        device_from (str, optional): Source identifier for the data. Defaults to 'OTB'.

    Returns:
        None: Saves the data in JSON format.

    Raises:
        FileNotFoundError: If `out_path` is missing.
        ValueError: If unexpected data formats are encountered.

    Example:
        >>> export_to_openhdemg_json(config, 'output.pkl', rawEMG_Channels, refSignal, 5, 2000, 'subject1')
        Saved results to output.json in OpenHD-EMG compressed format.
    """

    import openhdemg.library as emg
    
    # Load decomposition results
    try:
        with open(out_path, 'rb') as f:
            decomp = pickle.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Decomposition results file not found: {out_path}")
    
    # Allocate structure
    decompfile = allocate_openhdemg_file_structure()

    # Populate structured dictionary
    decompfile['SOURCE'] = device_from
    decompfile['FILENAME'] = fn
    decompfile['RAW_SIGNAL'] = rawEMG_Channels
    decompfile['REF_SIGNAL'] = refSignal
    decompfile['ACCURACY'] = pd.DataFrame([sil.cpu().numpy() for sil in decomp['silhouettes']])
    decompfile['IPTS'] = pd.DataFrame(np.array(decomp['source'])[:, :, 0].T)
    decompfile['MUPULSES'] = [np.array(mup.cpu(), dtype='int32') for mup in decomp['timestamps']]
    decompfile['FSAMP'] = fsamp
    decompfile['IED'] = ied
    decompfile['EMG_LENGTH'] = decompfile['IPTS'].shape[0]
    decompfile['NUMBER_OF_MUS'] = len(decomp['silhouettes'])

    # Create binary firing matrix
    spikeMat = np.zeros((decompfile['NUMBER_OF_MUS'], decompfile['EMG_LENGTH']))
    for i in range(decompfile['NUMBER_OF_MUS']):
        spikeMat[i, decompfile['MUPULSES'][i]] = 1

    decompfile['BINARY_MUS_FIRING'] = pd.DataFrame(spikeMat.T)
    decompfile['EXTRAS'] = extras

    # Save the file
    output_json_path = Path(str(out_path).replace('.pkl', '.json'))
    emg.save_json_emgfile(decompfile, output_json_path, compresslevel=4)
    print(f"Saved results to {output_json_path} in OpenHD-EMG compressed JSON format.")