from __future__ import annotations
import re
from pathlib import Path

_WIN_PATH = re.compile(r'[A-Za-z]:(?:\\|/)[^\s|"\'<>*\n\r]+')
_UNIX_PATH = re.compile(r'(?:^|\s)(/[^:\s|"\'<>*\n\r]+)')


def _strip_trailing_punct(s: str) -> str:
    return s.rstrip('.,;:!?)"\'\\]')


def extract_paths(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _WIN_PATH.finditer(text):
        p = _strip_trailing_punct(m.group(0))
        if len(p) >= 3 and p not in seen:
            seen.add(p)
            out.append(p)
    for m in _UNIX_PATH.finditer(text):
        p = _strip_trailing_punct(m.group(1).strip())
        if len(p) >= 2 and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def directory_for_listing(path_str: str) -> str:
    p = Path(path_str)
    try:
        if p.is_file():
            return str(p.parent.resolve())
        if p.is_dir():
            return str(p.resolve())
    except OSError:
        pass
    return path_str.rstrip('/\\') or path_str


def wants_directory_listing(text: str) -> bool:
    if not text or not text.strip():
        return False
    t = text.lower()
    if re.search('\\blist\\b', t) and ('file' in t or 'folder' in t or 'direct' in t):
        return True
    if any(k in t for k in ('list files', 'list the file', 'list the files', 'files in', 'contents of', "what's in", 'whats in')):
        return True
    if 'show' in t and ('file' in t or 'folder' in t or 'direct' in t):
        return True
    if 'enumerate' in t or 'directory' in t or ('folder' in t and 'list' in t):
        return True
    return False


def should_try_list_fallback(goal: str, task_description: str) -> bool:
    return wants_directory_listing(goal) or wants_directory_listing(task_description)


def should_auto_complete_list_task(goal: str, task_description: str) -> bool:
    if wants_directory_listing(goal):
        return True
    td = task_description.lower()
    if wants_directory_listing(task_description) and not _needs_deep_read(td):
        return True
    return False


def _needs_deep_read(task_lower: str) -> bool:
    if 'each file' in task_lower or 'every file' in task_lower:
        return True
    if 'all files' in task_lower and 'list' not in task_lower and ('read' in task_lower or 'memory' in task_lower):
        return True
    if 'full content' in task_lower or 'entire file' in task_lower:
        return True
    return False


def pick_listing_directory(goal: str, task_description: str) -> str | None:
    combined = f'{goal}\n{task_description}'
    paths = extract_paths(combined)
    if not paths:
        return None
    for raw in paths:
        d = directory_for_listing(raw)
        if d:
            return d
    return directory_for_listing(paths[0])


def format_list_result_for_user(result: dict) -> str:
    if not result.get('success'):
        err = result.get('error', 'Unknown error')
        return f'Could not list directory: {err}'
    entries = result.get('entries') or []
    lines: list[str] = []
    for e in entries[:500]:
        rel = e.get('relative', e.get('path', ''))
        kind = 'dir' if e.get('is_dir') else 'file'
        lines.append(f'  [{kind}] {rel}')
    more = len(entries) - 500
    head = f"Directory: {result.get('directory', '')}\n{len(entries)} item(s):\n" + '\n'.join(lines)
    if more > 0:
        head += f'\n... and {more} more.'
    return head
