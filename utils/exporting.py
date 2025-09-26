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
    
def allocate_muedit_file_structure():
    """
    Allocates a Python structure compatible with muedit's expected .mat layout.
    You can fill these fields later and save with scipy.io.savemat.

    Top-level variables (each a 1x1 struct in MATLAB):
      - edition
      - parameters
      - signal

    Notes for filling later:
      • MATLAB cell arrays:
          - Use Python lists for 1×N cells (e.g., Pulsetrain).
          - Use numpy object arrays (np.empty((R, C), dtype=object)) for R×C cells
            (e.g., Dischargetimes, silval).
      • Numeric vectors/matrices should be numpy arrays (float).
      • Where sizes are unknown now, placeholders are empty lists or empty arrays.

    Returns:
        dict with keys 'edition', 'parameters', 'signal' (ready for savemat).
    by Harald Penasso 2024-11 (with some help of ChatGPT 5)
    """
    import numpy as np

    # ---- edition (results & timebase) ----
    edition = {
        # 1 x ngrid cell row; each cell: double [nMU_i x n_samples]
        'Pulsetrain': [],
        # ngrid x maxMU cell; each cell: double [1 x nDischarges] (sample indices)
        'Dischargetimes': np.empty((0, 0), dtype=object),
        # ngrid x maxMU cell; each cell: double scalar SIL value
        'silval': np.empty((0, 0), dtype=object),
        # 1 x n_samples double (time in seconds)
        'time': np.empty((0,), dtype=float),
    }

    # ---- parameters (fixed/default algorithm settings) ----
    parameters = {
        'pathname': '',                # char
        'filename': '',                # char
        'NITER': 0.0,                  # double
        'ref_exist': 0.0,              # 1=yes, 0=no
        'checkEMG': 1.0,               # set to 1
        'nwindows': 1.0,               # set to 1
        'differentialmode': 0.0,       # 1=single-diff, 0=mono (set to 0)
        'peeloff': 0.0,                # set to 0
        'covfilter': 0.0,              # set to 0
        'alignMUAP': 0.0,              # set to 0
        'refineMU': 0.0,               # set to 0
        'drawingmode': 1.0,            # set to 1
        'nbelectrodes': 999.0,         # set to 999
        'thresholdtarget': 0.8,        # set to 0.8
        'nbextchan': 1000.0,           # set to 1000
        'edges': 1.0,                  # set to 1
        'contrastfunc': 'logcosh',     # char
        'silthr': 0.88,                # set to 0.88
        'covthr': 0.5,                 # set to 0.5
        'peeloffwin': 0.025,           # set to 0.025
        'duplicatesthresh': 0.3,       # set to 0.3
        'CoVDR': 0.3,                  # set to 0.3
    }

    # ---- signal (raw/aux signals + metadata) ----
    signal = {
        # n_data x n_samples; first EMG (all grids vertically stacked), then reference channels
        'data': np.empty((0, 0), dtype=float),
        # 2 x n_samples; fill with NaN later (kept present for compatibility)
        'bipolar': np.full((2, 0), np.nan),
        # sampling frequency (Hz)
        'fsamp': np.nan,
        # number of recorded channels (n_data + 2 bipolar)
        'nChan': 0.0,
        # number of grids/arrays
        'ngrid': 0.0,
        # 1 x ngrid cell; each cell: grid name string (e.g., 'GR04MM1305')
        'gridname': [],
        # 1 x ngrid cell; each cell: muscle name string
        'muscle': [],
        # 1 x n_samples double: produced path
        'path': np.empty((0,), dtype=float),
        # 1 x n_samples double: target path
        'target': np.empty((0,), dtype=float),
        # 1 x ngrid cell; each cell: [n_grid_channels x 2] double (row, col) 1-based indices
        'coordinates': [],
        # 1 x ngrid double: IED (mm)
        'IED': np.empty((0,), dtype=float),
        # 1 x ngrid cell; each cell: [n_grid_channels x 1] double (0=keep, 1=discard)
        'EMGmask': [],
        # 1 x ngrid double; each entry 1 for surface EMG (per manual)
        'emgtype': [],
        # 1 x ngrid cell row; each cell: double [nMU_i x n_samples]
        'Pulsetrain': [],
        # ngrid x maxMU cell; each cell: double [1 x nDischarges] (sample indices)
        'Dischargetimes': np.empty((0, 0), dtype=object),
    }

    return {'edition': edition, 'parameters': parameters, 'signal': signal}

def export_to_muedit_mat(
    config,
    out_path,
    rawEMG_Channels,
    refSignal,
    ied,
    fsamp,
    fn,
    *,
    # ---- Optional metadata for multi-grid datasets ----
    channel_splits=None,        # list[int]: number of EMG channels for each grid, must sum to rawEMG_Channels.shape[1]
    gridnames=None,             # list[str], len = ngrid (e.g., ['GR04MM1305', 'GR04MM1305'])
    muscles=None,               # list[str], len = ngrid (e.g., ['Tibialis Anterior', 'Soleus'])
    coordinates=None,           # list[np.ndarray], each (n_grid_channels x 2) with 1-based (row, col)
    emgmask=None,               # list[np.ndarray], each (n_grid_channels x 1), 0=keep, 1=discard
    ied_per_grid=None,          # list[float], len = ngrid; overrides scalar 'ied' if provided
    emgtype=None,               # list[float], len = ngrid (1 for surface EMG)
    # Optional auxiliary signals (time-aligned with EMG)
    target_signal=None,         # np.ndarray or pd.Series/DataFrame -> (n_samples,)
    path_signal=None,           # np.ndarray or pd.Series/DataFrame -> (n_samples,)
    # Optional assignment of each MU to a grid (0-based grid indices). Defaults to all on grid 0.
    mu_grid_assignment=None,
    # Optional output name; defaults to out_path with suffix replaced
    save_path=None,
):
    """
    Export the decomposition results to a muedit-compatible .mat.

    Parameters
    ----------
    config : Config
        Your config object (used for some defaults like NITER).
    out_path : str | Path
        Path to the `.pkl` file written by `save_results(...)` (holds 'timestamps', 'silhouettes', etc.).
    rawEMG_Channels : pd.DataFrame or np.ndarray
        EMG signals, shape (n_samples, n_emg_channels)  [time along rows].
    refSignal : pd.DataFrame or np.ndarray or None
        Reference/aux signals, shape (n_samples, n_ref). Use None if not available.
    ied : float
        Inter-electrode distance (mm). Used if `ied_per_grid` is not provided.
    fsamp : float
        Sampling frequency (Hz).
    fn : str | Path
        Full path to the original source file (used to fill parameters.pathname and parameters.filename).

    Keyword-only Parameters
    -----------------------
    channel_splits : list[int], optional
        Number of EMG channels per grid in the vertical concatenation order in `rawEMG_Channels`.
        If omitted, assumes a single grid with all EMG channels.
    gridnames, muscles, coordinates, emgmask, ied_per_grid, emgtype : optional
        Per-grid metadata; see muedit manual. If omitted, reasonable defaults are applied.
    target_signal, path_signal : optional
        1 x time vectors (force target / actual path). If provided, they must be time-aligned to EMG length.
    mu_grid_assignment : list[int] or np.ndarray, optional
        Length = nMU (from decomposition). Each entry gives which grid a MU belongs to (0-based).
        If omitted, all MUs are assigned to grid 0.
    save_path : str | Path, optional
        Where to save the .mat file. Defaults to `out_path` with suffix replaced by `_muedit.mat`.

    Returns
    -------
    Path : pathlib.Path
        Path to the saved .mat file.
    """
    import pickle
    from pathlib import Path
    import warnings
    import numpy as np
    import pandas as pd
    import scipy.io as sio

    # ---------- helpers ----------
    def _to_numpy_2d(x):
        if x is None:
            return None
        if isinstance(x, pd.DataFrame):
            arr = x.to_numpy()
        elif isinstance(x, (pd.Series,)):
            arr = x.to_numpy()[:, None]
        else:
            arr = np.asarray(x)
        if arr.ndim == 1:
            arr = arr[:, None]
        return arr.astype(float, copy=False)

    def _to_numpy_1d(x, n_samples=None):
        if x is None:
            return np.empty((0,), dtype=float)
        if isinstance(x, pd.DataFrame):
            if x.shape[1] != 1:
                raise ValueError("Expected a single-column vector for aux signals.")
            arr = x.iloc[:, 0].to_numpy()
        elif isinstance(x, pd.Series):
            arr = x.to_numpy()
        else:
            arr = np.asarray(x).ravel()
        if n_samples is not None and arr.size and arr.size != n_samples:
            warnings.warn(f"Aux signal length {arr.size} != EMG length {n_samples}. Truncating to min length.")
            m = min(arr.size, n_samples)
            arr = arr[:m]
        return arr.astype(float, copy=False)

    def _as_cell_row(py_list):
        """Return a 1xN object array (MATLAB cell row)."""
        arr = np.empty((1, len(py_list)), dtype=object)
        for i, v in enumerate(py_list):
            arr[0, i] = v
        return arr

    def _ensure_list_len(x, n, default_factory):
        """Ensure a list of length n; if x is None, create with default_factory(i)."""
        if x is None:
            return [default_factory(i) for i in range(n)]
        if len(x) != n:
            raise ValueError(f"Expected list length {n}, got {len(x)}.")
        return x

    # ---------- load decomposition ----------
    out_path = Path(out_path)
    try:
        with open(out_path, "rb") as f:
            decomp = pickle.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Decomposition results file not found: {out_path}")

    # expected keys: 'timestamps' (list per MU), 'silhouettes' (list per MU)
    timestamps_list = []
    for ts in decomp.get("timestamps", []):
        # convert from torch or numpy to 1D np.int64
        if hasattr(ts, "cpu"):
            ts = ts.cpu().numpy()
        ts = np.asarray(ts).astype(np.int64).ravel()
        timestamps_list.append(ts)
    nMU = len(timestamps_list)

    sil_list = []
    if "silhouettes" in decomp and len(decomp["silhouettes"]) == nMU:
        for s in decomp["silhouettes"]:
            if hasattr(s, "cpu"):
                s = s.cpu().numpy()
            s = np.asarray(s).squeeze()
            sil_list.append(float(s))
    else:
        sil_list = [np.nan] * nMU

    # ---------- signals & dimensions ----------
    emg = _to_numpy_2d(rawEMG_Channels)          # (n_samples, n_emg)
    if emg is None or emg.size == 0:
        raise ValueError("rawEMG_Channels is empty.")
    n_samples, n_emg = emg.shape

    ref = _to_numpy_2d(refSignal)                # (n_samples, n_ref)
    n_ref = 0 if ref is None else ref.shape[1]

    # build signal.data (channels x time): EMG (vertically stacked grids) then reference rows
    data = emg.T.astype(float, copy=False)       # (n_emg, n_samples)
    if ref is not None:
        if ref.shape[0] != n_samples:
            # align lengths if needed
            m = min(n_samples, ref.shape[0])
            data = data[:, :m]
            ref = ref[:m, :]
            n_samples = m
            warnings.warn("EMG and Ref length mismatch; truncated to common length.")
        data = np.vstack([data, ref.T])          # (n_emg + n_ref, n_samples)

    # channel bookkeeping per grid
    if channel_splits is None:
        channel_splits = [n_emg]
    if sum(channel_splits) != n_emg:
        raise ValueError(f"channel_splits sum ({sum(channel_splits)}) != number of EMG channels ({n_emg}).")

    ngrid = len(channel_splits)

    # Defaults for per-grid metadata
    if ied_per_grid is None:
        ied_per_grid = [float(ied)] * ngrid
    if gridnames is None:
        # Leave generic names; change to your actual grid IDs as needed.
        gridnames = [f"GR{int(round(ied_per_grid[i])):02d}MM????" for i in range(ngrid)]
    if muscles is None:
        muscles = ["Not defined"] * ngrid
    if emgtype is None:
        emgtype = [1.0] * ngrid  # 1 = surface EMG

    # Coordinates & masks defaults
    # For each grid i: coordinates[i] is (n_grid_channels x 2), 1-based (row, col)
    #                  emgmask[i] is (n_grid_channels x 1), 0=keep, 1=discard
    def _coord_default(i):
        return np.full((channel_splits[i], 2), np.nan, dtype=float)

    def _mask_default(i):
        return np.zeros((channel_splits[i], 1), dtype=float)

    coordinates = _ensure_list_len(coordinates, ngrid, _coord_default)
    emgmask     = _ensure_list_len(emgmask,     ngrid, _mask_default)

    # ---------- MU grid assignment ----------
    if mu_grid_assignment is None:
        mu_grid_assignment = np.zeros((nMU,), dtype=int)
    else:
        mu_grid_assignment = np.asarray(mu_grid_assignment, dtype=int).ravel()
        if mu_grid_assignment.size != nMU:
            raise ValueError("mu_grid_assignment length must equal number of MUs.")
        if np.any((mu_grid_assignment < 0) | (mu_grid_assignment >= ngrid)):
            raise ValueError("mu_grid_assignment contains invalid grid indices.")

    # ---------- build Pulsetrains (binary) & Discharge times ----------
    # Build a global binary matrix first: (nMU x n_samples)
    pulses_global = np.zeros((nMU, n_samples), dtype=float)
    for i, idx in enumerate(timestamps_list):
        # keep only indices that fall within [0, n_samples-1]
        valid = idx[(idx >= 0) & (idx < n_samples)]
        if valid.size < idx.size:
            warnings.warn(f"MU {i}: some timestamps outside [0, {n_samples-1}] were ignored.")
        pulses_global[i, valid] = 1.0

    # Per-grid packing
    mu_indices_by_grid = [np.where(mu_grid_assignment == g)[0].tolist() for g in range(ngrid)]
    pulsetrain_per_grid = []
    for g, mu_idx in enumerate(mu_indices_by_grid):
        if len(mu_idx) == 0:
            pulsetrain_per_grid.append(np.zeros((0, n_samples), dtype=float))
        else:
            pulsetrain_per_grid.append(pulses_global[mu_idx, :])

    maxMU = max((len(mu_idx) for mu_idx in mu_indices_by_grid), default=0)
    # Cell arrays (ngrid x maxMU)
    disc_cell = np.empty((ngrid, maxMU), dtype=object)
    sil_cell  = np.empty((ngrid, maxMU), dtype=object)
    disc_cell[:] = None
    sil_cell[:]  = None

    for g, mu_idx in enumerate(mu_indices_by_grid):
        for j, mu_id in enumerate(mu_idx):
            # MATLAB is 1-based; muedit expects sample indices (1..n_samples)
            disc_times = timestamps_list[mu_id]
            disc_times = disc_times[(disc_times >= 0) & (disc_times < n_samples)]
            disc_cell[g, j] = (disc_times.astype(float) + 1.0).reshape(1, -1)
            sil_cell[g, j]  = float(sil_list[mu_id])

    # ---------- allocate & populate muedit structure ----------
    muedit = allocate_muedit_file_structure()  # uses your previously defined allocator

    # edition
    muedit['edition']['Pulsetrain']     = _as_cell_row(pulsetrain_per_grid)
    muedit['edition']['Dischargetimes'] = disc_cell
    muedit['edition']['silval']         = sil_cell
    muedit['edition']['time']           = (np.arange(n_samples, dtype=float) / float(fsamp)).reshape(1, -1)

    # parameters (defaults per manual, a few inferred from config)
    src_path = Path(fn)
    muedit['parameters']['pathname']   = str(src_path.parent)
    muedit['parameters']['filename']   = src_path.name
    muedit['parameters']['NITER']      = float(getattr(config, 'max_iterations', 0))
    muedit['parameters']['ref_exist']  = 1.0 if (ref is not None and ref.size > 0) else 0.0
    muedit['parameters']['checkEMG']   = 1.0
    muedit['parameters']['nwindows']   = 1.0
    muedit['parameters']['differentialmode'] = 0.0
    muedit['parameters']['peeloff']    = 0.0
    muedit['parameters']['covfilter']  = 0.0
    muedit['parameters']['alignMUAP']  = 0.0
    muedit['parameters']['refineMU']   = 0.0
    muedit['parameters']['drawingmode']= 1.0
    muedit['parameters']['nbelectrodes']= 999.0
    muedit['parameters']['thresholdtarget'] = 0.8
    muedit['parameters']['nbextchan']  = 1000.0
    muedit['parameters']['edges']      = 1.0
    muedit['parameters']['contrastfunc']= 'logcosh'
    muedit['parameters']['silthr']     = 0.88
    muedit['parameters']['covthr']     = 0.5
    muedit['parameters']['peeloffwin'] = 0.025
    muedit['parameters']['duplicatesthresh'] = 0.3
    muedit['parameters']['CoVDR']      = 0.3

    # signal
    n_data_rows = data.shape[0]                    # EMG + ref rows
    muedit['signal']['data']        = data.astype(float, copy=False)
    muedit['signal']['bipolar']     = np.full((2, n_samples), np.nan, dtype=float)
    muedit['signal']['fsamp']       = float(fsamp)
    muedit['signal']['nChan']       = float(n_data_rows + 2)  # +2 bipolar (per manual)
    muedit['signal']['ngrid']       = float(ngrid)
    muedit['signal']['gridname']    = _as_cell_row(gridnames)
    muedit['signal']['muscle']      = _as_cell_row(muscles)
    muedit['signal']['IED']         = np.asarray(ied_per_grid, dtype=float).reshape(1, -1)
    muedit['signal']['EMGmask']     = _as_cell_row(emgmask)
    muedit['signal']['emgtype']     = np.asarray(emgtype, dtype=float).reshape(1, -1)
    muedit['signal']['coordinates']  = _as_cell_row(coordinates)

    # Optional target / path
    muedit['signal']['target'] = _to_numpy_1d(target_signal, n_samples).reshape(1, -1)
    muedit['signal']['path']   = _to_numpy_1d(path_signal,   n_samples).reshape(1, -1)

    # Duplicated MU info in 'signal' (per muedit sample structure)
    muedit['signal']['Pulsetrain']     = _as_cell_row(pulsetrain_per_grid)
    muedit['signal']['Dischargetimes'] = disc_cell

    # ---------- save ----------
    if save_path is None:
        save_path = Path(str(out_path).replace('.pkl', '_muedit.mat'))
    else:
        save_path = Path(save_path)

    sio.savemat(
        save_path,
        muedit,
        do_compression=True,
        long_field_names=True,
    )

    print(f"Saved muedit .mat to {save_path}")
    return save_path
