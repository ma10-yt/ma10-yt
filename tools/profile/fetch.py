"""Fetches fresh profile data from GitHub into data/stats.json and data/calendar.json (last 53 weeks of daily contributions).

Environment variables (all optional):
  PROFILE_TOKEN  classic personal access token (repo + read:user). Lets commit, PR and
                 streak numbers include private work. Falls back to GITHUB_TOKEN.
  GITHUB_TOKEN   the token GitHub Actions provides automatically (public data only).

Each source is fetched independently. If one fails, its previous values are kept,
so a flaky API never blanks out part of the profile.
"""
import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

USER = "ma10-yt"
HACKATHON_WINS = 0
DATA = pathlib.Path(__file__).resolve().parent / "data"
UA = "ma10-yt-profile-updater"


# ─────────────────────────────── helpers ───────────────────────────────
def http_json(url, *, headers=None, body=None, timeout=30):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def graphql(token, query, variables=None):
    res = http_json("https://api.github.com/graphql", headers={"Authorization": f"bearer {token}"},
                    body={"query": query, "variables": variables or {}})
    if res.get("errors"):
        raise RuntimeError("GraphQL error: " + "; ".join(e.get("message", "?") for e in res["errors"]))
    return res["data"]


def load(name, default):
    try:
        return json.loads((DATA / name).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(name, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def warn(msg):
    # "::warning::" makes the message show up as an annotation on the Actions run page
    print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"warning: {msg}", file=sys.stderr)


# ─────────────────────────────── GitHub ────────────────────────────────
PROFILE_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    merged: pullRequests(states: MERGED) { totalCount }
    contributionsCollection { contributionYears }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      nodes {
        name
        stargazerCount
        forkCount
        languages(first: 20) { edges { size node { name } } }
      }
    }
  }
}"""


def years_query(years):
    parts = []
    for y in years:
        parts.append(f"""
    y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") {{
      totalCommitContributions
      contributionCalendar {{ totalContributions weeks {{ contributionDays {{ date contributionCount }} }} }}
    }}""")
    return "query($login: String!) {\n  user(login: $login) {" + "".join(parts) + "\n  }\n}"


def streaks(days, today):
    """days: {date: count}. Current streak may end yesterday if today has no contributions yet."""
    dates = sorted(d for d in days if d <= today)
    longest = run = 0
    for d in dates:
        run = run + 1 if days[d] > 0 else 0
        longest = max(longest, run)
    current, d = 0, today
    if days.get(d, 0) == 0:
        d -= datetime.timedelta(days=1)
    while days.get(d, 0) > 0:
        current += 1
        d -= datetime.timedelta(days=1)
    return current, longest


def fetch_github(token, today):
    u = graphql(token, PROFILE_QUERY, {"login": USER})["user"]
    years = sorted(u["contributionsCollection"]["contributionYears"])
    ydata = graphql(token, years_query(years), {"login": USER})["user"] if years else {}

    days, commits_all, contribs_all = {}, 0, 0
    for y in years:
        c = ydata[f"y{y}"]
        commits_all += c["totalCommitContributions"]
        contribs_all += c["contributionCalendar"]["totalContributions"]
        for w in c["contributionCalendar"]["weeks"]:
            for day in w["contributionDays"]:
                days[datetime.date.fromisoformat(day["date"])] = day["contributionCount"]
    current, longest = streaks(days, today)
    # last 53 weeks, starting on a Sunday like GitHub's own graph (feeds the contribution city)
    start = today - datetime.timedelta(weeks=52)
    start -= datetime.timedelta(days=(start.weekday() + 1) % 7)
    calendar = [[d.isoformat(), days.get(d, 0)] for d in
                (start + datetime.timedelta(days=i) for i in range((today - start).days + 1))]

    repos = u["repositories"]["nodes"]
    langs = {}
    for r in repos:
        for edge in r["languages"]["edges"]:
            langs[edge["node"]["name"]] = langs.get(edge["node"]["name"], 0) + edge["size"]
    cur = ydata.get(f"y{today.year}", {})
    this_year = cur.get("totalCommitContributions", 0)
    contribs_year = cur.get("contributionCalendar", {}).get("totalContributions", 0)
    return {
        "created_at": u["createdAt"],
        "followers": u["followers"]["totalCount"],
        "prs": u["pullRequests"]["totalCount"],
        "prs_merged": u["merged"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "forks": sum(r["forkCount"] for r in repos),
        "repo_stars": {r["name"]: r["stargazerCount"] for r in repos},
        "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        "year": today.year,
        "commits_year": this_year,
        "commits_all": commits_all,
        "contributions_year": contribs_year,
        "contributions_all": contribs_all,
        "streak_current": current,
        "streak_longest": longest,
        "_calendar": calendar,
    }


# ──────────────────────────────── main ─────────────────────────────────
def main():
    today = datetime.datetime.now(datetime.timezone.utc).date()
    stats = load("stats.json", {})
    token = os.environ.get("PROFILE_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        warn("No PROFILE_TOKEN or GITHUB_TOKEN set, skipping GitHub")
        sys.exit(1)

    try:
        gh = fetch_github(token, today)
        save("calendar.json", gh.pop("_calendar"))
        stats.update(gh)
        print("github: ok" + (" (with private contributions)" if os.environ.get("PROFILE_TOKEN") else " (public only)"))
    except Exception as ex:  # noqa: BLE001
        warn(f"GitHub fetch failed, keeping previous stats: {ex}")
        sys.exit(1)

    stats["hackathon_wins"] = HACKATHON_WINS
    stats["updated"] = today.isoformat()
    save("stats.json", stats)


if __name__ == "__main__":
    main()
