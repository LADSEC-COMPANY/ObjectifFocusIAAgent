from __future__ import annotations
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from .persist_json import write_json_file
logger = logging.getLogger(__name__)

def _atomic_write(path: Path, data: Any) -> None:
    write_json_file(path, data)

@dataclass
class ConversationMemory:
    messages: list[dict[str, Any]] = field(default_factory=list)
    _path: Path | None = field(default=None, repr=False)

    def set_path(self, path: Path | str) -> None:
        self._path = Path(path)

    def append(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
        self.persist()

    def extend(self, messages: list[dict[str, Any]]) -> None:
        self.messages.extend(messages)
        self.persist()

    def clear(self) -> None:
        self.messages.clear()
        self.persist()

    def persist(self) -> None:
        if self._path is None:
            return
        _atomic_write(self._path, self.messages)
        logger.debug('Conversation saved (%d messages) -> %s', len(self.messages), self._path)

    @classmethod
    def load(cls, path: Path | str) -> ConversationMemory:
        p = Path(path)
        if not p.exists():
            m = cls()
            m.set_path(p)
            m.persist()
            return m
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        m = cls(messages=list(data) if isinstance(data, list) else [])
        m.set_path(p)
        return m

@dataclass
class LongTermMemory:
    notes: list[dict[str, Any]] = field(default_factory=list)
    _path: Path | None = field(default=None, repr=False)

    def set_path(self, path: Path | str) -> None:
        self._path = Path(path)

    def add_note(self, text: str, source: str | None=None, note_id: str | None=None) -> dict[str, Any]:
        nid = note_id or str(uuid.uuid4())
        entry = {'id': nid, 'text': text.strip(), 'source': source}
        self.notes.append(entry)
        self.persist()
        return entry

    def add_summary(self, text: str) -> dict[str, Any]:
        return self.add_note(text, source='summary')

    def persist(self) -> None:
        if self._path is None:
            return
        _atomic_write(self._path, self.notes)
        logger.debug('Long-term memory saved (%d notes) -> %s', len(self.notes), self._path)

    @classmethod
    def load(cls, path: Path | str) -> LongTermMemory:
        p = Path(path)
        if not p.exists():
            m = cls()
            m.set_path(p)
            m.persist()
            return m
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        notes = data if isinstance(data, list) else data.get('notes', [])
        m = cls(notes=list(notes))
        m.set_path(p)
        return m

    def format_for_prompt(self, max_items: int=30) -> str:
        if not self.notes:
            return '(no notes yet)'
        lines = []
        for n in self.notes[-max_items:]:
            t = n.get('text', '')
            src = n.get('source')
            if src:
                lines.append(f'- [{src}] {t}')
            else:
                lines.append(f'- {t}')
        return '\n'.join(lines)

@dataclass
class ToolResultMemory:
    results: list[dict[str, Any]] = field(default_factory=list)
    _path: Path | None = field(default=None, repr=False)

    def set_path(self, path: Path | str) -> None:
        self._path = Path(path)

    def clear(self) -> None:
        self.results.clear()
        self.persist()

    def record(self, tool_name: str, arguments: dict[str, Any], result: Any, success: bool=True) -> dict[str, Any]:
        entry = {'id': str(uuid.uuid4()), 'tool': tool_name, 'arguments': arguments, 'success': success, 'result': result}
        self.results.append(entry)
        self.persist()
        return entry

    def persist(self) -> None:
        if self._path is None:
            return
        _atomic_write(self._path, self.results)
        logger.debug('Tool results saved (%d entries) -> %s', len(self.results), self._path)

    @classmethod
    def load(cls, path: Path | str) -> ToolResultMemory:
        p = Path(path)
        if not p.exists():
            m = cls()
            m.set_path(p)
            m.persist()
            return m
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        m = cls(results=list(data) if isinstance(data, list) else [])
        m.set_path(p)
        return m

    def format_for_prompt(self, max_items: int=15) -> str:
        if not self.results:
            return '(no tool results yet)'
        chunks = []
        for r in self.results[-max_items:]:
            name = r.get('tool', '?')
            res = r.get('result')
            chunks.append(f'Tool: {name}\nResult: {_short_json(res)}')
        return '\n---\n'.join(chunks)

def _short_json(obj: Any, limit: int=1200) -> str:
    s = json.dumps(obj, ensure_ascii=False, default=str)
    if len(s) > limit:
        return s[:limit - 3] + '...'
    return s
