from pathlib import Path

import pytest

from nodi.config import load_config
from nodi.simulate.run import simulate

N_TEST = 3000


def small_cfg(data_dir: Path) -> dict:
    return load_config(data_dir=data_dir, overrides={
        "simulation": {"n_subscribers": N_TEST, "future_paths": 1},
    })


@pytest.fixture(scope="session")
def sim(tmp_path_factory):
    d = tmp_path_factory.mktemp("sim")
    cfg = small_cfg(d)
    simulate(cfg)
    return cfg


@pytest.fixture(scope="session")
def wh(sim):
    from nodi.warehouse.build import build_warehouse
    build_warehouse(sim)
    return sim


@pytest.fixture(scope="session")
def modelled(wh):
    from nodi.models.run import run_models
    summary = run_models(wh)
    return wh, summary


@pytest.fixture(scope="session")
def segmented(modelled):
    from nodi.segments.build import build_segments
    cfg, _ = modelled
    build_segments(cfg)
    return cfg
