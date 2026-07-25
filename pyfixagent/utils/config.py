from pathlib import Path
from typing import Any

import yaml

from pyfixagent.utils.logger import get_logger


logger = get_logger(__name__)


def load_config(path: Path) -> dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        if not isinstance(data, dict):
            raise ValueError("config root must be a mapping")
        return data
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        logger.exception("failed to load configuration from %s", path)
        raise RuntimeError(f"failed to load config {path}: {exc}") from exc
