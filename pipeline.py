import subprocess
import os
import sys

def main():
    # Scrape the GitHub repo 
    print("Starting the scraping process...")
    try:
        subprocess.run([sys.executable, "scrape_repo.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during scraping: {e}")
        return
    
    # Check if repo_content.md was created
    if not os.path.exists("repo_content.md"):
        print("Scraping failed: repo_content.md not found.")
        return
    
    # Embed and store the content 
    print("Embedding and storing the repo content")
    try:
        subprocess.run([sys.executable, "embed_and_store.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during embedding and storing: {e}")
        return
    
    # Seacrh interface
    print("Database is ready. Launching search interface...")
    try:
        subprocess.run([sys.executable, "search.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during search: {e}")
        return
    
if __name__ == "__main__":
    main()