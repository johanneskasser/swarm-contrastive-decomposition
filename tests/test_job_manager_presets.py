"""Tests for extended DEFAULT_ALGORITHM_PARAMS and preset-related JobManager methods."""
import pytest
from scheduler.job_manager import DEFAULT_ALGORITHM_PARAMS, ALGORITHM_PARAMS_METADATA


def test_new_params_present_in_defaults():
    assert "square_sources_spike_det" in DEFAULT_ALGORITHM_PARAMS
    assert "peel_off" in DEFAULT_ALGORITHM_PARAMS
    assert "swarm" in DEFAULT_ALGORITHM_PARAMS
    assert "electrode" in DEFAULT_ALGORITHM_PARAMS


def test_new_param_default_values():
    assert DEFAULT_ALGORITHM_PARAMS["square_sources_spike_det"] is True
    assert DEFAULT_ALGORITHM_PARAMS["peel_off"] is True
    assert DEFAULT_ALGORITHM_PARAMS["swarm"] is True
    assert DEFAULT_ALGORITHM_PARAMS["electrode"] == ""


def test_new_params_have_metadata():
    for key in ("square_sources_spike_det", "peel_off", "swarm", "electrode"):
        assert key in ALGORITHM_PARAMS_METADATA
        assert "description" in ALGORITHM_PARAMS_METADATA[key]
        assert "type" in ALGORITHM_PARAMS_METADATA[key]


def test_electrode_metadata_type_is_string():
    """Must be exactly 'string' (not 'str') to match the UI branch condition."""
    assert ALGORITHM_PARAMS_METADATA["electrode"]["type"] == "string"
