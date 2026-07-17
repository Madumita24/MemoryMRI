from pathlib import Path

import pytest

from memory_mri.benchmark_loader import load_benchmark_cases


@pytest.fixture()
def benchmark_cases():
    return load_benchmark_cases(Path(__file__).resolve().parents[2] / "benchmark" / "data")
