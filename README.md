# AndroBot + RepoChat

Two tools for GitHub:

## 1. AndroBot (GitHub Bot)
Automatically responds to new issues and PRs using an LLM.

### Setup
1. Copy `bot.py` and `.github/workflows/bot.yml` to your repo
2. Add `GEMINI_API_KEY` secret in repo settings (or use Ollama)
3. The bot will auto-respond to new issues/PRs

### How it works
- GitHub Actions triggers on `issues: opened` and `pull_request: opened`
- `bot.py` reads the event, calls LLM (Gemini/Ollama), posts a comment
- Supports both Gemini (cloud) and Ollama (local/self-hosted)

## 2. RepoChat (Local Chatbot)
Chat with your codebase locally using an LLM.

### Usage
```bash
# Chat with a local repo
python3 repochat.py /path/to/repo

# Clone and chat
python3 repochat.py --clone https://github.com/user/repo

# Use specific model
python3 repochat.py /path/to/repo --model qwen3:8b
```

### Features
- Indexes all code files (Python, JS, TS, Java, Kotlin, Go, etc.)
- Keyword search + LLM for answers
- Works with Ollama (local) or Gemini (cloud)
- Lightweight - no heavy dependencies

## Environment Variables
| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | - | Google Gemini API key |
| `GOOGLE_API_KEY` | - | Alias for Gemini key |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama endpoint |
| `LLM_PROVIDER` | auto | `gemini` or `ollama` |
| `LLM_MODEL` | auto | Model name |
| `CHAT_MODEL` | auto | Chat model for RepoChat |

## License
MIT