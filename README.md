# SmolMind — Local Micro-Agent Assistant

SmolMind is a modular, privacy-friendly AI assistant that runs entirely on your machine using compact open models from Hugging Face. It is designed for everyday productivity tasks such as summarising files, planning projects, and running safe shell checks without ever sending your data to the cloud.

## ✨ Features
- Lightweight multi-agent loop (`Researcher`, `Summarizer`, `Coder`, `Planner`)
- Plug-and-play tools: `summarize_file`, `todo`, `safe_shell` (extend easily)
- Local model loading via `transformers` with configurable parameters
- CLI chat application built with Typer + Rich (optional speech I/O)
- Minimal Streamlit UI (`streamlit run src/streamlit_app.py`)
- Pydantic-based schemas for configuration, tools, and agent state
- Optional Hugging Face Agents API integration for remote toolchains

## 🛠️ Installation
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> **Torch on Apple Silicon:** Install the appropriate `torch` wheel manually if the default wheel is not available. See https://pytorch.org/get-started/locally/ for up-to-date commands.

Create a `.env` file by copying `.env.example` and adjusting values (model id, token, etc.).

## 🚀 Usage

### CLI chat
```bash
python -m src.app chat
```

Options:
- `--voice` enable speech input via `speech_recognition` (requires a working microphone and optional Whisper backend; falls back to Google recogniser if available).
- `--verbose` show raw tool use JSON emitted by the model.
- `--agent <name>` lock the main loop to a specific micro-agent (`Researcher`, `Summarizer`, `Coder`, `Planner`).

List tools:
```bash
python -m src.app tools
```

Call a tool directly:
```bash
python -m src.app call-tool summarize_file --args '{"path": "README.md", "max_sentences": 3}'
```

### Streamlit UI
```bash
streamlit run src/streamlit_app.py
```

## 🧩 Extending tools
1. Create a new module in `src/tools/`.
2. Define a Pydantic input model and handler that accepts `(params, ToolContext)`.
3. Register the tool inside `src/tools/__init__.py` via a new `ToolSpec`.
4. The agent automatically receives the description and can request it with JSON.

## 🎤 Speech support
- Input powered by `speech_recognition`. For offline recognition install [`openai-whisper`](https://github.com/openai/whisper) and ensure `Recognizer.recognize_whisper` is available.
- Output uses `pyttsx3`. On Linux you may need to install system speech services (`espeak`, `nsss`, etc.).

## 🧪 Tests
```bash
pytest
```

## 🗺️ Roadmap ideas
- Persistence for chat sessions and embeddings
- Additional task-specific agents (finance, creative writing, study)
- Improved tool discovery and natural-language routing
- Local vector search over user documents

## 📄 License
MIT — feel free to experiment and adapt for personal workflows.
