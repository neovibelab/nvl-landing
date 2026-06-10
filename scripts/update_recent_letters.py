#!/usr/bin/env python3
"""랜딩(index.html)의 '최근 발행 레터' 블록을 Maily API로 갱신한다.

- 소스: https://api.maily.so/api/draft.briefing/notes.json
- 대상: index.html 의 <!-- RECENT-LETTERS:START --> ~ <!-- RECENT-LETTERS:END --> 사이
- 조건: status == 'published' 만 (hidden_published 제외), 최신 2건
- 변경이 없으면 아무것도 쓰지 않고 종료 (CI에서 커밋 스킵 판단용)

토큰 탐색 순서:
  1) 환경변수 MAILY_API_KEY (GitHub Actions)
  2) ../claude_API/maily_API.txt (로컬 모노레포 관례)
  3) ../.env 의 MAILY_API_KEY= (로컬 모노레포 관례)

사용: python scripts/update_recent_letters.py [--dry-run]
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
INDEX = REPO_DIR / "index.html"
PROFILE = "draft.briefing"
COUNT = 2
MARKER_RE = re.compile(
    r"(<!-- RECENT-LETTERS:START[^>]*-->)(.*?)(\n?[ \t]*<!-- RECENT-LETTERS:END[^>]*-->)",
    re.DOTALL,
)


def load_token() -> str | None:
    key = os.environ.get("MAILY_API_KEY", "").strip()
    if key:
        return key if key.startswith("Bearer ") else f"Bearer {key}"
    token_file = REPO_DIR.parent / "claude_API" / "maily_API.txt"
    if token_file.exists():
        t = token_file.read_text(encoding="utf-8").strip()
        if t:
            return t if t.startswith("Bearer ") else f"Bearer {t}"
    env_file = REPO_DIR.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("MAILY_API_KEY="):
                k = line.split("=", 1)[1].strip()
                if k:
                    return k if k.startswith("Bearer ") else f"Bearer {k}"
    return None


def fetch_notes(token: str) -> list[dict]:
    url = f"https://api.maily.so/api/{PROFILE}/notes.json"
    req = urllib.request.Request(url, headers={"Authorization": token})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data if isinstance(data, list) else data.get("notes", [])


def pick_recent(notes: list[dict]) -> list[dict]:
    published = [
        n for n in notes
        if n.get("status") == "published" and n.get("published_at") and n.get("ext_id")
    ]
    published.sort(key=lambda n: n["published_at"], reverse=True)
    return published[:COUNT]


def render_card(note: dict) -> str:
    ext_id = note["ext_id"]
    title = html.escape(note.get("title") or "(제목 없음)")
    subtitle = html.escape(note.get("subtitle") or "")
    paid = note.get("posting_type") == "membership_only"
    badge_cls = "paid" if paid else "free"
    badge = "PAID" if paid else "FREE"
    pub = datetime.fromisoformat(note["published_at"].replace("Z", "+00:00"))
    date = pub.strftime("%Y.%m.%d")
    url = f"https://maily.so/{PROFILE}/posts/{ext_id}"
    sub_html = f'\n          <p class="letter-sub kr">{subtitle}</p>' if subtitle else ""
    return (
        f'        <a class="letter-card" href="{url}" target="_blank" rel="noopener" '
        f"onclick=\"gtag('event','recent_letter_click',{{letter_id:'{ext_id}'}})\">\n"
        f'          <div class="letter-meta"><span class="letter-date">{date}</span>'
        f'<span class="letter-badge {badge_cls}">{badge}</span></div>\n'
        f'          <h4 class="letter-title kr">{title}</h4>{sub_html}\n'
        f"        </a>"
    )


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    token = load_token()
    if not token:
        print("[error] MAILY_API_KEY 없음 (환경변수 또는 로컬 토큰 파일)", file=sys.stderr)
        return 1

    try:
        notes = fetch_notes(token)
    except Exception as e:
        print(f"[error] Maily API 호출 실패: {e}", file=sys.stderr)
        return 1

    recent = pick_recent(notes)
    if not recent:
        # API가 비정상 응답이면 기존 블록을 지우지 않고 그대로 둔다
        print("[error] published 레터 0건 — 갱신 중단", file=sys.stderr)
        return 1

    block = "\n".join(render_card(n) for n in recent)

    src = INDEX.read_text(encoding="utf-8")
    m = MARKER_RE.search(src)
    if not m:
        print("[error] index.html에서 RECENT-LETTERS 마커를 찾지 못함", file=sys.stderr)
        return 1

    updated = src[: m.start()] + m.group(1) + "\n" + block + m.group(3) + src[m.end():]
    if updated == src:
        print("변경 없음")
        return 0

    if dry_run:
        print("[dry-run] 갱신 예정 레터:")
    else:
        INDEX.write_text(updated, encoding="utf-8", newline="\n")
        print("index.html 갱신 완료:")
    for n in recent:
        print(f"  - [{n['published_at'][:10]}] {n.get('title','')}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
