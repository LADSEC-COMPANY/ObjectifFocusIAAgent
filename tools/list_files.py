from __future__ import annotations
from pathlib import Path
from typing import Any

def list_files(directory: str='.', pattern: str='*', recursive: bool=False, include_hidden: bool=False) -> dict[str, Any]:
    root = Path(directory)
    try:
        if not root.exists():
            return {'success': False, 'error': f'Directory not found: {directory}'}
        if not root.is_dir():
            return {'success': False, 'error': f'Not a directory: {directory}'}
        if recursive:
            iterator = root.rglob(pattern)
        else:
            iterator = root.glob(pattern)
        entries: list[dict[str, Any]] = []
        for p in sorted(iterator):
            name = p.name
            if not include_hidden and name.startswith('.'):
                continue
            try:
                rel = p.relative_to(root.resolve())
            except ValueError:
                rel = p
            entries.append({'path': str(p.resolve()), 'relative': str(rel), 'is_file': p.is_file(), 'is_dir': p.is_dir()})
        return {'success': True, 'directory': str(root.resolve()), 'count': len(entries), 'entries': entries}
    except OSError as e:
        return {'success': False, 'error': str(e)}
