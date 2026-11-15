import json
import re
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

URL = "https://www.bbc.co.uk/sounds/brand/p0kfv035"
PROGRAMMES_URL = "https://www.bbc.co.uk/programmes/p0kfv035/episodes/player"
FILENAME = "BBC Sport - Stockport County.xml"
FEED_TITLE = "BBC Sport - Stockport County"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def load_cached_dates(filename):
    """Read previously scraped pubDates from the existing XML file so we don't re-fetch old episodes."""
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
    
    # Check srcset first for the highest resolution variant, otherwise fall back to data-src/src
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

    # Upgrade BBC ichef thumbnail dimensions (e.g., /320x180/ or /{recipe}/) to 1280x720 HD
    img_url = img_url.replace("{recipe}", "1280x720")
    img_url = re.sub(r'/ic/\d+x\d+/', '/ic/1280x720/', img_url)

    return img_url

def fetch_episode_pub_date(pid):
    """Fetch the exact uploadDate / datePublished from the individual BBC programme page."""
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
    print(f"Fetching {PROGRAMMES_URL}...")
    cached_dates = load_cached_dates(FILENAME)

    response = requests.get(PROGRAMMES_URL, headers=HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    fg = FeedGenerator()
    fg.title(FEED_TITLE)
    fg.link(href=URL, rel="alternate")
    fg.description(f"Latest episodes from {FEED_TITLE}")

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

    fg.rss_file(FILENAME, pretty=True)
    print(f"Saved '{FILENAME}' with {len(episodes[:20])} episodes.")

if __name__ == "__main__":
    try:
        scrape_bbc_sounds()
    except Exception as e:
        print(f"Error: {e}")
