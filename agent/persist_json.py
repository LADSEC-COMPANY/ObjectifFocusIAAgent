from __future__ import annotations
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any
logger = logging.getLogger(__name__)
_RETRIES = 12
_BASE_DELAY_S = 0.05

def write_json_file(path: Path | str, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    last_err: OSError | None = None
    for attempt in range(_RETRIES):
        tmp = path.parent / f'{path.stem}.{uuid.uuid4().hex}.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(text)
            os.replace(tmp, path)
            return
        except (PermissionError, OSError) as e:
            last_err = e
            _unlink_quiet(tmp)
            time.sleep(_BASE_DELAY_S * (attempt + 1))
    for attempt in range(_RETRIES):
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            logger.warning('Wrote %s with direct overwrite (atomic replace failed repeatedly; close IDE preview if this persists)', path)
            return
        except (PermissionError, OSError) as e:
            last_err = e
            time.sleep(_BASE_DELAY_S * (attempt + 1))
    if last_err is not None:
        raise last_err
    raise OSError(f'Cannot write {path}')

def _unlink_quiet(p: Path) -> None:
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass
