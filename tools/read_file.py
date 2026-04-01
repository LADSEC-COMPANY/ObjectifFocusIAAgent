from __future__ import annotations
from pathlib import Path
from typing import Any

def read_file(path: str, encoding: str='utf-8', max_chars: int | None=None) -> dict[str, Any]:
    p = Path(path)
    try:
        if not p.exists():
            return {'success': False, 'error': f'File not found: {path}'}
        if not p.is_file():
            return {'success': False, 'error': f'Not a file: {path}'}
        text = p.read_text(encoding=encoding)
        truncated = False
        if max_chars is not None and len(text) > max_chars:
            text = text[:max_chars]
            truncated = True
        out: dict[str, Any] = {'success': True, 'path': str(p.resolve()), 'content': text}
        if truncated:
            out['truncated'] = True
            out['max_chars'] = max_chars
        return out
    except OSError as e:
        return {'success': False, 'error': str(e)}
