from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from . import ToolContext


class TodoEntry(BaseModel):
    id: int
    title: str
    completed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class TodoInput(BaseModel):
    operation: str = Field(..., description="Operation: add, list, or complete.")
    title: Optional[str] = Field(None, description="Item text when adding a todo.")
    todo_id: Optional[int] = Field(None, description="Numeric identifier when completing.")

    def normalised_operation(self) -> str:
        return self.operation.lower().strip()


class TodoStore:
    def __init__(self, store_path: Path) -> None:
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self._write([])

    def _read(self) -> List[TodoEntry]:
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = []
        return [TodoEntry(**item) for item in data]

    def _write(self, items: List[TodoEntry]) -> None:
        serialisable = [item.model_dump() for item in items]
        self.store_path.write_text(json.dumps(serialisable, default=str, indent=2), encoding="utf-8")

    def list(self) -> List[TodoEntry]:
        return self._read()

    def add(self, title: str) -> TodoEntry:
        if not title.strip():
            raise ValueError("Cannot add an empty todo item.")
        items = self._read()
        next_id = 1 + max([item.id for item in items], default=0)
        entry = TodoEntry(id=next_id, title=title.strip())
        items.append(entry)
        self._write(items)
        return entry

    def complete(self, todo_id: int) -> TodoEntry:
        items = self._read()
        for item in items:
            if item.id == todo_id:
                if item.completed:
                    return item
                item.completed = True
                item.completed_at = datetime.utcnow()
                self._write(items)
                return item
        raise ValueError(f"Todo with id {todo_id} not found.")


def _format_todos(entries: List[TodoEntry]) -> str:
    if not entries:
        return "Todo list is empty. Use operation=add to insert new items."

    lines = []
    for entry in entries:
        status = "✅" if entry.completed else "⬜️"
        lines.append(f"{status} #{entry.id} {entry.title}")
    return "\n".join(lines)


def todo_manager(params: TodoInput, context: ToolContext) -> str:
    store = TodoStore(context.data_dir / "todo.json")
    operation = params.normalised_operation()

    if operation == "list":
        return _format_todos(store.list())

    if operation == "add":
        if not params.title:
            raise ValueError("Adding a todo requires a title.")
        entry = store.add(params.title)
        return f"Added todo #{entry.id}: {entry.title}"

    if operation in {"done", "complete"}:
        if params.todo_id is None:
            raise ValueError("Completing a todo requires `todo_id`.")
        entry = store.complete(params.todo_id)
        return f"Marked todo #{entry.id} as complete."

    raise ValueError(f"Unsupported todo operation '{params.operation}'.")


__all__ = ["TodoInput", "todo_manager", "TodoStore", "TodoEntry"]
