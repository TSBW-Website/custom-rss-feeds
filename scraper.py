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

def extract_image_url(item):
    img_el = item.select_one("img")
    if not img_el:
        return ""
    
    # BBC uses data-src or src, and sometimes puts a {recipe} placeholder in the URL
    img_url = img_el.get("data-src") or img_el.get("src") or ""
    if "{recipe}" in img_url:
        img_url = img_url.replace("{recipe}", "640x360")
    
    # Ignore tiny 1x1 tracking/placeholder pixels
    if img_url.startswith("data:image"):
        return ""
        
    return img_url

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

        seen_ids.add(pid)
        episodes.append({
            "id": pid,
            "title": title,
            "link": f"https://www.bbc.co.uk/sounds/play/{pid}",
            "synopsis": synopsis,
            "image": image_url
        })

    for ep in episodes[:20]:
        fe = fg.add_entry()
        fe.id(ep["link"])
        fe.title(ep["title"])
        fe.link(href=ep["link"])

        # Attach image as a standard RSS media enclosure
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
