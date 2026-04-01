from __future__ import annotations
import re
from pathlib import Path
from typing import Any

def _first_paragraph(text: str, max_len: int=800) -> str:
    text = text.strip()
    if not text:
        return ''
    blocks = re.split('\\n\\s*\\n', text)
    first = blocks[0].strip() if blocks else ''
    if len(first) > max_len:
        return first[:max_len - 3] + '...'
    return first

def summarize_file(path: str, encoding: str='utf-8', preview_chars: int=2000) -> dict[str, Any]:
    p = Path(path)
    try:
        if not p.exists():
            return {'success': False, 'error': f'File not found: {path}'}
        if not p.is_file():
            return {'success': False, 'error': f'Not a file: {path}'}
        raw = p.read_bytes()
        text = raw.decode(encoding, errors='replace')
        lines = text.splitlines()
        words = len(text.split())
        preview = text[:preview_chars]
        if len(text) > preview_chars:
            preview = preview[:preview_chars - 3] + '...'
        summary_text = f'File: {p.name}\nSize: {len(raw)} bytes\nLines: {len(lines)}, Words: {words}\nPreview:\n{preview}\nOpening excerpt (first block):\n{_first_paragraph(text)}'
        return {'success': True, 'path': str(p.resolve()), 'bytes': len(raw), 'line_count': len(lines), 'word_count': words, 'summary': summary_text}
    except OSError as e:
        return {'success': False, 'error': str(e)}
