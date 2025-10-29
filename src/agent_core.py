from __future__ import annotations

import json
import logging
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .models import ModelSettings, generate_completion
from .tools import ToolContext, ToolRegistry, load_default_tools

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentProfile:
    name: str
    description: str
    system_prompt: str


DEFAULT_AGENTS: List[AgentProfile] = [
    AgentProfile(
        name="Researcher",
        description="Gathers information, compares sources, and surfaces insights.",
        system_prompt="You are the Researcher agent. Focus on fact-finding, evidence, and clarity.",
    ),
    AgentProfile(
        name="Summarizer",
        description="Condenses documents and conversations into concise bullet points.",
        system_prompt="You are the Summarizer agent. Produce tight, structured summaries.",
    ),
    AgentProfile(
        name="Coder",
        description="Assists with programming tasks, debugging, and code walkthroughs.",
        system_prompt="You are the Coder agent. Give actionable code help and highlight pitfalls.",
    ),
    AgentProfile(
        name="Planner",
        description="Breaks objectives into clear steps and timelines.",
        system_prompt="You are the Planner agent. Create pragmatic plans with sequencing and priorities.",
    ),
]


KEYWORD_AGENT_HINTS: Dict[str, str] = {
    "summar": "Summarizer",
    "tl;dr": "Summarizer",
    "bullet": "Summarizer",
    "plan": "Planner",
    "roadmap": "Planner",
    "schedule": "Planner",
    "strategy": "Planner",
    "code": "Coder",
    "bug": "Coder",
    "error": "Coder",
    "refactor": "Coder",
    "research": "Researcher",
    "compare": "Researcher",
    "explain": "Researcher",
    "learn": "Researcher",
}


class AgentMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    agent: Optional[str] = None
    tool_name: Optional[str] = None


class AgentState(BaseModel):
    history: List[AgentMessage] = Field(default_factory=list)


class AgentTurn(BaseModel):
    agent: str
    text: str
    raw_tool_request: Optional[str] = None
    tool_used: Optional[str] = None
    tool_output: Optional[str] = None


@dataclass
class ToolCall:
    name: str
    args: Dict[str, Any]


class AgentCore:
    """Lightweight multi-agent orchestrator for SmolMind."""

    def __init__(
        self,
        agents: List[AgentProfile] | None = None,
        tool_registry: ToolRegistry | None = None,
        model_settings: ModelSettings | None = None,
        base_path: Path | None = None,
    ) -> None:
        self.agents = agents or DEFAULT_AGENTS
        self.agent_lookup = {agent.name: agent for agent in self.agents}
        self.model_settings = model_settings or ModelSettings()

        self.tool_registry = tool_registry or load_default_tools(base_path=base_path)
        default_context = getattr(self.tool_registry, "default_context", None)
        self.tool_context = default_context or ToolContext.build(base_path=base_path)

        self._default_agent = self.agent_lookup["Researcher"]

    def set_default_agent(self, agent_name: str) -> None:
        try:
            self._default_agent = self.agent_lookup[agent_name]
        except KeyError as exc:
            raise ValueError(f"Unknown agent '{agent_name}'. Available: {list(self.agent_lookup)}") from exc

    def available_agents(self) -> Dict[str, str]:
        return {agent.name: agent.description for agent in self.agents}

    def _pick_agent(self, user_text: str) -> AgentProfile:
        lowered = user_text.lower()
        for needle, agent_name in KEYWORD_AGENT_HINTS.items():
            if needle in lowered:
                return self.agent_lookup.get(agent_name, self._default_agent)
        return self._default_agent

    def process_turn(self, user_text: str, state: AgentState | None = None) -> AgentTurn:
        if state is None:
            state = AgentState()

        agent = self._pick_agent(user_text)
        logger.debug("Selected agent: %s for input: %s", agent.name, user_text)

        state.history.append(AgentMessage(role="user", content=user_text))
        messages = self._compose_messages(agent, state.history)
        assistant_reply = generate_completion(messages, settings=self.model_settings)

        tool_call = self._extract_tool_call(assistant_reply)
        if not tool_call:
            state.history.append(AgentMessage(role="assistant", content=assistant_reply, agent=agent.name))
            return AgentTurn(agent=agent.name, text=assistant_reply)

        logger.info("Agent requested tool %s with args %s", tool_call.name, tool_call.args)
        state.history.append(
            AgentMessage(role="assistant", content=assistant_reply, agent=agent.name, tool_name=tool_call.name)
        )

        tool_result = self._run_tool(tool_call)
        state.history.append(AgentMessage(role="tool", content=tool_result, tool_name=tool_call.name))

        follow_up_messages = self._compose_messages(agent, state.history)
        final_reply = generate_completion(follow_up_messages, settings=self.model_settings)
        state.history.append(AgentMessage(role="assistant", content=final_reply, agent=agent.name))

        return AgentTurn(
            agent=agent.name,
            text=final_reply,
            raw_tool_request=assistant_reply,
            tool_used=tool_call.name,
            tool_output=tool_result,
        )

    def _compose_messages(self, agent: AgentProfile, history: List[AgentMessage]) -> List[Dict[str, str]]:
        tool_descriptions = "\n".join(
            f"- {name}: {description}" for name, description in self.tool_registry.describe().items()
        )
        system_prompt = textwrap.dedent(
            f"""
            {agent.system_prompt}

            You are collaborating with sibling agents: {', '.join(self.agent_lookup)}.
            Use tools only when they add value.

            Available tools:
            {tool_descriptions}

            When a tool is required respond *only* with JSON:
            {{"tool": "tool_name", "args": {{...}}}}

            After receiving a tool result, craft a natural language answer.
            If no tool is needed, respond normally.
            """
        ).strip()

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for msg in history[-10:]:
            entry = {"role": msg.role, "content": msg.content}
            if msg.role == "tool" and msg.tool_name:
                entry["name"] = msg.tool_name
            messages.append(entry)
        return messages

    def _extract_tool_call(self, assistant_reply: str) -> Optional[ToolCall]:
        trimmed = assistant_reply.strip()
        if not trimmed:
            return None
        parsed = self._parse_json_object(trimmed)
        if not parsed:
            return None
        name = parsed.get("tool")
        if not isinstance(name, str):
            return None
        args = parsed.get("args", {})
        if not isinstance(args, dict):
            args = {}
        return ToolCall(name=name, args=args)

    def _parse_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            snippet = text[start : end + 1]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                return None

    def _run_tool(self, tool_call: ToolCall) -> str:
        return self.tool_registry.call(tool_call.name, tool_call.args, self.tool_context)


__all__ = [
    "AgentCore",
    "AgentProfile",
    "AgentState",
    "AgentTurn",
    "DEFAULT_AGENTS",
]
