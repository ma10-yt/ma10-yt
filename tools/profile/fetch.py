"""Fetch fresh GitHub profile data into tools/profile/data/.

The workflow supplies GITHUB_TOKEN automatically. A PROFILE_TOKEN may be
provided when broader/private contribution access is desired.

Writing/blog data is intentionally not part of this profile.
"""
import datetime
import json
import os
import pathlib
import sys
import urllib.request

USER = "ma10-yt"
DATA = pathlib.Path(__file__).resolve().parent / "data"
UA = "ma10-yt-profile-updater"


def http_json(url, *, headers=None, body=None, timeout=30):
    req = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})},
    )
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def graphql(token, query, variables=None):
    res = http_json(
        "https://api.github.com/graphql",
        headers={"Authorization": f"bearer {token}"},
        body={"query": query, "variables": variables or {}},
    )
    if res.get("errors"):
        raise RuntimeError("; ".join(e.get("message", "?") for e in res["errors"]))
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
    print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"warning: {msg}",
          file=sys.stderr)


PROFILE_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    merged: pullRequests(states: MERGED) { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      nodes {
        name
        stargazerCount
        forkCount
        languages(first: 20) { edges { size node { name } } }
      }
    }
    contributionsCollection { contributionYears }
  }
}
"""


def years_query(years):
    parts = []
    for y in years:
        parts.append(f"""
    y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") {{
      totalCommitContributions
      contributionCalendar {{ totalContributions weeks {{ contributionDays {{ date contributionCount }} }} }}
    }}""")
    return "query($login: String!) { user(login: $login) {" + "".join(parts) + "} }"


def streaks(days, today):
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

    start = today - datetime.timedelta(weeks=52)
    start -= datetime.timedelta(days=(start.weekday() + 1) % 7)
    calendar = [[d.isoformat(), days.get(d, 0)] for d in
                (start + datetime.timedelta(days=i)
                 for i in range((today - start).days + 1))]

    repos = u["repositories"]["nodes"]
    langs = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            langs[edge["node"]["name"]] = langs.get(edge["node"]["name"], 0) + edge["size"]

    cur = ydata.get(f"y{today.year}", {})
    this_year = cur.get("totalCommitContributions", 0)
    contribs_year = cur.get("contributionCalendar", {}).get("totalContributions", 0)

    return {
        "created_at": u["createdAt"],
        "followers": u["followers"]["totalCount"],
        "prs": u["pullRequests"]["totalCount"],
        "prs_merged": u["merged"]["totalCount"],
        "stars": sum(repo["stargazerCount"] for repo in repos),
        "forks": sum(repo["forkCount"] for repo in repos),
        "repo_count": len(repos),
        "repo_stars": {repo["name"]: repo["stargazerCount"] for repo in repos},
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
        print("github: ok")
    except Exception as ex:  # noqa: BLE001
        warn(f"GitHub fetch failed, keeping previous stats: {ex}")
        sys.exit(1)

    stats["updated"] = today.isoformat()
    save("stats.json", stats)


if __name__ == "__main__":
    main()
