#!/usr/bin/env python3
"""Fetch reproducible GitHub profile metrics and inject them into profile files."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


GRAPHQL_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"
STAT_KEYS = (
    "commits",
    "prs",
    "issues",
    "repos",
    "overall",
    "current_streak",
    "longest_streak",
)

PROFILE_QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(privacy: PUBLIC, ownerAffiliations: OWNER) { totalCount }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def api_request(url: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "jeancecilia-profile-stats",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    request = Request(url, data=body, headers=headers, method="POST" if body else "GET")
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API returned HTTP {error.code}: {detail}") from error


def fetch_live_data(login: str, token: str) -> dict[str, Any]:
    graphql = api_request(
        GRAPHQL_URL,
        token,
        {"query": PROFILE_QUERY, "variables": {"login": login}},
    )
    if graphql.get("errors"):
        raise RuntimeError(f"GraphQL errors: {json.dumps(graphql['errors'])}")

    searches: dict[str, int] = {}
    search_queries = {
        "commits": f"author:{login} is:public",
        "prs": f"author:{login} is:pr is:public",
        "issues": f"author:{login} is:issue is:public",
    }
    endpoints = {"commits": "commits", "prs": "issues", "issues": "issues"}
    for key, query in search_queries.items():
        result = api_request(
            f"{REST_URL}/search/{endpoints[key]}?q={quote(query)}&per_page=1",
            token,
        )
        if result.get("incomplete_results"):
            raise RuntimeError(f"GitHub returned incomplete {key} search results")
        searches[key] = int(result["total_count"])

    return {"graphql": graphql, "searches": searches}


def calculate_streaks(days: list[dict[str, Any]]) -> tuple[int, int]:
    ordered = sorted(days, key=lambda day: day["date"])
    counts = [int(day["contributionCount"]) for day in ordered]

    longest = 0
    run = 0
    for count in counts:
        run = run + 1 if count > 0 else 0
        longest = max(longest, run)

    index = len(counts) - 1
    # The final calendar day is still in progress. A zero today does not end
    # a streak that was active yesterday.
    if index >= 0 and counts[index] == 0:
        index -= 1

    current = 0
    while index >= 0 and counts[index] > 0:
        current += 1
        index -= 1

    return current, longest


def build_stats(api_data: dict[str, Any]) -> dict[str, str]:
    user = api_data.get("graphql", {}).get("data", {}).get("user")
    if not user:
        raise RuntimeError("GitHub user was not found in the GraphQL response")

    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = [
        day
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    ]
    current, longest = calculate_streaks(days)
    searches = api_data["searches"]

    return {
        "commits": str(int(searches["commits"])),
        "prs": str(int(searches["prs"])),
        "issues": str(int(searches["issues"])),
        "repos": str(int(user["repositories"]["totalCount"])),
        "overall": str(int(calendar["totalContributions"])),
        "current_streak": f"{current} {'day' if current == 1 else 'days'}",
        "longest_streak": f"{longest} {'day' if longest == 1 else 'days'}",
    }


def replace_stat(text: str, key: str, value: str) -> tuple[str, bool]:
    pattern = re.compile(
        rf"(<!--stat:{re.escape(key)}-->)(.*?)(<!--/stat:{re.escape(key)}-->)"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one marker for '{key}', found {len(matches)}")
    changed = matches[0].group(2) != value
    return pattern.sub(lambda match: f"{match.group(1)}{value}{match.group(3)}", text), changed


def update_files(root: Path, stats: dict[str, str], timestamp: str) -> bool:
    paths = (root / "README.md", root / "docs" / "index.html")
    originals = {path: path.read_text(encoding="utf-8") for path in paths}
    rendered: dict[Path, str] = {}
    changed = False

    for path, original in originals.items():
        text = original
        for key in STAT_KEYS:
            text, stat_changed = replace_stat(text, key, stats[key])
            changed = changed or stat_changed
        rendered[path] = text

    if not changed:
        return False

    timestamp_pattern = re.compile(r"<!--updated: .*?-->")
    for path, text in rendered.items():
        if timestamp_pattern.search(text):
            text = timestamp_pattern.sub(f"<!--updated: {timestamp}-->", text)
        path.write_text(text, encoding="utf-8", newline="\n")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--timestamp")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.fixture:
        api_data = json.loads(args.fixture.read_text(encoding="utf-8"))
    else:
        login = os.environ.get("GH_LOGIN", "jeancecilia")
        token = os.environ.get("GH_TOKEN")
        if not token:
            raise RuntimeError("GH_TOKEN is required for live updates")
        api_data = fetch_live_data(login, token)

    stats = build_stats(api_data)
    timestamp = args.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    changed = update_files(args.root, stats, timestamp)
    print(json.dumps({"changed": changed, "stats": stats}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
