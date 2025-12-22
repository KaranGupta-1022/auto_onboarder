import asyncio
from crawl4ai import *

async def main():
    url = input("Enter the Github URL to scrape:")
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)

        with open("pr_content.md", "w") as f:
            f.write(result.markdown)
        print("Scraped content saved to pr_content.md")
        print("\nPreview of scraped content:\n")
        print(result.markdown[:500])

if __name__ == "__main__":
    asyncio.run(main())