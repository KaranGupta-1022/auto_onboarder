import asyncio
import requests
from crawl4ai import *

async def main():
    url = input("Enter the Github repo URL to scrape:")
    blocks = url.strip('/').split('/')
    owner, repo = blocks[-2], blocks[-1]

    # Fetch repository contents via GitHub API
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
    print(f"Fetching contents from {api_url}...")

    # Make the API request
    response = requests.get(api_url)
    if response.status_code != 200:
        print(f"Failed to fetch repository contents: {response.status_code}")
        return

    # Parse the JSON response
    files = response.json()
    important_files = []

    # Filter for important files
    for file in files:
        if file['type'] == 'file':
            name = file['name']
            # Include README, docs, code files, and config files
            if name.endswith(('.md', '.py', '.js', '.ts', '.json', '.yaml', '. yml', '.txt')):
                important_files.append(file['download_url'])

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
