"""
Reddit Post Card Image Generator
Renders a modern, pixel-perfect dark mode Reddit post header card using Playwright HTML/CSS screenshot.
"""

import sys
import os
import json
import argparse
from typing import Dict, Any
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: transparent;
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 20px;
  }}
  .reddit-card {{
    background-color: #1a1a1b;
    border: 1px solid #343536;
    border-radius: 18px;
    width: 680px;
    padding: 24px 28px;
    color: #d7dedd;
    box-shadow: 0 12px 40px rgba(0,0,0,0.6);
  }}
  .card-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
  }}
  .icon {{
    width: 44px;
    height: 44px;
    background: linear-gradient(135deg, #ff4500, #ff8700);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 22px;
    color: white;
  }}
  .meta {{
    display: flex;
    flex-direction: column;
  }}
  .sub {{
    font-weight: 700;
    font-size: 16px;
    color: #f2f4f5;
  }}
  .author {{
    font-size: 13px;
    color: #818384;
    margin-top: 2px;
  }}
  .title {{
    font-size: 24px;
    font-weight: 700;
    line-height: 1.35;
    color: #ffffff;
    margin-bottom: 20px;
    word-break: break-word;
  }}
  .card-footer {{
    display: flex;
    gap: 12px;
  }}
  .badge {{
    background: #272729;
    border: 1px solid #343536;
    border-radius: 20px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 600;
    color: #d7dedd;
    display: flex;
    align-items: center;
    gap: 6px;
  }}
</style>
</head>
<body>
  <div class="reddit-card" id="card">
    <div class="card-header">
      <div class="icon">r/</div>
      <div class="meta">
        <div class="sub">r/{subreddit}</div>
        <div class="author">Posted by u/{author}</div>
      </div>
    </div>
    <div class="title">{title}</div>
    <div class="card-footer">
      <div class="badge">⬆️ {upvotes}</div>
      <div class="badge">💬 {num_comments} comments</div>
    </div>
  </div>
</body>
</html>
"""

def generate_reddit_card(story: Dict[str, Any], output_path: str = "reddit_card.png") -> str:
    """Render story metadata into HTML and capture a screenshot with Playwright."""
    html_content = HTML_TEMPLATE.format(
        subreddit=story.get("subreddit", "AskReddit"),
        author=story.get("author", "anonymous"),
        title=story.get("title", ""),
        upvotes=f"{story.get('upvotes', 1200):,}",
        num_comments=f"{story.get('num_comments', 340):,}"
    )

    abs_output = os.path.abspath(output_path)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 800, "height": 600}, device_scale_factor=2)
        page.set_content(html_content, wait_until="networkidle")
        
        card_element = page.query_selector("#card")
        if card_element:
            card_element.screenshot(path=abs_output, omit_background=True)
        else:
            page.screenshot(path=abs_output)
            
        browser.close()

    print(f"✅ Reddit card screenshot saved to {abs_output}")
    return abs_output

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Reddit post card PNG screenshot")
    parser.add_argument("--json", type=str, default="story.json", help="Input story JSON file")
    parser.add_argument("--out", type=str, default="reddit_card.png", help="Output PNG path")
    args = parser.parse_args()

    if os.path.exists(args.json):
        with open(args.json, "r", encoding="utf-8") as f:
            story_data = json.load(f)
    else:
        story_data = {
            "subreddit": "AskReddit",
            "author": "mystery_user",
            "title": "What is the most terrifying thing that ever happened to you in the woods?",
            "upvotes": 15400,
            "num_comments": 920
        }

    generate_reddit_card(story_data, output_path=args.out)
