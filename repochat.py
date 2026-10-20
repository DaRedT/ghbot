#!/usr/bin/env python3
"""
RepoChat - local chatbot for your GitHub repos.

Indexes a local repo (or clones one) and lets you ask questions
about the codebase using an LLM (Ollama or Gemini).

Usage:
  python3 repochat.py /path/to/repo
  python3 repochat.py --clone https://github.com/user/repo
"""
import os
import sys
import json
import subprocess
import argparse
import urllib.request

# --- Config ---
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "auto")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "auto")
MAX_CONTEXT_CHARS = 8000
CHUNK_SIZE = 1500

IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".idea", ".vscode"}
IGNORE_EXTS = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".ttf", ".zip", ".tar", ".gz", ".bin", ".exe"}
CODE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".kt", ".go", ".rs", ".c", ".cpp", ".h", ".md", ".yaml", ".yml", ".json", ".toml", ".sh", ".sql", ".html", ".css"}


def call_llm(prompt, system=None):
    provider = LLM_PROVIDER
    if provider == "auto":
        provider = "gemini" if GEMINI_KEY else "ollama"

    if provider == "gemini":
        model = CHAT_MODEL if CHAT_MODEL != "auto" else "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": system}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        payload = {"contents": contents}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                return result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            return f"[Gemini error: {e}]"
    else:
        model = CHAT_MODEL if CHAT_MODEL != "auto" else "qwen3:8b"
        url = f"{OLLAMA_URL}/api/generate"
        full_prompt = (system + "\n\n" if system else "") + prompt
        payload = {"model": model, "prompt": full_prompt, "stream": False}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
                return result.get("response", "")
        except Exception as e:
            return f"[Ollama error: {e}]"


def collect_files(repo_path):
    files = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in IGNORE_EXTS:
                continue
            if ext not in CODE_EXTS and ext != "":
                continue
            fpath = os.path.join(root, fn)
            rel = os.path.relpath(fpath, repo_path)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if len(content) < 10:
                    continue
                files.append((rel, content))
            except Exception:
                continue
    return files


def chunk_text(text, path):
    chunks = []
    # Split by lines, group into chunks
    lines = text.split("\n")
    current = []
    current_len = 0
    for line in lines:
        if current_len + len(line) > CHUNK_SIZE and current:
            chunks.append((path, "\n".join(current)))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        chunks.append((path, "\n".join(current)))
    return chunks


def build_index(repo_path):
    files = collect_files(repo_path)
    index = []
    for path, content in files:
        index.extend(chunk_text(content, path))
    print(f"[*] Indexed {len(files)} files, {len(index)} chunks")
    return index


def search_index(index, query, top_k=5):
    query_terms = set(query.lower().split())
    scored = []
    for path, chunk in index:
        chunk_lower = chunk.lower()
        score = sum(1 for term in query_terms if term in chunk_lower)
        # Bonus for path match
        if any(term in path.lower() for term in query_terms):
            score += 2
        if score > 0:
            scored.append((score, path, chunk))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]


def chat_loop(index, repo_name):
    print(f"\nRepoChat ready. Repo: {repo_name}")
    print("Type your question (or 'quit' to exit, 'files' to list indexed files).\n")
    history = []
    while True:
        try:
            q = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not q:
            continue
        if q.lower() in ("quit", "exit", "q"):
            break
        if q.lower() == "files":
            paths = sorted(set(p for _, p, _ in [(0, c[0], c[1]) for c in [(i[0], i[1]) for i in [(x[1], x[2]) for x in [(0, i[0], i[1]) for i in index]]]]))
            # simpler:
            paths = sorted(set(i[0] for i in index))
            for p in paths[:50]:
                print(f"  {p}")
            if len(paths) > 50:
                print(f"  ... and {len(paths)-50} more")
            continue

        # Search
        results = search_index(index, q, top_k=5)
        context = ""
        for score, path, chunk in results:
            context += f"\n--- {path} ---\n{chunk}\n"
        context = context[:MAX_CONTEXT_CHARS]

        system = (
            "You are a helpful coding assistant. Answer questions about the codebase "
            "based on the provided context. Be concise and specific. "
            "If you don't know, say so."
        )
        prompt = f"Context from repository:\n{context}\n\nQuestion: {q}\n\nAnswer:"

        print("Bot: ", end="", flush=True)
        response = call_llm(prompt, system=system)
        print(response)
        print()
        history.append((q, response))


def clone_repo(url, dest):
    print(f"[*] Cloning {url}...")
    subprocess.run(["git", "clone", "--depth", "1", url, dest], check=True)
    return dest


def main():
    parser = argparse.ArgumentParser(description="RepoChat - chat with your repos")
    parser.add_argument("path", nargs="?", help="local repo path")
    parser.add_argument("--clone", help="clone a repo URL")
    parser.add_argument("--model", default="auto", help="LLM model to use")
    args = parser.parse_args()

    global CHAT_MODEL
    CHAT_MODEL = args.model

    if args.clone:
        dest = os.path.join("/tmp", args.clone.split("/")[-1].replace(".git", ""))
        repo_path = clone_repo(args.clone, dest)
    elif args.path:
        repo_path = os.path.abspath(args.path)
    else:
        print("Usage: repochat.py <path> or --clone <url>")
        sys.exit(1)

    if not os.path.isdir(repo_path):
        print(f"[!] Not a directory: {repo_path}")
        sys.exit(1)

    repo_name = os.path.basename(repo_path)
    index = build_index(repo_path)
    chat_loop(index, repo_name)


if __name__ == "__main__":
    main()
