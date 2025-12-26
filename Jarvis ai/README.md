# Jarvis AI Assistant

This repository contains a local voice assistant using OpenAI, TTS, and other integrations.

## Key Changes & Fixes
- Fixed a JSON loading error when `config.json` was empty.
- Added config field `openai_model` and `enable_raptor_mini_for_all_clients`.
- The assistant now selects the OpenAI model from `config.json` and respects `enable_raptor_mini_for_all_clients` to use `raptor-mini-preview`.
- Added safer JSON error handling and improved logging.

## Enabling Raptor mini (Preview) for all clients
1. Open `config.json`.
2. Set `enable_raptor_mini_for_all_clients` to `true` to instruct the assistant to use `raptor-mini-preview`.
3. Make sure your OpenAI API key has access to the raptor-mini preview model.

## Installation
1. Create and activate a virtual environment:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Fill in `config.json` with real API keys and paths.

## Running

```powershell
python main.py
```

If you encounter issues, check `jarvis.log` for more information.
