import json
import re
import os
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from playwright.sync_api import sync_playwright

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ==========================================
# 1. BBC SOUNDS SCRAPER (Stockport County)
# ==========================================
BBC_URL = "https://www.bbc.co.uk/sounds/brand/p0kfv035"
BBC_PROGRAMMES_URL = "https://www.bbc.co.uk/programmes/p0kfv035/episodes/player"
BBC_FILENAME = "BBC Sport - Stockport County.xml"
BBC_FEED_TITLE = "BBC Sport - Stockport County"

def load_cached_dates(filename):
    cache = {}
    if not os.path.exists(filename):
        return cache
    try:
        tree = ET.parse(filename)
        for item in tree.findall(".//item"):
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            if link_el is not None and pub_el is not None and link_el.text and pub_el.text:
                cache[link_el.text.strip()] = parsedate_to_datetime(pub_el.text.strip())
    except Exception:
        pass
    return cache

def extract_image_url(item):
    img_el = item.select_one("img")
    if not img_el:
        return ""
    img_url = ""
    srcset = img_el.get("srcset") or img_el.get("data-srcset") or ""
    if srcset:
        candidates = [s.strip().split(" ")[0] for s in srcset.split(",") if s.strip()]
        if candidates:
            img_url = candidates[-1]
    if not img_url:
        img_url = img_el.get("data-src") or img_el.get("src") or ""
    if img_url.startswith("data:image") or not img_url:
        return ""
    img_url = img_url.replace("{recipe}", "1280x720")
    img_url = re.sub(r'/ic/\d+x\d+/', '/ic/1280x720/', img_url)
    return img_url

def fetch_episode_pub_date(pid):
    ep_url = f"https://www.bbc.co.uk/programmes/{pid}"
    try:
        resp = requests.get(ep_url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for obj in items:
                    date_str = obj.get("datePublished") or obj.get("uploadDate") or obj.get("startDate")
                    if date_str:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
        meta_date = soup.select_one("meta[property='article:published_time'], meta[name='DCTERMS.created']")
        if meta_date and meta_date.get("content"):
            dt = datetime.fromisoformat(meta_date["content"].replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        time_el = soup.select_one("time[datetime]")
        if time_el and time_el.get("datetime"):
            dt = datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception as e:
        print(f"Could not fetch date for {pid}: {e}")
    return None

def scrape_bbc_sounds():
    print(f"Fetching {BBC_PROGRAMMES_URL}...")
    cached_dates = load_cached_dates(BBC_FILENAME)
    response = requests.get(BBC_PROGRAMMES_URL, headers=HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    fg = FeedGenerator()
    fg.title(BBC_FEED_TITLE)
    fg.link(href=BBC_URL, rel="alternate")
    fg.description(f"Latest episodes from {BBC_FEED_TITLE}")

    episodes = []
    seen_ids = set()

    for item in soup.select("[data-pid]"):
        pid = item.get("data-pid")
        if not pid or pid in seen_ids or pid == "p0kfv035":
            continue
        title_el = item.select_one(".programme__title, h2, h3")
        if not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        synopsis_el = item.select_one(".programme__synopsis, p")
        synopsis = synopsis_el.get_text(" ", strip=True) if synopsis_el else ""
        image_url = extract_image_url(item)
        sounds_link = f"https://www.bbc.co.uk/sounds/play/{pid}"
        seen_ids.add(pid)
        episodes.append({
            "id": pid,
            "title": title,
            "link": sounds_link,
            "synopsis": synopsis,
            "image": image_url
        })

    for ep in episodes[:20]:
        pub_date = cached_dates.get(ep["link"])
        if not pub_date:
            print(f"Fetching date for {ep['id']}...")
            pub_date = fetch_episode_pub_date(ep["id"])
        fe = fg.add_entry()
        fe.id(ep["link"])
        fe.title(ep["title"])
        fe.link(href=ep["link"])
        if pub_date:
            fe.pubDate(pub_date)
        if ep["image"]:
            fe.enclosure(url=ep["image"], length="0", type="image/jpeg")
            desc_html = f'<p><img src="{ep["image"]}" alt="{ep["title"]}" /></p><p>{ep["synopsis"]}</p>'
        else:
            desc_html = ep["synopsis"]
        if desc_html:
            fe.description(desc_html)

    fg.rss_file(BBC_FILENAME, pretty=True)
    print(f"Saved '{BBC_FILENAME}' with {len(episodes[:20])} episodes.")


# ==========================================
# 2. FA WNL SCRAPER (Wycombe Wanderers)
# ==========================================
WNL_URL = "https://wnl.thefa.com/overview/division-1-south-west"
WNL_RESULTS_FILE = "Wycombe_Wanderers_Results.xml"
WNL_TABLE_FILE = "WNL_Div1_South_West_Table.xml"

def parse_wnl_date(date_text):
    """Attempt to parse date strings found near FA WNL results."""
    if not date_text:
        return None
    # Strip ordinal suffixes (1st, 2nd, 3rd, 4th)
    cleaned = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_text.strip())
    for fmt in ("%d %b %Y", "%d %B %Y", "%a %d %b %Y", "%A %d %B %Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None

def scrape_wnl_wycombe():
    print(f"Launching headless browser for {WNL_URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS["User-Agent"])
        page = context.new_page()
        page.goto(WNL_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)  # Allow React/SPA tables and results widgets to finish rendering

        # Click cookie banner if present so nothing obscures DOM elements
        for btn_text in ["Accept All", "Accept", "I Accept"]:
            btn = page.locator(f"button:has-text('{btn_text}')").first
            if btn.is_visible():
                btn.click()
                page.wait_for_timeout(500)
                break

        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")

    # --- PART A: EXTRACT LATEST LEAGUE TABLE ---
    table_fg = FeedGenerator()
    table_fg.title("FA WNL Division 1 South West - League Table")
    table_fg.link(href=WNL_URL, rel="alternate")
    table_fg.description("Latest FA Women's National League Division 1 South West Standings")

    standings_html = ""
    best_table = None

    for tbl in soup.find_all("table"):
        tbl_text = tbl.get_text(" ", strip=True)
        if "Wycombe" in tbl_text and ("Pts" in tbl_text or "GD" in tbl_text or "P" in tbl_text):
            best_table = tbl
            break

    if best_table:
        rows_html = []
        for tr in best_table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            cells = [c for c in cells if c != ""]
            if not cells:
                continue
            is_header = bool(tr.find("th"))
            tag = "th" if is_header else "td"
            row_style = ' style="background-color:#e6f2ff;font-weight:bold;"' if "Wycombe" in " ".join(cells) else ""
            row_cells = "".join(f"<{tag}>{c}</{tag}>" for c in cells)
            rows_html.append(f"<tr{row_style}>{row_cells}</tr>")

        standings_html = f'<table border="1" cellpadding="6" cellspacing="0">{"".join(rows_html)}</table>'
    else:
        print("Warning: Could not locate standard <table> for standings; saving raw text fallback.")
        standings_html = "<p>Standings table structure changed on source page.</p>"

    # Hash table contents so WordPress sees a new GUID whenever points/positions update
    table_hash = hashlib.md5(standings_html.encode("utf-8")).hexdigest()[:10]
    today_str = datetime.now(timezone.utc).strftime("%d %b %Y")

    te = table_fg.add_entry()
    te.id(f"{WNL_URL}#table-{table_hash}")
    te.title(f"Division 1 South West Standings ({today_str})")
    te.link(href=WNL_URL)
    te.pubDate(datetime.now(timezone.utc))
    te.description(standings_html)

    table_fg.rss_file(WNL_TABLE_FILE, pretty=True)
    print(f"Saved '{WNL_TABLE_FILE}'.")

    # --- PART B: EXTRACT WYCOMBE WANDERERS RESULTS ---
    res_fg = FeedGenerator()
    res_fg.title("Wycombe Wanderers Women - Results (FA WNL)")
    res_fg.link(href=WNL_URL, rel="alternate")
    res_fg.description("Latest FA WNL Division 1 South West results for Wycombe Wanderers")

    results = []
    seen_matches = set()

    # Scan match containers / rows that mention Wycombe and contain a scoreline (e.g., "2 - 1" or "2-1")
    for el in soup.find_all(["tr", "li", "div", "article"]):
        text = el.get_text(" ", strip=True)
        if "Wycombe" not in text or len(text) > 220:
            continue

        # Look for a completed score pattern like "2 - 0" or "1-3" (avoiding times like "14:00")
        score_match = re.search(
            r'([A-Za-z0-9\s&\.\'-]{3,40}?)\s+(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z0-9\s&\.\'-]{3,40})',
            text
        )
        if not score_match:
            continue

        home_team = score_match.group(1).strip()
        home_goals = score_match.group(2)
        away_goals = score_match.group(3)
        away_team = score_match.group(4).strip()

        # Filter out false positives where a date or competition name got captured
        if "Wycombe" not in home_team and "Wycombe" not in away_team:
            continue
        if any(bad in home_team.lower() or bad in away_team.lower() for bad in ["division", "table", "fixtures", "results"]):
            continue

        headline = f"{home_team} {home_goals} - {away_goals} {away_team}"
        if headline in seen_matches:
            continue
        seen_matches.add(headline)

        # Look for a date string in the element or its immediate parent
        parent_text = el.parent.get_text(" ", strip=True) if el.parent else text
        date_search = re.search(r'(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})', parent_text)
        match_date = parse_wnl_date(date_search.group(1)) if date_search else None

        results.append({
            "headline": headline,
            "date_str": date_search.group(1) if date_search else "",
            "pub_date": match_date
        })

    for res in results[:20]:
        match_slug = hashlib.md5(res["headline"].encode("utf-8")).hexdigest()[:10]
        fe = res_fg.add_entry()
        fe.id(f"{WNL_URL}#result-{match_slug}")
        fe.title(res["headline"])
        fe.link(href=WNL_URL)
        if res["pub_date"]:
            fe.pubDate(res["pub_date"])
        desc = f"FA WNL Division 1 South West Result: {res['headline']}"
        if res["date_str"]:
            desc += f" ({res['date_str']})"
        fe.description(desc)

    res_fg.rss_file(WNL_RESULTS_FILE, pretty=True)
    print(f"Saved '{WNL_RESULTS_FILE}' with {len(results[:20])} Wycombe results.")


if __name__ == "__main__":
    try:
        scrape_bbc_sounds()
    except Exception as e:
        print(f"Error in BBC scraper: {e}")

    try:
        scrape_wnl_wycombe()
    except Exception as e:
        print(f"Error in FA WNL scraper: {e}")
