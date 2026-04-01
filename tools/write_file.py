from __future__ import annotations
from pathlib import Path
from typing import Any

def write_file(path: str, content: str, encoding: str='utf-8', create_parents: bool=True) -> dict[str, Any]:
    p = Path(path)
    try:
        if create_parents:
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)
        return {'success': True, 'path': str(p.resolve()), 'bytes_written': len(content.encode(encoding))}
    except OSError as e:
        return {'success': False, 'error': str(e)}
