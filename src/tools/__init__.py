from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping

from pydantic import BaseModel, ConfigDict, ValidationError


class ToolContext(BaseModel):
    """Shared context passed to every tool invocation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    base_path: Path
    data_dir: Path

    @classmethod
    def build(cls, base_path: Path | None = None, data_subdir: str = ".smolmind") -> "ToolContext":
        base_path = base_path or Path.cwd()
        data_dir = base_path / data_subdir
        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(base_path=base_path, data_dir=data_dir)


HandlerType = Callable[[BaseModel, ToolContext], str]


@dataclass
class ToolSpec:
    """Container describing a tool and how to execute it."""

    name: str
    description: str
    input_model: type[BaseModel]
    handler: HandlerType

    def run(self, raw_args: Mapping[str, Any] | BaseModel, context: ToolContext) -> str:
        """Validate input payload and invoke the handler."""
        if isinstance(raw_args, BaseModel):
            payload = raw_args
        else:
            try:
                payload = self.input_model(**raw_args)
            except ValidationError as exc:  # pragma: no cover - precise error message helps at runtime
                raise ValueError(f"Invalid payload for tool '{self.name}': {exc}") from exc
        return self.handler(payload, context)


class ToolRegistry:
    """Registry that keeps track of tools exposed to the agent."""

    def __init__(self, tools: Iterable[ToolSpec] | None = None) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: ToolSpec) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool '{name}'.") from exc

    def names(self) -> List[str]:
        return sorted(self._tools.keys())

    def describe(self) -> Dict[str, str]:
        return {name: spec.description for name, spec in self._tools.items()}

    def call(self, name: str, args: Mapping[str, Any] | BaseModel, context: ToolContext) -> str:
        spec = self.get(name)
        return spec.run(args, context)


def load_default_tools(base_path: Path | None = None) -> ToolRegistry:
    """Helper to initialise the default tool suite."""
    context = ToolContext.build(base_path=base_path)

    from .files import SummarizeFileInput, summarize_file
    from .shell import SafeShellInput, safe_shell
    from .todo import TodoInput, todo_manager

    registry = ToolRegistry(
        tools=[
            ToolSpec(
                name="summarize_file",
                description="Summarise a local text/markdown file into a concise overview.",
                input_model=SummarizeFileInput,
                handler=summarize_file,
            ),
            ToolSpec(
                name="todo",
                description="Manage the local SmolMind todo list. Supports add/list/complete operations.",
                input_model=TodoInput,
                handler=todo_manager,
            ),
            ToolSpec(
                name="safe_shell",
                description="Execute a whitelisted shell command for quick system checks.",
                input_model=SafeShellInput,
                handler=safe_shell,
            ),
        ]
    )
    # Store a reference to the default context for callers who only need the registry
    registry.default_context = context  # type: ignore[attr-defined]
    return registry


__all__ = [
    "ToolContext",
    "ToolRegistry",
    "ToolSpec",
    "load_default_tools",
]
