"""
GitHub Trending Daily Scraper
Scrapes https://github.com/trending?since=daily and outputs structured JSON.
"""

import json
import os
from datetime import datetime
from urllib.request import Request, urlopen
from html.parser import HTMLParser


TRENDING_URL = "https://github.com/trending?since=daily"


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

        # Description paragraph: <p class="col-9 color-fg-muted my-1 tmp-pr-4">
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

    output_file = os.path.join(output_dir, f"{file_date}GithubTrendingDaily.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(repos, f, ensure_ascii=False, indent=2)

    print(f"Done - {len(repos)} repos saved to {output_file}")


if __name__ == "__main__":
    main()
