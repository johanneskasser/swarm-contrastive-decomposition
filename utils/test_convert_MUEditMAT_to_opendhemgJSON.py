# -*- coding: utf-8 -*-
"""
Created on Sun Sep 28 17:17:12 2025

@author: harald.penasso
"""
#%%
from pathlib import Path
import numpy as np
import pandas as pd
import h5py
import openhdemg.library as emg

#%%
in_json  = "C:\GitHub\swarm-contrastive-decomposition\data\output\PeHaOf20241107163930_Ramp01.json"
in_mat   = "C:\GitHub\swarm-contrastive-decomposition\data\output\PeHaOf20241107163930_Ramp01_muedit_edited.mat"
out_json = "C:\GitHub\swarm-contrastive-decomposition\data\output\PeHaOf20241107163930_Ramp01_edited.json"

json_in_path = Path(in_json)
mat_edited_path = Path(in_mat)
json_out_path = Path(out_json)
#%%
# --- Load original OpenHD-EMG JSON via the same library routines you use elsewhere ---
json_dict_orig = emg.emg_from_json(json_in_path)
json_dict_upd = json_dict_orig.copy()
#%%
def _is_valid_ref(ref):
    """True for a non-null HDF5 object reference."""
    import h5py as _h5py
    return isinstance(ref, _h5py.Reference) and bool(ref)

def _cell_row_read(f, ds):
    """
    Read a MATLAB 1xN (or Nx1) cell array dataset into a Python list of arrays.
    Assumes v7.3 (HDF5). Elements are object references.
    """
    obj = ds[()]
    if obj.ndim != 2:
        raise ValueError(f"Expected 2-D cell array, got {obj.ndim}D.")
    # normalize to a row
    if obj.shape[0] == 1:
        refs = [obj[0, j] for j in range(obj.shape[1])]
    elif obj.shape[1] == 1:
        refs = [obj[i, 0] for i in range(obj.shape[0])]
    else:
        # still handle as row-major
        refs = [obj[0, j] for j in range(obj.shape[1])]

    out = []
    for r in refs:
        if _is_valid_ref(r):
            arr = np.array(f[r])
            out.append(arr)
        else:
            out.append(None)
    return out

def _cell_matrix_read(f, ds):
    """
    Read a MATLAB (ngrid x maxMU) cell array dataset into nested lists:
      nested[g][j] -> np.ndarray or None
    """
    obj = ds[()]
    if obj.ndim != 2:
        raise ValueError(f"Expected 2-D cell matrix, got {obj.ndim}D.")
    G, J = obj.shape
    nested = [[None for _ in range(J)] for _ in range(G)]
    for g in range(G):
        for j in range(J):
            r = obj[g, j]
            if _is_valid_ref(r):
                nested[g][j] = np.array(f[r])
            else:
                nested[g][j] = None
    return nested

# --- Read edited muedit MAT (v7.3) using h5py ---
with h5py.File(mat_edited_path, 'r') as f:
    if 'edition' not in f:
        # Some MATLAB saves nest structs; common name is '/edition'
        raise KeyError(f"'edition' group not found in {mat_edited_path}")
    edit = f['edition']
    
    # SIL: 1 x ngrid cell, each double
    if 'silval' not in edit:
        raise KeyError("edition.silval not found in edited MAT.")
    silval = _cell_row_read(f, edit['silval'])
    
    # Pulsetrain: 1 x ngrid cell; each cell: (nMU_g x n_samples)
    if 'Pulsetrainclean' not in edit:
        raise KeyError("signal.Pulsetrain not found in edited MAT.")
    pulsetrain_cells = _cell_row_read(f, edit['Pulsetrainclean'])

    # Dischargetimes: ngrid x maxMU cell; each cell: (1 x nDischarges) or (nDischarges,)
    top = edit['Distimeclean'][()]           # object array, shape (1,1)
    inner_ref = top.flat[0]                  # the only reference
    inner_cell_ds = f[inner_ref]             # dataset: the 1×nMU cell

    # Now read that inner row cell into a Python list of arrays (length = nMU)
    disc_nested = _cell_row_read(f, inner_cell_ds)
        
# %% --- Build IPTS (time x nMU) by stacking grids (row-wise) then transposing ---
# JSON expects IPTS as DataFrame (time x nMU)
IPTS_df = pd.DataFrame( pulsetrain_cells[0] )

#%% --- Build MUPULSES (0-based) from Dischargetimes; fallback to IPTS threshold if empty cells ---
MUPULSES_list = []
for mu_timing in disc_nested:
    MUPULSES_list.append(np.squeeze(np.asarray(mu_timing,dtype='int32')))#[0]

#%% 
# --- Update ONLY the requested fields in the JSON ---
json_dict_upd['IPTS'] = IPTS_df
json_dict_upd['MUPULSES'] = MUPULSES_list
# Create binary firing matrix
nMU = min(IPTS_df.shape)
spikeMat = np.zeros((nMU, max(IPTS_df.shape)))
for i in range(nMU):
    spikeMat[i, MUPULSES_list[i]] = 1
json_dict_upd['BINARY_MUS_FIRING'] = pd.DataFrame(spikeMat.T)
json_dict_upd['FILENAME'] = str(mat_edited_path)
json_dict_upd['ACCURACY'] = pd.DataFrame(np.squeeze(np.array(silval)))
json_dict_upd['NUMBER_OF_MUS'] = nMU

#%%
emg.save_json_emgfile(json_dict_upd, json_out_path, compresslevel=4)
print(f"Updated JSON written to: {json_out_path}")