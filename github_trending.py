"""
GitHub Trending Daily Scraper
Scrapes https://github.com/trending?since=daily, fetches each repo's README,
and outputs structured JSON with original Markdown content preserved.
"""

import json
import os
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from html.parser import HTMLParser


TRENDING_URL = "https://github.com/trending?since=daily"
API_README_TEMPLATE = "https://api.github.com/repos/{owner}/{name}/readme"


class TrendingParser(HTMLParser):
    """Minimal HTML parser that extracts repo info from GitHub trending page."""

    def __init__(self):
        super().__init__()
        self.repos = []
        self._in_article = False
        self._current = {}
        self._capture = None
        self._text_buf = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "article" and "Box-row" in attrs_dict.get("class", ""):
            self._in_article = True
            self._current = {}
            return

        if not self._in_article:
            return

        if tag == "h2":
            self._capture = "h2"
            self._text_buf = ""
            return

        if tag == "a" and self._capture == "h2":
            href = attrs_dict.get("href", "")
            if href.startswith("/"):
                self._current["href"] = href

        if tag == "p":
            cls = attrs_dict.get("class", "")
            if "col-9" in cls and "color-fg-muted" in cls and "my-1" in cls:
                self._capture = "desc"
                self._text_buf = ""

    def handle_endtag(self, tag):
        if tag == "article" and self._in_article:
            if self._current.get("href"):
                parts = self._current["href"].strip("/").split("/")
                owner = parts[0] if len(parts) >= 1 else ""
                name = parts[1] if len(parts) >= 2 else ""
                self.repos.append({
                    "name": name,
                    "owner": owner,
                    "description": self._current.get("description", ""),
                    "url": f"https://github.com/{owner}/{name}",
                })
            self._in_article = False
            self._current = {}
            self._capture = None
            return

        if tag == "h2" and self._capture == "h2":
            self._capture = None

        if tag == "p" and self._capture == "desc":
            self._current["description"] = self._text_buf.strip()
            self._capture = None

    def handle_data(self, data):
        if self._capture in ("h2", "desc"):
            self._text_buf += data


def fetch_trending(url=TRENDING_URL):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_trending(html):
    parser = TrendingParser()
    parser.feed(html)
    return parser.repos


def fetch_readme(owner, name):
    """Fetch the raw Markdown README via GitHub API."""
    api_url = API_README_TEMPLATE.format(owner=owner, name=name)
    req = Request(api_url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/vnd.github.raw",
    })
    try:
        with urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8")
    except HTTPError as e:
        if e.code == 404:
            return ""
        print(f"  HTTP {e.code} fetching README for {owner}/{name}")
    except URLError as e:
        print(f"  URL error fetching README for {owner}/{name}: {e.reason}")
    except Exception as e:
        print(f"  Error fetching README for {owner}/{name}: {e}")
    return ""


def main():
    today = datetime.now()
    date_str = today.strftime("%y_%m_%d")
    file_date = today.strftime("%y%m%d")

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OUTPUT", date_str)
    os.makedirs(output_dir, exist_ok=True)

    print("Fetching GitHub trending page ...")
    html = fetch_trending()
    repos = parse_trending(html)

    if not repos:
        print("Warning: no repos parsed. The page structure may have changed.")
        debug_path = os.path.join(output_dir, "_raw_debug.html")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Raw HTML saved to {debug_path} for debugging.")

    # Fetch README for each repo
    print(f"Fetching README for {len(repos)} repos ...")
    for i, repo in enumerate(repos, 1):
        owner, name = repo["owner"], repo["name"]
        print(f"  [{i}/{len(repos)}] {owner}/{name} ...", end=" ", flush=True)
        readme = fetch_readme(owner, name)
        repo["readme"] = readme
        status = "OK" if readme else "EMPTY/NOT FOUND"
        print(status)
        # Be polite to the API — small delay between requests
        if i < len(repos):
            time.sleep(0.5)

    output_file = os.path.join(output_dir, f"{file_date}GithubTrendingDaily.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(repos, f, ensure_ascii=False, indent=2)

    readme_count = sum(1 for r in repos if r["readme"])
    print(f"Done - {len(repos)} repos ({readme_count} with README) saved to {output_file}")


if __name__ == "__main__":
    main()
