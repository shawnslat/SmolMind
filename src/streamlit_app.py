from __future__ import annotations

from pathlib import Path

import streamlit as st

from .agent_core import AgentCore, AgentState
from .models import ModelSettings
from .tools import load_default_tools


@st.cache_resource(show_spinner=False)
def _bootstrap_agent(base_path: Path) -> tuple[AgentCore, AgentState]:
    settings = ModelSettings()
    registry = load_default_tools(base_path=base_path)
    core = AgentCore(tool_registry=registry, model_settings=settings, base_path=base_path)
    state = AgentState()
    return core, state


def main() -> None:
    st.set_page_config(page_title="SmolMind", page_icon="🧠")
    st.title("🧠 SmolMind — Local Micro-Agent Assistant")
    st.caption("Powered by small open-source Hugging Face models.")

    base_path = Path.cwd()
    agent_core, state = _bootstrap_agent(base_path)

    if "history" not in st.session_state:
        st.session_state.history = []

    for entry in st.session_state.history:
        with st.chat_message(entry["role"]):
            st.markdown(entry["content"])
            if tool := entry.get("tool_output"):
                st.info(tool)

    prompt = st.chat_input("Ask SmolMind...")
    if prompt:
        st.session_state.history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            turn = agent_core.process_turn(prompt, state=state)
            placeholder.markdown(turn.text)
            if turn.tool_output:
                st.info(turn.tool_output)
            st.session_state.history.append(
                {
                    "role": "assistant",
                    "content": turn.text,
                    "tool_output": turn.tool_output,
                }
            )


if __name__ == "__main__":
    main()
