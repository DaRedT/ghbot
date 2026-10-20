#!/usr/bin/env python3
"""
GitHub Bot - responds to issues and PRs using an LLM.

Runs as a GitHub Actions step or standalone. Reads the event payload
from GITHUB_EVENT_PATH, calls an LLM (Gemini or Ollama), and posts
a comment on the issue/PR.

Environment variables:
  GITHUB_TOKEN        - GitHub API token (auto-provided in Actions)
  GITHUB_REPOSITORY   - owner/repo (auto-provided in Actions)
  GITHUB_EVENT_PATH   - path to event JSON (auto-provided in Actions)
  GEMINI_API_KEY      - Google Gemini API key (optional)
  OLLAMA_URL          - Ollama endpoint (optional, default http://127.0.0.1:11434)
  LLM_PROVIDER        - "gemini" or "ollama" (default: gemini if key present)
  LLM_MODEL           - model name (default: gemini-3.6-flash or qwen3:8b)
"""
import json
import os
import sys
import subprocess
import urllib.request
import urllib.error


def get_event():
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path or not os.path.exists(path):
        print("[!] No GITHUB_EVENT_PATH found")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def call_gemini(prompt, model="gemini-3.6-flash", api_key=None):
    api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read())
            return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[!] Gemini error: {e}")
        return None


def call_ollama(prompt, model="qwen3:8b", base="http://127.0.0.1:11434"):
    url = f"{base}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result.get("response", "")
    except Exception as e:
        print(f"[!] Ollama error: {e}")
        return None


def call_llm(prompt):
    provider = os.environ.get("LLM_PROVIDER", "auto")
    if provider == "auto":
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            provider = "gemini"
        else:
            provider = "ollama"
    if provider == "gemini":
        model = os.environ.get("LLM_MODEL", "gemini-3.6-flash")
        return call_gemini(prompt, model=model)
    else:
        model = os.environ.get("LLM_MODEL", "qwen3:8b")
        base = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
        return call_ollama(prompt, model=model, base=base)


def github_api(method, endpoint, data=None, token=None):
    token = token or os.environ.get("GITHUB_TOKEN")
    url = f"https://api.github.com{endpoint}"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"[!] GitHub API error {e.code}: {e.read().decode()[:300]}")
        return None


def post_comment(repo, issue_number, body):
    return github_api("POST", f"/repos/{repo}/issues/{issue_number}/comments", {"body": body})


def build_prompt(event, event_type):
    if event_type == "issues":
        issue = event.get("issue", {})
        title = issue.get("title", "")
        body = issue.get("body", "") or ""
        user = issue.get("user", {}).get("login", "unknown")
        return (
            "You are a helpful GitHub bot. A new issue was opened. "
            "Provide a concise, helpful response. If it's a bug report, "
            "acknowledge and suggest debugging steps. If it's a feature request, "
            "acknowledge and discuss feasibility. Keep it under 200 words.\n\n"
            f"Issue title: {title}\n"
            f"Issue body: {body[:2000]}\n"
            f"Opened by: {user}\n"
        )
    elif event_type == "pull_request":
        pr = event.get("pull_request", {})
        title = pr.get("title", "")
        body = pr.get("body", "") or ""
        user = pr.get("user", {}).get("login", "unknown")
        return (
            "You are a helpful GitHub bot. A new PR was opened. "
            "Provide a brief review summary: what changed, potential concerns, "
            "and suggestions. Keep it under 200 words.\n\n"
            f"PR title: {title}\n"
            f"PR body: {body[:2000]}\n"
            f"Opened by: {user}\n"
        )
    return None


def main():
    event = get_event()
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("[!] GITHUB_REPOSITORY not set")
        sys.exit(1)

    # Determine event type
    if "issue" in event and "pull_request" not in event:
        event_type = "issues"
        number = event["issue"]["number"]
    elif "pull_request" in event:
        event_type = "pull_request"
        number = event["pull_request"]["number"]
    else:
        print("[!] Unknown event type")
        sys.exit(1)

    prompt = build_prompt(event, event_type)
    if not prompt:
        sys.exit(1)

    print(f"[*] Processing {event_type} #{number} in {repo}")
    response = call_llm(prompt)
    if not response:
        print("[!] LLM returned no response")
        sys.exit(1)

    comment = f"**AndroBot** (AI-assisted)\n\n{response}\n\n---\n*Powered by AndroBot*"
    result = post_comment(repo, number, comment)
    if result:
        print(f"[+] Comment posted: {result.get('html_url', '')}")
    else:
        print("[!] Failed to post comment")
        sys.exit(1)


if __name__ == "__main__":
    main()
