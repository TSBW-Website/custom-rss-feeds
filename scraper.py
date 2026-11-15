import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from urllib.parse import urljoin

FEEDS = [
    {
        "filename": "stockport-county.xml",
        "title": "Stockport County News - Sky Sports",
        "url": "https://www.skysports.com/stockport-county"
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def scrape_skysports(config):
    print(f"Fetching {config['url']}...")
    response = requests.get(config["url"], headers=HEADERS, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    fg = FeedGenerator()
    fg.title(config["title"])
    fg.link(href=config["url"], rel="alternate")
    fg.description(f"Latest news and videos from {config['title']}")

    seen_urls = set()
    articles = []

    # Target Sky Sports news/video article links inside content tiles
    for link_el in soup.select("a[href*='/football/news/'], a[href*='/football/video/']"):
        href = urljoin(config["url"], link_el.get("href", ""))
        title = link_el.get_text(" ", strip=True)

        # Skip empty links, image-only links, or duplicate links on the same card
        if not title or len(title) < 15 or href in seen_urls:
            continue

        seen_urls.add(href)
        articles.append((title, href))

    for title, link in articles[:20]:
        fe = fg.add_entry()
        fe.id(link)
        fe.title(title)
        fe.link(href=link)

    fg.rss_file(config["filename"], pretty=True)
    print(f"Saved {config['filename']} with {len(articles[:20])} articles.")

if __name__ == "__main__":
    for feed in FEEDS:
        try:
            scrape_skysports(feed)
        except Exception as e:
            print(f"Error processing {feed['title']}: {e}")
