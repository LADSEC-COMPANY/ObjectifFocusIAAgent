from __future__ import annotations
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from .persist_json import write_json_file
logger = logging.getLogger(__name__)

class TaskStatus(str, Enum):
    TODO = 'todo'
    IN_PROGRESS = 'in_progress'
    DONE = 'done'

@dataclass
class Task:
    id: str
    description: str
    status: TaskStatus = TaskStatus.TODO

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d['status'] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        return cls(id=data['id'], description=data['description'], status=TaskStatus(data.get('status', 'todo')))

@dataclass
class TaskMemory:
    goal: str = ''
    tasks: list[Task] = field(default_factory=list)
    _path: Path | None = field(default=None, repr=False)

    def set_path(self, path: Path | str) -> None:
        self._path = Path(path)

    def clear_tasks(self) -> None:
        self.tasks.clear()

    def add_task(self, description: str, task_id: str | None=None) -> Task:
        tid = task_id or str(uuid.uuid4())
        t = Task(id=tid, description=description.strip(), status=TaskStatus.TODO)
        self.tasks.append(t)
        self.persist()
        return t

    def get_task(self, task_id: str) -> Task | None:
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    def set_goal(self, goal: str) -> None:
        self.goal = goal.strip()
        self.persist()

    def current_task(self) -> Task | None:
        for t in self.tasks:
            if t.status == TaskStatus.IN_PROGRESS:
                return t
        for t in self.tasks:
            if t.status == TaskStatus.TODO:
                return t
        return None

    def start_next_if_needed(self) -> Task | None:
        if any((t.status == TaskStatus.IN_PROGRESS for t in self.tasks)):
            return self.current_task()
        for t in self.tasks:
            if t.status == TaskStatus.TODO:
                t.status = TaskStatus.IN_PROGRESS
                self.persist()
                return t
        return None

    def mark_done(self, task_id: str) -> bool:
        t = self.get_task(task_id)
        if not t:
            return False
        t.status = TaskStatus.DONE
        self.persist()
        return True

    def all_done(self) -> bool:
        return len(self.tasks) > 0 and all((t.status == TaskStatus.DONE for t in self.tasks))

    def any_tasks(self) -> bool:
        return len(self.tasks) > 0

    def to_dict(self) -> dict[str, Any]:
        return {'goal': self.goal, 'tasks': [t.to_dict() for t in self.tasks]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskMemory:
        mem = cls(goal=data.get('goal', ''))
        for td in data.get('tasks', []):
            mem.tasks.append(Task.from_dict(td))
        return mem

    def persist(self) -> None:
        if self._path is None:
            return
        write_json_file(self._path, self.to_dict())
        logger.debug('Task memory saved to %s', self._path)

    @classmethod
    def load(cls, path: Path | str) -> TaskMemory:
        p = Path(path)
        if not p.exists():
            m = cls()
            m.set_path(p)
            m.persist()
            return m
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        m = cls.from_dict(data)
        m.set_path(p)
        return m
