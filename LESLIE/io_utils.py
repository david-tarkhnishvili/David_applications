from __future__ import annotations

import json
from dataclasses import asdict

import pandas as pd

from model import SimulationConfig


def config_to_json_bytes(config: SimulationConfig) -> bytes:
    return json.dumps(asdict(config), indent=2).encode("utf-8")


def dataframe_to_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")
