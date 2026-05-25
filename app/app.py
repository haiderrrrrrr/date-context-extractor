import re
import json
import requests
from flask import Flask, jsonify, request, render_template
from bs4 import BeautifulSoup
import dateparser
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

app = Flask(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MONTH_NAMES = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
    r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)

DATE_PATTERNS = re.compile(
    r"\b(?:"
    # ISO: 2023-01-26
    r"\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
    r"|"
    # DD/MM/YYYY or MM/DD/YYYY slashed/dashed
    r"(?:0?[1-9]|[12]\d|3[01])[\/\-](?:0?[1-9]|1[0-2])[\/\-](?:\d{2}|\d{4})"
    r"|"
    # 26 January 2023  /  26 Jan 2023  /  26th January 2023
    r"(?:0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\s+" + MONTH_NAMES + r"\s+\d{2,4}"
    r"|"
    # January 26, 2023  /  Jan 26 2023
    + MONTH_NAMES + r"\s+(?:0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?,?\s+\d{2,4}"
    r"|"
    # January 2023
    + MONTH_NAMES + r"\s+(?:19|20)\d{2}"
    r")\b",
    re.IGNORECASE,
)

# Standalone year pattern for plain-text date extraction.
YEAR_PATTERN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


def get_selenium_page_source(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.get(url)
    page_source = driver.page_source
    driver.quit()
    return page_source


def fetch_html(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        raise RuntimeError(f"Failed to fetch URL: {e}")


def clean_soup(soup):
    """Strip noise elements before text extraction."""
    # Tags that are never useful
    for tag in soup(["script", "style", "noscript", "head"]):
        tag.decompose()
    # Wikipedia-specific noise: navboxes, reference lists, categories
    noisy_classes = [
        "navbox", "navtable", "reflist", "references",
        "mw-references-wrap", "mw-editsection", "noprint",
        "sidebar", "infobox",           # infoboxes mostly have years in odd context
    ]
    for cls in noisy_classes:
        for tag in soup.find_all(True, class_=cls):
            tag.decompose()
    # By ID
    for tid in ["toc", "catlinks", "mw-navigation", "footer", "p-search"]:
        t = soup.find(id=tid)
        if t:
            t.decompose()
    return soup


def extract_dates_from_text(text):
    """Return list of {date, parsed, context} dicts from plain text."""
    seen = set()
    results = []

    for match in DATE_PATTERNS.finditer(text):
        raw = match.group(0).strip()
        key = raw.lower()
        if key in seen:
            continue
        parsed = dateparser.parse(raw, settings={"PREFER_DAY_OF_MONTH": "first"})
        if not parsed:
            continue
        seen.add(key)
        ctx_start = max(0, match.start() - 80)
        ctx_end = min(len(text), match.end() + 80)
        context = " ".join(text[ctx_start:ctx_end].split())
        results.append({
            "date": raw,
            "parsed": parsed.strftime("%Y-%m-%d"),
            "context": context,
        })

    return results


def extract_meta_dates(soup):
    """Pull dates from <meta> tags and JSON-LD scripts."""
    results = []
    seen = set()

    def add(raw, ctx):
        key = raw.lower()
        if key in seen:
            return
        parsed = dateparser.parse(raw)
        if parsed:
            seen.add(key)
            results.append({
                "date": raw,
                "parsed": parsed.strftime("%Y-%m-%d"),
                "context": ctx,
            })

    for tag in soup.find_all("meta"):
        for attr in ["content", "date", "publishdate"]:
            v = tag.get(attr, "")
            if v:
                add(v, f"Meta tag [{tag.get('name') or tag.get('property') or attr}]")

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if not isinstance(data, dict):
                continue
            for field in ["datePublished", "dateModified", "dateCreated"]:
                if field in data:
                    add(data[field], f"JSON-LD ({field})")
        except (json.JSONDecodeError, TypeError):
            continue

    return results


@app.route("/scrape", methods=["GET"])
def scrape():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        if "dynamic" in request.args:
            html_content = get_selenium_page_source(url)
        else:
            html_content = fetch_html(url)

        soup = BeautifulSoup(html_content, "html.parser")
        soup = clean_soup(soup)

        full_text = soup.get_text(separator=" ")
        # Collapse excessive whitespace
        full_text = re.sub(r"\s+", " ", full_text)

        text_dates = extract_dates_from_text(full_text)
        meta_dates = extract_meta_dates(soup)

        # Merge, skipping meta duplicates already in text
        text_keys = {d["date"].lower() for d in text_dates}
        unique_meta = [d for d in meta_dates if d["date"].lower() not in text_keys]
        all_dates = text_dates + unique_meta

        if not all_dates:
            return jsonify({"message": "No dates found on the page!"}), 404

        return jsonify({"dates": all_dates, "total": len(all_dates)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
