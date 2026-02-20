#!/usr/bin/env python3
"""Daily job search for an English & American Studies student near Bamberg.

Queries the Bundesagentur für Arbeit (Federal Employment Agency) API for job
listings within 30 km of Bamberg, scores them by relevance to the field, and
creates a GitHub Issue with the top 2 most relevant listings.
If no relevant listings are found, no issue is created.
"""

import os
import sys
from datetime import date

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOCATION = "Bamberg"
RADIUS_KM = 30
MAX_LISTINGS = 2
REGULAR_EMPLOYMENT = 1  # angebotsart value for standard job offers

# Broad search terms to cast a wide net
SEARCH_TERMS = [
    "Englisch",
    "Übersetzer",
    "Redakteur",
    "Texter",
    "Anglistik",
    "Fremdsprache",
]

# Keyword → relevance weight (applied to job title + occupation field)
RELEVANCE_WEIGHTS: dict[str, int] = {
    "anglistik": 5,
    "amerikanistik": 5,
    "englischlehrer": 5,
    "englisch": 4,
    "english": 4,
    "übersetzer": 4,
    "dolmetscher": 4,
    "sprachlehrer": 3,
    "fremdsprache": 3,
    "lektor": 3,
    "texter": 2,
    "redakteur": 2,
    "content": 2,
    "kommunikation": 1,
    "journalist": 1,
    "medien": 1,
}

# ---------------------------------------------------------------------------
# Bundesagentur für Arbeit API
# ---------------------------------------------------------------------------

_BA_API_URL = (
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
)
_BA_HEADERS = {"X-API-Key": "jobboerse-jobsuche"}


def fetch_jobs(keyword: str) -> list[dict]:
    """Return job listings from the BA API matching *keyword* near Bamberg."""
    params = {
        "was": keyword,
        "wo": LOCATION,
        "umkreis": RADIUS_KM,
        "angebotsart": REGULAR_EMPLOYMENT,
        "size": 25,
        "page": 0,
    }
    try:
        resp = requests.get(
            _BA_API_URL,
            headers=_BA_HEADERS,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("stellenangebote") or []
    except (requests.RequestException, ValueError) as exc:
        print(f"Warning: could not fetch jobs for '{keyword}': {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

def score_job(job: dict) -> int:
    """Return a non-negative relevance score for *job*."""
    text = " ".join([
        job.get("titel", ""),
        job.get("beruf", ""),
    ]).lower()
    return sum(w for kw, w in RELEVANCE_WEIGHTS.items() if kw in text)


def collect_top_jobs() -> list[dict]:
    """Fetch all matching jobs, deduplicate, rank, and return the top N."""
    seen: set[str] = set()
    all_jobs: list[dict] = []

    for term in SEARCH_TERMS:
        for job in fetch_jobs(term):
            ref = job.get("refnr") or (job.get("titel"), job.get("arbeitgeber"))
            if ref not in seen:
                seen.add(ref)
                all_jobs.append(job)

    scored = sorted(
        ((score_job(j), j) for j in all_jobs),
        key=lambda x: x[0],
        reverse=True,
    )
    # Only include jobs that are actually relevant (score > 0)
    return [j for score, j in scored[:MAX_LISTINGS] if score > 0]


# ---------------------------------------------------------------------------
# GitHub Issue creation
# ---------------------------------------------------------------------------

def _build_issue_body(jobs: list[dict]) -> str:
    today = date.today().strftime("%B %d, %Y")
    lines = [
        f"## Job Listings – {today}",
        "",
        "Top relevant job listings near Bamberg (30 km radius) for a "
        "Master's student in English and American Studies:",
        "",
    ]
    for i, job in enumerate(jobs, 1):
        title = job.get("titel", "N/A")
        employer = job.get("arbeitgeber", "N/A")
        location = (job.get("arbeitsort") or {}).get("ort", "N/A")
        ref = job.get("refnr", "")
        link = (
            f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}"
            if ref
            else "N/A"
        )
        lines += [
            f"### {i}. {title}",
            f"- **Employer:** {employer}",
            f"- **Location:** {location}",
            f"- **Link:** {link}",
            "",
        ]
    return "\n".join(lines)


def create_github_issue(title: str, body: str) -> None:
    """Create a GitHub Issue via the REST API using GITHUB_TOKEN."""
    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY")

    if not token or not repository:
        print(
            "GITHUB_TOKEN or GITHUB_REPOSITORY not set; cannot create issue.",
            file=sys.stderr,
        )
        sys.exit(1)

    url = f"https://api.github.com/repos/{repository}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = requests.post(
        url,
        json={"title": title, "body": body},
        headers=headers,
        timeout=15,
    )
    if resp.status_code == 201:
        print(f"Issue created: {resp.json()['html_url']}")
    else:
        print(
            f"Failed to create issue ({resp.status_code}): {resp.text}",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    top_jobs = collect_top_jobs()

    if not top_jobs:
        print("No relevant job listings found today. No issue will be created.")
        return

    today = date.today().isoformat()
    issue_title = f"Daily Job Listings – {today}"
    issue_body = _build_issue_body(top_jobs)

    print(f"Found {len(top_jobs)} relevant job(s). Creating issue…")
    create_github_issue(issue_title, issue_body)


if __name__ == "__main__":
    main()
