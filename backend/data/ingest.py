import requests
from bs4 import BeautifulSoup
import json

OUTPUT_FILE = "knowledge.json"

def scrape_page(url="https://www.occamsadvisory.com/"):
    html = requests.get(url, timeout=10).text
    soup = BeautifulSoup(html, "html.parser")
    return {
        "url": url,
        "title": soup.title.text.strip(),
        "content": " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p")),
    }


import re

def clean_text(text: str) -> str:
    if not text:
        return ""

    # Replace multiple whitespace (space, \n, \t) with single space
    text = re.sub(r"\s+", " ", text)

    return text.strip()


if __name__ == "__main__":
    print("Starting ingestion pipeline...")
    data = scrape_page()

    data["content"] = clean_text(data["content"])
    # Save to local file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


    print(f"Successfully scraped {len(data)} pages.")
    print(f"Knowledge base saved to {OUTPUT_FILE}")
