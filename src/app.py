from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .agent_core import AgentCore, AgentState
from .models import ModelSettings
from .tools import ToolRegistry, load_default_tools

app = typer.Typer(add_completion=False, invoke_without_command=True)
console = Console()


def _init_agent(core_agent: Optional[str], model_settings: ModelSettings, base_path: Path) -> AgentCore:
    registry = load_default_tools(base_path=base_path)
    agent_core = AgentCore(tool_registry=registry, model_settings=model_settings, base_path=base_path)
    if core_agent:
        try:
            agent_core.set_default_agent(core_agent)
        except ValueError:
            console.print(f"[yellow]Unknown agent '{core_agent}'. Using automatic routing instead.[/]")
    return agent_core


def _listen_for_audio(timeout: int = 5, phrase_time_limit: int = 15) -> str:
    try:
        import speech_recognition as sr
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Speech recognition not available. Install `speechrecognition`.") from exc
    recogniser = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            console.print("[cyan]Listening...[/]")
            try:
                audio = recogniser.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            except sr.WaitTimeoutError:
                return ""
    except AttributeError as exc:
        raise RuntimeError(
            "PyAudio is required for microphone input. Install it or run without --voice."
        ) from exc
    except OSError as exc:  # e.g. no default input device
        raise RuntimeError(
            "No microphone input device detected. Connect a mic or run without --voice."
        ) from exc
    try:
        return recogniser.recognize_whisper(audio)
    except AttributeError:
        pass
    except ModuleNotFoundError:
        console.print("[yellow]Whisper is not installed; falling back to Google recognizer.[/]")
    except sr.UnknownValueError:
        return ""
    except Exception:
        console.print("[yellow]Whisper recognition failed; trying Google recognizer.[/]")
    try:
        return recogniser.recognize_google(audio)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as exc:
        raise RuntimeError(
            "Google Speech API is unavailable. Install `openai-whisper` or configure another recognizer."
        ) from exc


def _speak_text(text: str) -> None:
    try:
        import pyttsx3
    except ImportError:  # pragma: no cover - optional dependency
        console.print("[yellow]pyttsx3 not installed; skipping voice response.[/]")
        return

    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()


def _render_turn(turn, voice_enabled: bool) -> None:
    subtitles = []
    if turn.tool_used:
        subtitles.append(f"tool: {turn.tool_used}")
    subtitle = " • ".join(subtitles) if subtitles else None
    console.print(Panel(turn.text, title=f"{turn.agent} agent", subtitle=subtitle))
    if turn.tool_output:
        console.print(Panel(turn.tool_output, title=f"Tool output ({turn.tool_used})", style="dim"))
    if voice_enabled:
        _speak_text(turn.text)


def _run_chat(voice: bool, verbose: bool, agent: Optional[str], base_path: Path) -> None:
    settings = ModelSettings()
    agent_core = _init_agent(agent, settings, base_path=base_path)
    state = AgentState()

    console.print("[bold magenta]SmolMind[/] — lightweight local assistant. Type 'exit' to quit.")

    while True:
        try:
            if voice:
                try:
                    user_text = _listen_for_audio()
                except RuntimeError as exc:
                    console.print(f"[red]{exc}[/]")
                    console.print("[yellow]Voice mode disabled for this session. Re-run with --voice after installing dependencies.[/]")
                    voice = False
                    continue
                if not user_text:
                    console.print("[yellow]Heard silence. Say something or disable --voice.[/]")
                    continue
                console.print(f"[green]You[/]: {user_text}")
            else:
                user_text = Prompt.ask("[green]You")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[red]Session ended.[/]")
            break

        if user_text.strip().lower() in {"exit", "quit"}:
            console.print("[cyan]Goodbye![/]")
            break

        turn = agent_core.process_turn(user_text, state=state)
        if verbose and turn.raw_tool_request:
            console.print(f"[grey53]Tool request: {turn.raw_tool_request}[/]")
        _render_turn(turn, voice_enabled=voice)


@app.command()
def chat(
    voice: bool = typer.Option(False, "--voice", help="Enable speech recognition + TTS."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show raw tool requests."),
    agent: Optional[str] = typer.Option(None, "--agent", help="Pin to a specific micro-agent."),
    base_path: Path = typer.Option(Path.cwd(), "--base-path", help="Working directory for tools."),
) -> None:
    """Launch a chat loop with the SmolMind assistant."""
    _run_chat(voice=voice, verbose=verbose, agent=agent, base_path=base_path)


@app.command()
def tools() -> None:
    """List available SmolMind tools."""
    registry: ToolRegistry = load_default_tools()
    for name, description in registry.describe().items():
        console.print(f"[bold]{name}[/]: {description}")


@app.command()
def call_tool(
    name: str = typer.Argument(..., help="Tool name."),
    args: str = typer.Option("{}", "--args", "-a", help="JSON payload containing tool arguments."),
    base_path: Path = typer.Option(Path.cwd(), "--base-path", help="Working directory for tools."),
):
    """Invoke a tool directly from the CLI."""
    registry = load_default_tools(base_path=base_path)
    context = getattr(registry, "default_context", None)
    if context is None:
        from .tools import ToolContext

        context = ToolContext.build(base_path=base_path)
    try:
        payload = json.loads(args)
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid JSON payload:[/] {exc}")
        raise typer.Exit(code=1)

    try:
        result = registry.call(name, payload, context)
    except Exception as exc:  # pylint: disable=broad-except
        console.print(f"[red]Tool execution failed:[/] {exc}")
        raise typer.Exit(code=1)
    console.print(result)


@app.callback(invoke_without_command=True)
def _default(
    ctx: typer.Context,
    voice: bool = typer.Option(False, "--voice", help="Enable speech recognition + TTS."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show raw tool requests."),
    agent: Optional[str] = typer.Option(None, "--agent", help="Pin to a specific micro-agent."),
    base_path: Path = typer.Option(Path.cwd(), "--base-path", help="Working directory for tools."),
) -> None:
    """Fallback to chat when no subcommand is provided."""
    if ctx.invoked_subcommand is None:
        _run_chat(voice=voice, verbose=verbose, agent=agent, base_path=base_path)
        raise typer.Exit()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
