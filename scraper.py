import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from urllib.parse import urljoin

# Configure your target websites here
FEEDS = [
    {
        "filename": "example-news.xml",
        "title": "Example Site News",
        "url": "https://example.com/news",
        "item_selector": "article.post",       # CSS selector for each article container
        "title_selector": "h2.entry-title a",  # CSS selector for the headline inside the container
        "link_selector": "h2.entry-title a",   # CSS selector for the link (usually same as title)
        "summary_selector": "div.excerpt p"    # Optional: CSS selector for description/summary
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def build_feed(config):
    print(f"Scraping {config['url']}...")
    response = requests.get(config["url"], headers=HEADERS, timeout=15)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    fg = FeedGenerator()
    fg.title(config["title"])
    fg.link(href=config["url"], rel="alternate")
    fg.description(f"Custom RSS feed for {config['title']}")
    
    items = soup.select(config["item_selector"])
    
    for item in items[:20]:  # Limit to top 20 items
        title_el = item.select_one(config["title_selector"])
        link_el = item.select_one(config["link_selector"])
        
        if not title_el or not link_el:
            continue
            
        title = title_el.get_text(strip=True)
        # Convert relative URLs (e.g., "/blog/post-1") into full URLs
        link = urljoin(config["url"], link_el.get("href", ""))
        
        summary = ""
        if config.get("summary_selector"):
            summary_el = item.select_one(config["summary_selector"])
            if summary_el:
                summary = summary_el.get_text(strip=True)
        
        fe = fg.add_entry()
        fe.id(link)
        fe.title(title)
        fe.link(href=link)
        if summary:
            fe.description(summary)
            
    fg.rss_file(config["filename"], pretty=True)
    print(f"Saved {config['filename']} with {len(items[:20])} items.")

if __name__ == "__main__":
    for feed_config in FEEDS:
        try:
            build_feed(feed_config)
        except Exception as e:
            print(f"Error processing {config['title']}: {e}")
