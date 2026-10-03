"""Update dynamic alt text in README.md from generated GitHub data."""
import datetime
import html
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
README = HERE.parent.parent / "README.md"
DATA = HERE / "data"


def days(n):
    return f"{n} day" if n == 1 else f"{n} days"


def stats_alt(d):
    since = datetime.date.fromisoformat(d["created_at"][:10])
    langs = sorted(d["languages"].items(), key=lambda kv: -kv[1])[:5]
    parts = [
        f'{d["stars"]} total stars',
        f'{d["contributions_year"]} contributions in {d["year"]}, {d["contributions_all"]} all time',
        f'{d["prs"]} pull requests ({d["prs_merged"]} merged)',
        f'current streak {days(d["streak_current"])}, longest {days(d["streak_longest"])}',
        f'{d["followers"]} followers',
        f'{d["forks"]} forks',
        f'member since {since:%B %Y}',
        f'{d["repo_count"]} public repositories',
    ]
    return html.escape("Stats: " + "; ".join(parts) +
                       ". Top languages: " + ", ".join(k for k, _ in langs) + ".", quote=True)


def city_alt(calendar):
    total = sum(n for _, n in calendar)
    busiest = max(calendar, key=lambda t: t[1]) if calendar else None
    text = f"Contribution city: an isometric night skyline with one building per day of the last year. {total:,} contributions"
    if busiest and busiest[1]:
        d = datetime.date.fromisoformat(busiest[0])
        text += f", busiest day {d:%B} {d.day} with {busiest[1]}"
    return html.escape(text + ".", quote=True)


def main():
    stats = json.loads((DATA / "stats.json").read_text())
    s = README.read_text()

    s = re.sub(
        r'(<img src="\./assets/stats\.svg"[^>]*?alt=")[^"]*(")',
        lambda m: m.group(1) + stats_alt(stats) + m.group(2),
        s,
    )

    cal_file = DATA / "calendar.json"
    if cal_file.exists():
        s = re.sub(
            r'(<img src="\./assets/contribution-city\.svg"[^>]*?alt=")[^"]*(")',
            lambda m: m.group(1) + city_alt(json.loads(cal_file.read_text())) + m.group(2),
            s,
        )

    README.write_text(s)
    print("README updated")


if __name__ == "__main__":
    main()
