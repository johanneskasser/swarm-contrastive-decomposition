# Swarm-Contrastive Decomposition 🧠

[![PyPI version](https://badge.fury.io/py/swarm-contrastive-decomposition.svg)](https://pypi.org/project/swarm-contrastive-decomposition/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

A Python package for decomposition of neurophysiological time series signals using a Particle Swarm Optimised Independence Estimator for Blind Source Separation.

<div align="center">
    <img src="images/pipeline.png" alt="Pipeline" width="500"/>
</div>

## Table of Contents 📚

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Configuration](#configuration)
- [Test Data](#test-data)
- [Contributing](#contributing)
- [License](#license)
- [Citation](#citation)
- [Contact](#contact)

## Installation 🛠️

### From PyPI (Recommended)

```bash
pip install swarm-contrastive-decomposition
```

### From GitHub (Latest Development Version)

```bash
pip install git+https://github.com/AgneGris/swarm-contrastive-decomposition.git
```

### From Source

```bash
git clone https://github.com/AgneGris/swarm-contrastive-decomposition
cd swarm-contrastive-decomposition
pip install -e .
```

### Verify Installation

```bash
python -c "import scd; print(f'SCD version: {scd.__version__}')"
```

## Quick Start 🚀

```python
import scd

# Train with default configuration
dictionary, timestamps = scd.train("data/input/emg.npy")

# Save results
scd.save_results("data/output/emg.pkl", dictionary)
```

## Usage

### Basic Usage

```python
import scd

# Use a predefined configuration
dictionary, timestamps = scd.train(
    "path/to/your/data.mat",
    config_name="surface"  # or "default", "intramuscular"
)

scd.save_results("output.pkl", dictionary)
```

### With Configuration Overrides

```python
import scd

# Override specific parameters
dictionary, timestamps = scd.train(
    "data/input/emg.npy",
    config_name="surface",
    max_iterations=100,  # override for quick testing
    output_final_source_plot=True
)
```

### Step-by-Step Control

```python
import scd

# Load configuration
config = scd.load_config("surface")

# Load data
neural_data = scd.load_data("data/input/emg.npy", device=config.device)

# Preprocess
neural_data = scd.preprocess_data(neural_data, config)

# Train model
dictionary, timestamps = scd.train_model(neural_data, config)

# Save results
scd.save_results("output.pkl", dictionary)
```

### Supported Data Formats

- `.mat` — MATLAB files (specify the variable name with `key` parameter)
- `.npy` — NumPy arrays

```python
# For .mat files with custom variable name
dictionary, timestamps = scd.train("data.mat", key="emg_data")

# For .npy files
dictionary, timestamps = scd.train("data.npy")
```

Data should have shape `(time, channels)` or `(channels, time)` — the loader will automatically transpose if needed.

## Configuration ⚙️

Configurations are defined in `scd/configs.json`. Available presets:

| Config Name | Use Case | Sampling Rate | Description |
|-------------|----------|---------------|-------------|
| `default` | General purpose | 10240 Hz | Balanced settings for most EMG data |
| `surface` | Surface EMG | 10240 Hz | Optimized for surface recordings |
| `intramuscular` | Intramuscular EMG | 10240 Hz | Higher iterations for fine-wire recordings |

### Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `device` | `"cuda"` for GPU or `"cpu"` | `"cuda"` |
| `acceptance_silhouette` | Quality threshold for source acceptance | `0.85` |
| `extension_factor` | Typically `1000 / num_channels`. Higher values may improve results | `25` |
| `low_pass_cutoff` | Low-pass filter cutoff frequency (Hz) | `4400` |
| `high_pass_cutoff` | High-pass filter cutoff frequency (Hz) | `10` |
| `sampling_frequency` | Sampling frequency of your signal (Hz) | `10240` |
| `start_time` | Start time for signal trimming (s). Use `0` for beginning | `0` |
| `end_time` | End time for signal trimming (s). Use `-1` for entire signal | `-1` |
| `max_iterations` | Maximum decomposition iterations | `200` |
| `max_firing_rate_hz` | Expected maximum motoneuron firing rate (Hz). Used to derive the temporal-separation bound on `extension_factor` and to validate `reset_peak_separation_ms` | `50.0` |
| `peel_off_window_size_ms` | Window size for spike-triggered average (ms). `peel_off_window_size` in samples is derived automatically as `ms × fs / 1000` | `20` |
| `reset_peak_separation_ms` | Minimum distance between two detected peaks in the source signal (ms), converted to samples as `ms × fs / 1000`. Must be less than the minimum ISI at `max_firing_rate_hz` | `4.0` |
| `output_final_source_plot` | Generate plot of final sources | `false` |
| `use_coeff_var_fitness` | Use coefficient of variation fitness. `true` for EMG, `false` for intracortical | `true` |
| `remove_bad_fr` | Filter sources with firing rates < 2 Hz or > 100 Hz | `true` |
| `clamp_sources` | Clamp source amplitudes to ±30 σ during ICA to suppress outliers | `true` |

### Custom Configuration

Add your own configuration to `scd/configs.json`:

```json
{
    "my_experiment": {
        "device": "cuda",
        "acceptance_silhouette": 0.80,
        "extension_factor": 30,
        "sampling_frequency": 2048,
        ...
    }
}
```

Then use it:

```python
dictionary, timestamps = scd.train("data.mat", config_name="my_experiment")
```

## Extension Factor Constraints

The extension factor `K` is validated automatically against two mathematical constraints before each run.

### Variables

| Symbol | Meaning |
|--------|---------|
| `K` | Extension factor (`extension_factor` config parameter) |
| `M` | Number of **clean** channels = total channels − `bad_channels` |
| `L` | MUAP length in samples = `floor(15 ms × fs / 1000)` |
| `N` | Assumed number of sources = **30** (fixed assumption) |
| `T` | Minimum inter-spike interval = `floor(fs / max_firing_rate_hz)` samples |

### Constraint 1 — Model Identifiability

Starting from the over-determination condition for the extended mixing matrix:

```
K · M  ≥  N · (K + L − 1)
```

Rearranging (requires M > N):

```
K · (M − N)  ≥  N · (L − 1)
K  ≥  ceil( N · (L − 1) / (M − N) )   →   K_min
```

`K_min` is the **minimum** K needed for the extended system to be theoretically identifiable (more observations than unknowns in the mixing model).  In practice, the sparse-EMG assumption means the algorithm can converge below this bound; a `UserWarning` is issued rather than an error when `K < K_min`.

### Constraint 2 — Temporal Separation

The observation window for a single spike spans `L + K − 1` samples after extension. It must be shorter than the fastest expected inter-spike interval `T`:

```
L + K − 1  <  T
K  ≤  T − L   →   K_max
```

**A `ValueError` is raised** if `K > K_max`, because temporal aliasing between adjacent spikes is guaranteed.

### Valid range and automatic validation

```
K_min  ≤  K  ≤  K_max
```

At the default sampling frequency of 10 240 Hz with `max_firing_rate_hz = 50`:

| Quantity | Value |
|----------|-------|
| L (15 ms @ 10 240 Hz) | 153 samples |
| T (50 Hz `max_firing_rate_hz`) | 204 samples |
| **K_max** | **51** |

All built-in presets (`default` K=25, `intramuscular` K=20, `surface` K=5) satisfy K ≤ 51.

> **Tip:** If your recordings include faster-firing units (e.g. 70 Hz), set `max_firing_rate_hz` accordingly — this tightens K_max and prevents temporal aliasing at that firing rate.

### Programmatic access

```python
from scd import compute_extension_factor_bounds

k_min, k_max = compute_extension_factor_bounds(
    num_channels=64,
    bad_channels=[56],          # 63 clean channels
    sampling_frequency=10240,
)
print(f"Valid K range: [{k_min}, {k_max}]")
```

## Test Data 🧪

The repository includes test data to verify your installation:

- **File:** `data/input/emg.npy`
- **Type:** Surface EMG
- **Sampling rate:** 10240 Hz
- **Configuration:** Use `"surface"` config

```python
import scd

# Run with test data
dictionary, timestamps = scd.train(
    "data/input/emg.npy",
    config_name="surface"
)

print(f"Found {len(dictionary)} motor units")
```

## Contributing 🤝

We welcome contributions! Here's how you can contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/newfeature`)
3. Commit your changes (`git commit -m 'Add some newfeature'`)
4. Push to the branch (`git push origin feature/newfeature`)
5. Open a pull request

## License 📜

This project is licensed under the CC BY-NC 4.0 License.

## Citation

If you use this code in your research, please cite our paper:

```bibtex
@article{grison2024particle,
  author={Grison, Agnese and Clarke, Alexander Kenneth and Muceli, Silvia and Ibáñez, Jaime and Kundu, Aritra and Farina, Dario},
  journal={IEEE Transactions on Biomedical Engineering}, 
  title={A Particle Swarm Optimised Independence Estimator for Blind Source Separation of Neurophysiological Time Series}, 
  year={2024},
  volume={},
  number={},
  pages={1-11},
  doi={10.1109/TBME.2024.3446806},
  keywords={Recording; Time series analysis; Sorting; Vectors; Measurement; Electrodes; Probes; Independent component analysis; particle swarm optimisation; blind source separation; intramuscular electromyography; intracortical recording}
}

@article{grison2025unlocking,
  title={Unlocking the full potential of high-density surface EMG: novel non-invasive high-yield motor unit decomposition},
  author={Grison, Agnese and Mendez Guerra, Irene and Clarke, Alexander Kenneth and Muceli, Silvia and Ib{\'a}{\~n}ez, Jaime and Farina, Dario},
  journal={The Journal of Physiology},
  volume={603},
  number={8},
  pages={2281--2300},
  year={2025},
  publisher={Wiley Online Library}
}
```

## Contact

For questions or inquiries:

**Agnese Grison**  
📧 agnese.grison@outlook.it