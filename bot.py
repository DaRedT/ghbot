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
  NOUS_REFRESH_TOKEN  - Nous OAuth refresh token (GitHub Secret, rotating-safe)
  OLLAMA_URL          - Ollama endpoint (optional, default http://127.0.0.1:11434)
  LLM_PROVIDER        - "nous", "gemini" or "ollama" (default: nous if RT present)
  LLM_MODEL           - model name (default: tencent/hy4-flash:free)
"""
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse

NOUS_PORTAL = "https://portal.nousresearch.com"
NOUS_CLIENT = "hermes-cli"
NOUS_INFERENCE = "https://inference-api.nousresearch.com/v1"


def _post_form(url, fields, headers=None):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def nous_access_token(refresh_token):
    """Refresh the short-lived invoke-JWT from the (reusable) refresh token."""
    tok = _post_form(
        f"{NOUS_PORTAL}/api/oauth/token",
        {"grant_type": "refresh_token", "client_id": NOUS_CLIENT},
        {"x-nous-refresh-token": refresh_token,
         "Content-Type": "application/x-www-form-urlencoded"},
    )
    return tok.get("access_token")


def call_nous(prompt, model="tencent/hy4-flash:free", refresh_token=None):
    refresh_token = refresh_token or os.environ.get("NOUS_REFRESH_TOKEN")
    if not refresh_token:
        return None
    try:
        access = nous_access_token(refresh_token)
        if not access:
            print("[!] Nous refresh returned no access_token")
            return None
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful GitHub bot. Reply concisely."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 600,
        }
        req = urllib.request.Request(
            f"{NOUS_INFERENCE}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[!] Nous error: {e}")
        return None


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
    """Try providers in order: nous -> ollama -> gemini (fallback chain).

    LLM_PROVIDER can force a single provider ("nous"/"ollama"/"gemini");
    otherwise every configured provider is tried until one answers.
    NOTE: Ollama is only reachable when OLLAMA_URL points at a running
    server (e.g. local device). On GitHub-hosted runners localhost:11434
    has no Ollama, so that step fails fast and is skipped.
    """
    forced = os.environ.get("LLM_PROVIDER", "auto")
    if forced == "nous":
        return call_nous(prompt, model=os.environ.get("LLM_MODEL", "tencent/hy4-flash:free"))
    if forced == "gemini":
        return call_gemini(prompt, model=os.environ.get("LLM_MODEL", "gemini-3.6-flash"))
    if forced == "ollama":
        return call_ollama(prompt, model=os.environ.get("LLM_MODEL", "qwen3:8b"),
                           base=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))

    if os.environ.get("NOUS_REFRESH_TOKEN"):
        result = call_nous(prompt, model=os.environ.get("LLM_MODEL", "tencent/hy4-flash:free"))
        if result:
            return result
        print("[*] Nous failed -> trying Ollama backup")
    result = call_ollama(prompt, model=os.environ.get("LLM_MODEL", "qwen3:8b"),
                         base=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
    if result:
        return result
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        print("[*] Ollama failed -> trying Gemini backup")
        return call_gemini(prompt, model=os.environ.get("LLM_MODEL", "gemini-3.6-flash"))
    return None


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
