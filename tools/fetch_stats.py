"""Fetch profile stats into cache/.

Reads GITHUB_TOKEN. On any failure the previous cache is left untouched so the
card keeps rendering. Lines of code are memoised in cache/loc.json by the
default-branch head OID.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
STATS_PATH = CACHE / "stats.json"
CALENDAR_PATH = CACHE / "calendar.json"
LOC_PATH = CACHE / "loc.json"
LOGIN = "usamakhangt4"
API = "https://api.github.com/graphql"
WEEKS = 53
LOC_VERSION = 2
_SKIP_BASENAMES = frozenset({"package-lock.json", "pnpm-lock.yaml", "yarn.lock"})
_SKIP_DIRECTORIES = frozenset({"dist", "build", ".next", "node_modules"})
_RATE_LOCK = threading.Lock()
_THREAD_STATE = threading.local()


class GitHubError(Exception):
    pass


def _token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise GitHubError("GITHUB_TOKEN is not set")
    return token


def gql(query: str, variables: dict[str, object] | None = None) -> dict[str, object]:
    response = requests.post(
        API,
        json={"query": query, "variables": variables or {}},
        headers={
            "Authorization": f"Bearer {_token()}",
            "User-Agent": "usamakhangt4-profile-card",
            "Accept": "application/vnd.github+json",
        },
        timeout=60,
    )
    if response.status_code != 200:
        raise GitHubError(f"GitHub HTTP {response.status_code}")
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        message = errors[0].get("message", "GraphQL error")
        raise GitHubError(message)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise GitHubError("GraphQL response had no data")
    return data


def _read(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return None
    return loaded


def _write(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _year_ranges(created_at: str) -> list[tuple[datetime, datetime]]:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    ranges: list[tuple[datetime, datetime]] = []
    year = created.year
    while year <= now.year:
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
        if end >= created and start <= now:
            ranges.append((max(start, created), min(end, now)))
        year += 1
    return ranges


def _commit_total(created_at: str) -> int:
    ranges = _year_ranges(created_at)
    declarations = ", ".join(f"$f{index}: DateTime!, $t{index}: DateTime!" for index in range(len(ranges)))
    fields = " ".join(
        f"y{index}: contributionsCollection(from: $f{index}, to: $t{index}) {{ totalCommitContributions }}"
        for index in range(len(ranges))
    )
    variables: dict[str, object] = {}
    for index, (start, end) in enumerate(ranges):
        variables[f"f{index}"] = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        variables[f"t{index}"] = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = gql(f'query({declarations}) {{ user(login: "{LOGIN}") {{ {fields} }} }}', variables)
    user = data["user"]
    if not isinstance(user, dict):
        raise GitHubError("missing user in commit query")
    total = 0
    for index in range(len(ranges)):
        window = user[f"y{index}"]
        if not isinstance(window, dict):
            raise GitHubError("missing contribution window")
        total += int(window["totalCommitContributions"])
    return total


def _profile() -> tuple[str, str, int]:
    data = gql(
        f"""
        query {{
          user(login: "{LOGIN}") {{
            id
            createdAt
            followers {{ totalCount }}
          }}
        }}
        """
    )
    user = data["user"]
    if not isinstance(user, dict):
        raise GitHubError("user lookup failed")
    followers = user["followers"]
    if not isinstance(followers, dict):
        raise GitHubError("follower count missing")
    return str(user["id"]), str(user["createdAt"]), int(followers["totalCount"])


def _paginate(field: str, extra_args: str, selection: str) -> tuple[int, list[dict[str, object]]]:
    nodes: list[dict[str, object]] = []
    cursor: str | None = None
    total = 0
    while True:
        query = f"""
        query($cursor: String) {{
          user(login: "{LOGIN}") {{
            {field}(first: 50, after: $cursor, {extra_args}) {{
              totalCount
              pageInfo {{ hasNextPage endCursor }}
              nodes {{ {selection} }}
            }}
          }}
        }}
        """
        data = gql(query, {"cursor": cursor})
        user = data["user"]
        if not isinstance(user, dict):
            raise GitHubError(f"{field} lookup failed")
        page = user[field]
        if not isinstance(page, dict):
            raise GitHubError(f"{field} page missing")
        total = int(page["totalCount"])
        raw_nodes = page["nodes"]
        if not isinstance(raw_nodes, list):
            raise GitHubError(f"{field} nodes missing")
        for node in raw_nodes:
            if isinstance(node, dict):
                nodes.append(node)
        info = page["pageInfo"]
        if not isinstance(info, dict) or not info.get("hasNextPage"):
            break
        cursor = str(info["endCursor"])
    return total, nodes


def _repo_record(node: dict[str, object]) -> tuple[str, str] | None:
    name = node.get("nameWithOwner")
    branch = node.get("defaultBranchRef")
    if not isinstance(name, str) or not isinstance(branch, dict):
        return None
    target = branch.get("target")
    if not isinstance(target, dict) or not isinstance(target.get("oid"), str):
        return None
    return name, str(target["oid"])


def _excluded_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if name in _SKIP_BASENAMES or name.endswith((".min.js", ".map", ".svg")):
        return True
    directories = normalized.split("/")[:-1]
    return any(part in _SKIP_DIRECTORIES for part in directories)


def _notebook_source_delta(patch: str) -> tuple[int, int]:
    """Count notebook diff lines outside `"outputs"` arrays."""
    added = 0
    deleted = 0
    in_outputs = False
    outputs_indent: int | None = None
    for raw in patch.splitlines():
        if not raw or raw[0] not in "+- " or raw.startswith(("+++", "---")):
            continue
        body = raw[1:]
        indent = len(body) - len(body.lstrip(" "))
        stripped = body.strip()
        if stripped.startswith('"outputs"'):
            in_outputs = True
            outputs_indent = indent
            continue
        if in_outputs and outputs_indent is not None and indent <= outputs_indent and stripped.startswith("]"):
            in_outputs = False
            continue
        if in_outputs or len(stripped) > 180:
            continue
        if raw[0] == "+":
            added += 1
        elif raw[0] == "-":
            deleted += 1
    return added, deleted


def _file_delta(entry: dict[str, object]) -> tuple[int, int]:
    filename = str(entry.get("filename") or "")
    if _excluded_path(filename):
        return 0, 0
    additions = int(entry.get("additions") or 0)
    deletions = int(entry.get("deletions") or 0)
    if not filename.endswith(".ipynb"):
        return additions, deletions
    patch = entry.get("patch")
    if not isinstance(patch, str) or not patch:
        return 0, 0
    return _notebook_source_delta(patch)


def _session() -> requests.Session:
    session = getattr(_THREAD_STATE, "session", None)
    if isinstance(session, requests.Session):
        return session
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {_token()}",
            "User-Agent": "usamakhangt4-profile-card",
            "Accept": "application/vnd.github+json",
        }
    )
    _THREAD_STATE.session = session
    return session


def _rest(url: str, accept: str) -> requests.Response:
    response: requests.Response | None = None
    for attempt in range(5):
        response = _session().get(url, headers={"Accept": accept}, timeout=120)
        limited = response.status_code in {403, 429} and (
            response.headers.get("X-RateLimit-Remaining") == "0"
            or "rate limit" in response.text.lower()
            or response.status_code == 429
        )
        if limited:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = int(retry_after)
            else:
                reset = int(response.headers.get("X-RateLimit-Reset") or "0")
                delay = max(1, reset - int(time.time()) + 1)
            with _RATE_LOCK:
                time.sleep(min(delay, 90))
            continue
        if response.status_code >= 500 and attempt < 4:
            time.sleep(1.5 * (attempt + 1))
            continue
        return response
    if response is None:
        raise GitHubError(f"no response from {url}")
    return response


def _diff_delta(owner: str, repo: str, sha: str) -> tuple[int, int]:
    response = _rest(f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}", "application/vnd.github.diff")
    if response.status_code != 200:
        raise GitHubError(f"{owner}/{repo}@{sha[:7]} diff HTTP {response.status_code}")
    added = 0
    deleted = 0
    current = ""
    skip = False
    notebook: list[str] = []

    def flush() -> None:
        nonlocal added, deleted, notebook
        if skip or not current:
            notebook = []
            return
        if current.endswith(".ipynb"):
            file_added, file_deleted = _notebook_source_delta("\n".join(notebook))
            added += file_added
            deleted += file_deleted
        else:
            for line in notebook:
                if line.startswith("+") and not line.startswith("+++"):
                    added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deleted += 1
        notebook = []

    for line in response.text.splitlines():
        if line.startswith("diff --git "):
            flush()
            marker = " b/"
            current = line.rsplit(marker, 1)[1] if marker in line else ""
            if current.startswith('"') and current.endswith('"'):
                current = current[1:-1]
            skip = _excluded_path(current)
            continue
        if current and not skip:
            notebook.append(line)
    flush()
    return added, deleted


def _commit_delta(owner: str, repo: str, sha: str) -> tuple[int, int]:
    response = _rest(f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}", "application/vnd.github+json")
    if response.status_code == 404:
        return 0, 0
    if response.status_code != 200:
        raise GitHubError(f"{owner}/{repo}@{sha[:7]} HTTP {response.status_code}")
    payload = response.json()
    files = payload.get("files")
    if not isinstance(files, list):
        files = []
    if len(files) >= 300:
        return _diff_delta(owner, repo, sha)
    added = 0
    deleted = 0
    for entry in files:
        if not isinstance(entry, dict):
            continue
        file_added, file_deleted = _file_delta(entry)
        added += file_added
        deleted += file_deleted
    return added, deleted


def _author_shas(owner: str, repo: str, author_id: str) -> list[str]:
    shas: list[str] = []
    cursor: str | None = None
    while True:
        data = gql(
            """
            query($owner: String!, $name: String!, $author: ID!, $cursor: String) {
              repository(owner: $owner, name: $name) {
                defaultBranchRef {
                  target {
                    ... on Commit {
                      history(first: 100, author: { id: $author }, after: $cursor) {
                        pageInfo { hasNextPage endCursor }
                        nodes { oid }
                      }
                    }
                  }
                }
              }
            }
            """,
            {"owner": owner, "name": repo, "author": author_id, "cursor": cursor},
        )
        repository = data["repository"]
        if not isinstance(repository, dict):
            break
        branch = repository.get("defaultBranchRef")
        if not isinstance(branch, dict):
            break
        target = branch.get("target")
        if not isinstance(target, dict):
            break
        history = target.get("history")
        if not isinstance(history, dict):
            break
        commits = history.get("nodes")
        if not isinstance(commits, list):
            break
        for commit in commits:
            if isinstance(commit, dict) and isinstance(commit.get("oid"), str):
                shas.append(str(commit["oid"]))
        info = history.get("pageInfo")
        if not isinstance(info, dict) or not info.get("hasNextPage"):
            break
        cursor = str(info["endCursor"])
    return shas


def _walk_loc(name: str, author_id: str) -> tuple[int, int]:
    owner, repo = name.split("/", 1)
    shas = _author_shas(owner, repo, author_id)
    if not shas:
        return 0, 0
    print(f"loc {name}: {len(shas)} commits", flush=True)
    added = 0
    deleted = 0
    workers = min(6, len(shas))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for file_added, file_deleted in pool.map(lambda sha: _commit_delta(owner, repo, sha), shas):
            added += file_added
            deleted += file_deleted
    return added, deleted


def _calendar() -> dict[str, object]:
    data = gql(
        f"""
        query {{
          user(login: "{LOGIN}") {{
            contributionsCollection {{
              contributionCalendar {{
                weeks {{
                  contributionDays {{ date contributionCount }}
                }}
              }}
            }}
          }}
        }}
        """
    )
    user = data["user"]
    if not isinstance(user, dict):
        raise GitHubError("calendar user missing")
    collection = user["contributionsCollection"]
    if not isinstance(collection, dict):
        raise GitHubError("calendar missing")
    calendar = collection["contributionCalendar"]
    if not isinstance(calendar, dict):
        raise GitHubError("calendar missing")
    weeks_raw = calendar["weeks"]
    if not isinstance(weeks_raw, list):
        raise GitHubError("calendar weeks missing")
    weeks: list[list[dict[str, object]]] = []
    for week in weeks_raw:
        if not isinstance(week, dict):
            continue
        days_raw = week.get("contributionDays")
        days: list[dict[str, object]] = []
        if isinstance(days_raw, list):
            for day in days_raw:
                if not isinstance(day, dict):
                    continue
                days.append({"count": int(day["contributionCount"]), "date": str(day["date"])})
        if days:
            weeks.append(days)
    if len(weeks) > WEEKS:
        weeks = weeks[-WEEKS:]
    while len(weeks) < WEEKS and weeks:
        first = datetime.fromisoformat(str(weeks[0][0]["date"]))
        padded = []
        for offset in range(7):
            day = first - timedelta(days=7 - offset)
            padded.append({"count": 0, "date": day.date().isoformat()})
        weeks.insert(0, padded)
    total = sum(int(day["count"]) for week in weeks for day in week)
    return {"total": total, "weeks": weeks}


def _loc_cache(author_id: str, repos: dict[str, str]) -> dict[str, object]:
    previous = _read(LOC_PATH) or {}
    old_repos = previous.get("repos") if previous.get("version") == LOC_VERSION else None
    stored: dict[str, object] = old_repos if isinstance(old_repos, dict) else {}
    refreshed: dict[str, object] = {}
    for name in sorted(repos):
        oid = repos[name]
        cached = stored.get(name)
        if isinstance(cached, dict) and cached.get("oid") == oid:
            refreshed[name] = {"added": int(cached["added"]), "deleted": int(cached["deleted"]), "oid": oid}
            continue
        try:
            added, deleted = _walk_loc(name, author_id)
        except GitHubError as exc:
            print(f"loc unchanged for {name}: {exc}", file=sys.stderr)
            if isinstance(cached, dict):
                refreshed[name] = cached
            continue
        refreshed[name] = {"added": added, "deleted": deleted, "oid": oid}
        print(f"loc {name}: ++{added} --{deleted}")
    return {"repos": refreshed, "version": LOC_VERSION}


def collect() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    author_id, created_at, followers = _profile()
    owned_count, owned_nodes = _paginate(
        "repositories",
        "privacy: PUBLIC, ownerAffiliations: [OWNER], isFork: false",
        "nameWithOwner stargazerCount defaultBranchRef { target { oid } }",
    )
    contributed_count, contributed_nodes = _paginate(
        "repositoriesContributedTo",
        "privacy: PUBLIC, includeUserRepositories: true, contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]",
        "nameWithOwner defaultBranchRef { target { oid } }",
    )
    stars = 0
    repos: dict[str, str] = {}
    for node in owned_nodes:
        stars += int(node.get("stargazerCount") or 0)
        record = _repo_record(node)
        if record:
            repos[record[0]] = record[1]
    for node in contributed_nodes:
        record = _repo_record(node)
        if record:
            repos.setdefault(record[0], record[1])
    loc = _loc_cache(author_id, repos)
    repo_cache = loc["repos"]
    added = deleted = 0
    if isinstance(repo_cache, dict):
        for entry in repo_cache.values():
            if isinstance(entry, dict):
                added += int(entry.get("added") or 0)
                deleted += int(entry.get("deleted") or 0)
    stats = {
        "commits": _commit_total(created_at),
        "followers": followers,
        "loc_added": added,
        "loc_deleted": deleted,
        "repos_contributed": contributed_count,
        "repos_owned": owned_count,
        "stars": stars,
    }
    return stats, _calendar(), loc


def main() -> int:
    try:
        stats, calendar, loc = collect()
    except (GitHubError, requests.RequestException, OSError, json.JSONDecodeError) as exc:
        print(f"stats fetch failed: {exc}", file=sys.stderr)
        print("keeping the last cache", file=sys.stderr)
        return 0
    _write(STATS_PATH, stats)
    _write(CALENDAR_PATH, calendar)
    _write(LOC_PATH, loc)
    print(
        "cached "
        f"repos={stats['repos_owned']} contributed={stats['repos_contributed']} "
        f"stars={stats['stars']} commits={stats['commits']} followers={stats['followers']} "
        f"loc=++{stats['loc_added']} --{stats['loc_deleted']}"
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
