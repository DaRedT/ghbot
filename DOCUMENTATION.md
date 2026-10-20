# AndroBot & RepoChat — Dokumentation

## AndroBot (GitHub Bot)

Automatisch auf neue Issues und Pull Requests antworten via GitHub Actions + LLM.

### Dateien
- `bot.py` — Hauptskript (liest Event, ruft LLM, postet Kommentar)
- `.github/workflows/bot.yml` — GitHub Actions Workflow

### Setup
1. `bot.py` und `.github/workflows/bot.yml` in das Ziel-Repo kopieren
2. GitHub Secret hinzufügen: Settings → Secrets → Actions → `GEMINI_API_KEY`
3. Optional: `LLM_PROVIDER`, `LLM_MODEL` als Secrets setzen

### Funktionsweise
1. GitHub Actions triggert bei `issues: opened` oder `pull_request: opened`
2. `bot.py` liest den Event-Payload aus `GITHUB_EVENT_PATH`
3. Erkennt Event-Typ (Issue oder PR)
4. Baut einen Prompt mit Titel, Body und Autor
5. Ruft LLM auf (Gemini Cloud oder Ollama lokal)
6. Postet die Antwort als Kommentar auf das Issue/PR

### Umgebungsvariablen
| Variable | Default | Beschreibung |
|---|---|---|
| `GITHUB_TOKEN` | (auto) | GitHub API Token (wird von Actions bereitgestellt) |
| `GITHUB_REPOSITORY` | (auto) | `owner/repo` (wird von Actions bereitgestellt) |
| `GITHUB_EVENT_PATH` | (auto) | Pfad zur Event-JSON (wird von Actions bereitgestellt) |
| `GEMINI_API_KEY` | — | Google Gemini API Key |
| `GOOGLE_API_KEY` | — | Alias für Gemini Key |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama Endpoint |
| `LLM_PROVIDER` | auto | `gemini` oder `ollama` |
| `LLM_MODEL` | gemini-3.6-flash | Modellname |

### Manueller Test (lokal)
```bash
# Mock-Event erstellen
mkdir -p /tmp/test
cat > /tmp/test/event.json <<'EOF'
{
  "action": "opened",
  "issue": {
    "number": 1,
    "title": "Test issue",
    "body": "This is a test",
    "user": {"login": "testuser"}
  }
}
EOF

# Bot ausführen
export GITHUB_EVENT_PATH=/tmp/test/event.json
export GITHUB_REPOSITORY="user/repo"
export GEMINI_API_KEY="your-key"
export LLM_PROVIDER=gemini
python3 bot.py
```

### Hinweise
- Timeout: 180s (Gemini 3.6-flash braucht ~75s pro Anfrage)
- Der Bot postet nur bei neuen Issues/PRs, nicht bei Kommentaren
- Für Ollama: Ollama muss lokal laufen und erreichbar sein

---

## RepoChat (Local Chatbot)

Lokaler Chatbot für Codebases — indexiert Dateien und beantwortet Fragen via LLM.

### Dateien
- `repochat.py` — Hauptskript

### Installation
Keine externen Abhängigkeiten nötig (nur Python 3.9+ und Standardbibliothek).

### Nutzung
```bash
# Lokales Repo
python3 repochat.py /pfad/zum/repo

# Repo klonen und chatten
python3 repochat.py --clone https://github.com/user/repo

# Spezifisches Modell
python3 repochat.py /pfad/zum/repo --model qwen3:8b
```

### Befehle im Chat
| Befehl | Beschreibung |
|---|---|
| `quit` / `exit` / `q` | Beenden |
| `files` | Liste aller indexierten Dateien |
| Freitext | Frage an den Bot |

### Funktionsweise
1. Durchläuft das Repo-Verzeichnis (ignoriert `.git`, `node_modules`, etc.)
2. Liest alle Code-Dateien (.py, .js, .ts, .java, .kt, .go, .md, etc.)
3. Teilt Dateien in Chunks (max 1500 Zeichen)
4. Bei einer Frage: Keyword-Suche in den Chunks, Top-5 Ergebnisse als Kontext
5. LLM generiert Antwort basierend auf dem Kontext

### Unterstützte Dateitypen
`.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.java`, `.kt`, `.go`, `.rs`, `.c`, `.cpp`, `.h`, `.md`, `.yaml`, `.yml`, `.json`, `.toml`, `.sh`, `.sql`, `.html`, `.css`

### Umgebungsvariablen
| Variable | Default | Beschreibung |
|---|---|---|
| `GEMINI_API_KEY` | — | Google Gemini API Key |
| `GOOGLE_API_KEY` | — | Alias für Gemini Key |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama Endpoint |
| `LLM_PROVIDER` | auto | `gemini` oder `ollama` |
| `CHAT_MODEL` | auto | Modellname (auto = gemini-3.6-flash oder qwen3:8b) |

### Performance
- Indexierung: ~1s für 5 Dateien / 34 Chunks
- Gemini 3.6-flash: ~75s pro Anfrage
- Ollama (qwen3:8b): ~10-30s pro Anfrage (lokal)

### Android/Termux Hinweise
- Keine externen Pakete nötig (nur Python stdlib)
- Speicherverbrauch minimal (Chunks im RAM)
- Für große Repos: Indexierung kann länger dauern
- Ollama lokal nutzen für Offline-Betrieb

---

## Repos
- AndroPOT: https://github.com/DaRedT/andropot
- ghbot (AndroBot + RepoChat): https://github.com/DaRedT/ghbot

## Autor
Christian D. (DaRedT) — 2026