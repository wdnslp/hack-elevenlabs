"""
Reddit Story Scraper & Parser
Supports:
1. CDP Browser Fetching (via port 9222 with Turbo VPN)
2. Direct HTTP JSON endpoints
3. Sample offline Reddit stories
"""

import sys
import re
import json
import urllib.request
import urllib.parse
import argparse
from typing import Optional, List, Dict, Any

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DEFAULT_SUBREDDITS = ["AskReddit", "AmItheAsshole", "tifu", "stories", "confession", "TwoSentenceHorror"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

SAMPLE_STORIES = [
    {
        "id": "sample_01",
        "subreddit": "AskReddit",
        "author": "story_teller_99",
        "title": "What is the most unsettling secret you discovered by accident?",
        "body": "A few years ago, while cleaning out my grandfather's old attic, I stumbled across a small wooden box locked with a rusty padlock. When I finally got it open, I found a series of hand-drawn maps of our town from the 1950s, with several red X marks over locations that don't exist on modern maps.\n\nCuriosity got the better of me, so I decided to visit one of the marked locations on the edge of the local woods. Standing there, I realized it wasn't just an empty field — buried beneath layers of overgrown moss was a heavy metal cellar door chained shut from the outside. I couldn't open it, but when I leaned closer, I could hear a strange low mechanical humming coming from deep underground.",
        "full_text": "What is the most unsettling secret you discovered by accident? A few years ago, while cleaning out my grandfather's old attic, I stumbled across a small wooden box locked with a rusty padlock. When I finally got it open, I found a series of hand-drawn maps of our town from the 1950s, with several red X marks over locations that don't exist on modern maps. Curiosity got the better of me, so I decided to visit one of the marked locations on the edge of the local woods. Standing there, I realized it wasn't just an empty field — buried beneath layers of overgrown moss was a heavy metal cellar door chained shut from the outside. I couldn't open it, but when I leaned closer, I could hear a strange low mechanical humming coming from deep underground.",
        "upvotes": 14200,
        "num_comments": 890,
        "word_count": 135
    },
    {
        "id": "sample_02",
        "subreddit": "AmItheAsshole",
        "author": "curious_mind_42",
        "title": "AITA for refusing to give my brother my heirloom watch after he lost his own?",
        "body": "My grandfather passed down a vintage 1970s watch to me when I graduated college. It has immense sentimental value to me because he wore it every single day for over forty years before passing it down. My brother recently lost his own expensive watch during a drunken trip with friends and is now demanding that I give him mine since I don't wear it every day.\n\nI flatly refused, explaining that it is a family heirloom with personal meaning. Now my brother, along with my parents, are calling me selfish and saying family should share items during tough times. AITA?",
        "full_text": "AITA for refusing to give my brother my heirloom watch after he lost his own? My grandfather passed down a vintage 1970s watch to me when I graduated college. It has immense sentimental value to me because he wore it every single day for over forty years before passing it down. My brother recently lost his own expensive watch during a drunken trip with friends and is now demanding that I give him mine since I don't wear it every day. I flatly refused, explaining that it is a family heirloom with personal meaning. Now my brother, along with my parents, are calling me selfish and saying family should share items during tough times. AITA?",
        "upvotes": 9800,
        "num_comments": 1240,
        "word_count": 125
    }
]

def clean_reddit_text(text: str) -> str:
    """Clean markdown artifacts, edits, and URLs from Reddit post body without truncating main text."""
    if not text:
        return ""
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    text = re.sub(r'[\*#_~`]', '', text)
    # Remove single line edits/updates without truncating the rest of the story
    text = re.sub(r'^\s*(edit|update|tldr|tl;dr):.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def fetch_via_cdp(subreddit: str = "AskReddit", limit: int = 10) -> Optional[Dict[str, Any]]:
    """Try fetching JSON via open Chrome CDP session if port 9222 is active."""
    url = f"https://www.reddit.com/r/{subreddit}/top.json?t=day&limit={limit}"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            text = page.inner_text("body")
            page.close()
            return json.loads(text)
    except Exception:
        return None

def fetch_top_stories(
    subreddit: str = "stories",
    time_filter: str = "day",
    limit: int = 20,
    min_words: int = 120,
    max_words: int = 1500
) -> List[Dict[str, Any]]:
    """Fetch stories using PullPush live API mirror, direct HTTP, CDP fallback, or sample stories."""
    valid_stories = []

    # Priority 1: PullPush Live Reddit Mirror API
    pullpush_url = f"https://api.pullpush.io/reddit/submission/search/?subreddit={subreddit}&size={limit}"
    try:
        req = urllib.request.Request(pullpush_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw_json = json.loads(resp.read().decode('utf-8'))
            items = raw_json.get("data", [])
            for post_data in items:
                title = post_data.get("title", "").strip()
                body = clean_reddit_text(post_data.get("selftext", ""))
                upvotes = post_data.get("score", post_data.get("ups", 0))
                num_comments = post_data.get("num_comments", 0)
                author = post_data.get("author", "anonymous")
                post_id = post_data.get("id", "")
                
                full_text = f"{title}. {body}".strip() if body else title
                words = len(full_text.split())
                
                if words >= min_words and words <= max_words:
                    valid_stories.append({
                        "id": post_id or f"post_{len(valid_stories)+1}",
                        "subreddit": subreddit,
                        "author": author,
                        "title": title,
                        "body": body,
                        "full_text": full_text,
                        "upvotes": upvotes,
                        "num_comments": num_comments,
                        "word_count": words
                    })
            if valid_stories:
                print(f"🔥 Successfully scraped {len(valid_stories)} live Reddit stories from r/{subreddit} via PullPush!")
                return valid_stories
    except Exception as e:
        print(f"⚠️ PullPush live API notice: {e}")

    # Priority 2: Direct Reddit HTTP JSON Endpoints
    urls = [
        f"https://www.reddit.com/r/{subreddit}/top.json?t={time_filter}&limit={limit}",
        f"https://old.reddit.com/r/{subreddit}/top.json?t={time_filter}&limit={limit}"
    ]
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9"
    }

    data = None
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data and "data" in data:
                    break
        except Exception:
            continue

    if not data:
        data = fetch_via_cdp(subreddit=subreddit, limit=limit)

    if data and "data" in data:
        try:
            posts = data.get("data", {}).get("children", [])
            for p in posts:
                post_data = p.get("data", {})
                title = post_data.get("title", "").strip()
                body = clean_reddit_text(post_data.get("selftext", ""))
                is_stickied = post_data.get("stickied", False)
                is_over18 = post_data.get("over_18", False)
                upvotes = post_data.get("ups", 0)
                num_comments = post_data.get("num_comments", 0)
                author = post_data.get("author", "anonymous")
                post_id = post_data.get("id", "")
                permalink = post_data.get("permalink", "")
                
                if is_stickied or is_over18:
                    continue
                
                full_text = f"{title}. {body}".strip() if body else title
                word_count = len(full_text.split())
                
                if min_words <= word_count <= max_words:
                    valid_stories.append({
                        "id": post_id,
                        "subreddit": subreddit,
                        "author": author,
                        "title": title,
                        "body": body,
                        "full_text": full_text,
                        "upvotes": upvotes,
                        "num_comments": num_comments,
                        "word_count": word_count,
                        "url": f"https://www.reddit.com{permalink}"
                    })
        except Exception as e:
            print(f"❌ Error parsing stories: {e}")
    
    if not valid_stories:
        print(f"ℹ️ Network request blocked. Using sample fallback stories for r/{subreddit}...")
        valid_stories = SAMPLE_STORIES

    return valid_stories

def get_single_story(subreddit: str = "AskReddit", story_idx: int = 0) -> Optional[Dict[str, Any]]:
    """Get a single story by index from top stories."""
    stories = fetch_top_stories(subreddit=subreddit, limit=30)
    if stories and 0 <= story_idx < len(stories):
        return stories[story_idx]
    return stories[0] if stories else None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch top stories from Reddit")
    parser.add_argument("--subreddit", type=str, default="AskReddit", help="Subreddit name")
    parser.add_argument("--limit", type=int, default=5, help="Number of stories to fetch")
    parser.add_argument("--out", type=str, default="story.json", help="Output JSON file")
    args = parser.parse_args()

    print(f"🔎 Fetching top stories from r/{args.subreddit}...")
    stories = fetch_top_stories(subreddit=args.subreddit, limit=args.limit * 3)
    
    if stories:
        selected = stories[:args.limit]
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(selected[0], f, ensure_ascii=False, indent=2)
        print(f"✅ Saved story to {args.out}")
        for idx, s in enumerate(selected):
            print(f" [{idx+1}] [{s['upvotes']} 👍] r/{s['subreddit']} - {s['title'][:70]}... ({s['word_count']} words)")
