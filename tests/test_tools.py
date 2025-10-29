from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.tools import ToolContext
from src.tools.files import SummarizeFileInput, summarize_file
from src.tools.shell import SAFE_COMMAND_WHITELIST, SafeShellInput, safe_shell
from src.tools.todo import TodoInput, todo_manager


def test_summarize_file(tmp_path: Path) -> None:
    sample = tmp_path / "example.md"
    sample.write_text("# Title\n\nFirst sentence. Second sentence. Third sentence.", encoding="utf-8")

    context = ToolContext.build(base_path=tmp_path)
    summary = summarize_file(SummarizeFileInput(path=str(sample)), context)
    assert "Summary of 'example.md'" in summary
    assert "- First sentence." in summary


def test_todo_add_and_list(tmp_path: Path) -> None:
    context = ToolContext.build(base_path=tmp_path)
    add_payload = TodoInput(operation="add", title="Write tests")
    response = todo_manager(add_payload, context)
    assert "Added todo" in response

    list_payload = TodoInput(operation="list")
    listing = todo_manager(list_payload, context)
    assert "Write tests" in listing

    todo_id = json.loads((context.data_dir / "todo.json").read_text())[0]["id"]
    done_payload = TodoInput(operation="complete", todo_id=todo_id)
    done_response = todo_manager(done_payload, context)
    assert "Marked todo" in done_response


def test_safe_shell_whitelist(tmp_path: Path) -> None:
    context = ToolContext.build(base_path=tmp_path)
    command = next(iter(SAFE_COMMAND_WHITELIST))
    output = safe_shell(SafeShellInput(command=[command]), context)
    assert isinstance(output, str)

    with pytest.raises(PermissionError):
        safe_shell(SafeShellInput(command="rm -rf /"), context)
