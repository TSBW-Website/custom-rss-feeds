import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
import re

URL = "https://www.bbc.co.uk/sounds/brand/p0kfv035"
PROGRAMMES_URL = "https://www.bbc.co.uk/programmes/p0kfv035/episodes/player"
FILENAME = "BBC Sport - Stockport County.xml"
FEED_TITLE = "BBC Sport - Stockport County"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def extract_image_url(item):
    img_el = item.select_one("img")
    if not img_el:
        return ""
    
    img_url = img_el.get("data-src") or img_el.get("src") or ""
    if "{recipe}" in img_url:
        img_url = img_url.replace("{recipe}", "640x360")
    
    if img_url.startswith("data:image"):
        return ""
        
    return img_url

def extract_pub_date(item):
    # 1. Check for a standard HTML <time datetime="..."> attribute
    time_el = item.select_one("time[datetime]")
    if time_el and time_el.get("datetime"):
        dt_str = time_el["datetime"].strip()
        try:
            # Handle trailing 'Z' for Python ISO parsing
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass

    # 2. Fallback: Parse visible BBC broadcast date text (e.g., "14 Nov 2026")
    date_el = item.select_one(".broadcast-event__time, .programme__service, .date, time")
    if date_el:
        text = date_el.get_text(" ", strip=True)
        match = re.search(r'(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})', text)
        if match:
            for fmt in ("%d %b %Y", "%d %B %Y"):
                try:
                    return datetime.strptime(match.group(1), fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

    return None

def scrape_bbc_sounds():
    print(f"Fetching {PROGRAMMES_URL}...")
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
        pub_date = extract_pub_date(item)

        seen_ids.add(pid)
        episodes.append({
            "id": pid,
            "title": title,
            "link": f"https://www.bbc.co.uk/sounds/play/{pid}",
            "synopsis": synopsis,
            "image": image_url,
            "pub_date": pub_date
        })

    for ep in episodes[:20]:
        fe = fg.add_entry()
        fe.id(ep["link"])
        fe.title(ep["title"])
        fe.link(href=ep["link"])

        if ep["pub_date"]:
            fe.pubDate(ep["pub_date"])

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
