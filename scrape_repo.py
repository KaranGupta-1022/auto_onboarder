import asyncio
import requests
from crawl4ai import *

async def main():
    url = input("Enter the Github repo URL to scrape:").rstrip('/').split('/tree')[0]
    blocks = url.strip('/').split('/')
    owner, repo = blocks[-2], blocks[-1]
    
    # Recursively fetch files from subdirectories
    important_files = []
    async def fetch_all_files(path=""):
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        try:
            response = requests.get(api_url)
            if response.status_code != 200:
                print(f"Failed to fecth contents from {api_url}: {response.status_code}")
                return 
            
            items = response.json()
            for item in items:
                if item['type'] == 'file':
                    # scrape only important file types
                    name = item['name']
                    if name.endswith(('.md', '.py', '.js', '.ts', '.json', '.yaml', '.yml', '.txt', '.jsx', '.tsx')):
                        important_files.append(item['download_url'])
                # Recursively fetch from subdirectories
                elif item['type'] == 'dir':
                        await fetch_all_files(path=item['path'])
        except Exception as e:
            print(f"Error fetching contents from {api_url}: {e}")
    
    print("Fetching important files...")
    await fetch_all_files()
    print(f"Found {len(important_files)} important files")
    
    # Scrape each file
    all_content = f"# Repository: {owner}/{repo}\n\n"
    async with AsyncWebCrawler() as crawler:
        for i, file_url in enumerate(important_files, 1):
            print(f"Scraping {i}/{len(important_files)}: {file_url.split('/') [-1]}...")
            try:
                result = await crawler.arun(url=file_url)
                all_content += f"\n## File: {file_url.split('/')[-1]}\n"
                all_content += result.markdown + "\n\n"
            except Exception as e:
                print(f"Error scraping {file_url}: {e}")
    
    # Save all content
    with open("repo_content.md", "w", encoding="utf-8") as f:
        f.write(all_content)
    print(f"Repository content saved to repo_content.md")
    print(f"Total content: {len(all_content)} characters")

if __name__ == "__main__":
    asyncio.run(main())
