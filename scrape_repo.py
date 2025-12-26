import asyncio
import requests
from crawl4ai import *

async def main():
    url = input("Enter the Github repo URL to scrape: ").rstrip('/').split('/tree')[0]
    blocks = url.strip('/').split('/')
    owner, repo = blocks[-2], blocks[-1]
    
    important_files = [] # Now stores (download_url, full_path)
    async def fetch_all_files(path=""):
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        try:
            response = requests.get(api_url)
            if response.status_code != 200: return 
            
            items = response.json()
            for item in items:
                if item['type'] == 'file':
                    name = item['name']
                    if name.endswith(('.md', '.py', '.js', '.ts', '.json', '.yaml', '.yml', '.txt', '.jsx', '.tsx')):
                        # Store the full path so we know where the file lives in the folder structure
                        important_files.append((item['download_url'], item['path']))
                elif item['type'] == 'dir':
                    await fetch_all_files(path=item['path'])
        except Exception as e:
            print(f"Error: {e}")
    
    print("Fetching file list...")
    await fetch_all_files()
    
    all_content = f"# Repository: {owner}/{repo}\n\n"
    async with AsyncWebCrawler() as crawler:
        for i, (file_url, full_path) in enumerate(important_files, 1):
            print(f"Scraping {i}/{len(important_files)}: {full_path}...")
            try:
                result = await crawler.arun(url=file_url)
                # Optimization: We now use the FULL PATH as the header for the splitter to find
                all_content += f"\n## File Path: {full_path}\n"
                all_content += result.markdown + "\n\n"
            except Exception as e:
                print(f"Error scraping {full_path}: {e}")
    
    with open("repo_content.md", "w", encoding="utf-8") as f:
        f.write(all_content)
    print(f"✅ Saved to repo_content.md")

if __name__ == "__main__":
    asyncio.run(main())