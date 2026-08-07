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

DEFAULT_SUBREDDITS = [
    "TrueOffMyChest",
    "ProRevenge",
    "nosleep",
    "entitledparents",
    "AmItheAsshole",
    "pettyrevenge",
    "relationship_advice",
    "TalesFromTechSupport",
    "tifu",
    "confession"
]

CATEGORIZED_SUBREDDITS = {
    "drama": ["TrueOffMyChest", "AmItheAsshole", "relationship_advice", "confession"],
    "revenge": ["ProRevenge", "pettyrevenge", "nuclearrevenge"],
    "horror": ["nosleep", "scarystories", "Glitch_in_the_Matrix"],
    "entitled": ["entitledparents", "entitledpeople"],
    "workplace": ["TalesFromTechSupport", "TalesFromYourServer", "TalesFromRetail"],
    "longform": ["HobbyDrama", "HFY", "ProRevenge"]
}
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

SAMPLE_STORIES = [
    {
        "id": "ru_story_01",
        "subreddit": "ru_Reddit",
        "author": "alex_storyteller",
        "title": "Какая самая странная или пугающая находка была в вашем доме?",
        "body": "Переехал в старый хрущевский дом, который достался от прабабушки. Когда делал ремонт в прихожей и снимал старые деревянные панели со стены, обнаружил за ними небольшой тайник. Там лежала металлическая коробка 1960-х годов. Внутри были не деньги и не драгоценности, а несколько старых черно-белых фотографий нашей улицы и тетрадь. На фотографиях на крыше нашего дома стоял человек в странном плаще и смотрел строго в кадр. В тетради были аккуратно записаны даты и точное время — каждые 3 дня на протяжении 15 лет. Самое жуткое: последняя запись была сделана вчерашней датой, хотя в квартиру до меня никто не заходил уже лет пять.",
        "full_text": "Какая самая странная или пугающая находка была в вашем доме? Переехал в старый хрущевский дом, который достался от прабабушки. Когда делал ремонт в прихожей и снимал старые деревянные панели со стены, обнаружил за ними небольшой тайник. Там лежала металлическая коробка 1960-х годов. Внутри были не деньги и не драгоценности, а несколько старых черно-белых фотографий нашей улицы и тетрадь. На фотографиях на крыше нашего дома стоял человек в странном плаще и смотрел строго в кадр. В тетради были аккуратно записаны даты и точное время — каждые 3 дня на протяжении 15 лет. Самое жуткое: последняя запись была сделана вчерашней датой, хотя в квартиру до меня никто не заходил уже лет пять.",
        "upvotes": 18400,
        "num_comments": 1120,
        "word_count": 120
    },
    {
        "id": "pikabu_story_02",
        "subreddit": "pikabu",
        "author": "pikabu_hero",
        "title": "Как я отучил шумных соседей устраивать вечеринки по ночам",
        "body": "Сверху заселилась компания студентов, которая каждую пятницу и субботу устраивала дискотеки до 4 утра. Разговоры и вызовы участкового не помогали — они просто открывали дверь, извинялись и через полчаса снова включали сабвуфер. Тогда я решил действовать технически. Купил виброколонку, прижал её к потолку в спальне прямо под их полом и настроил таймер на 6:00 утра — как раз когда они только засыпали. На колонку я поставил аудиозапись звука работающей болгарки, дрели и детского плача. Через 3 дня таких утренних подьемов соседи сами пришли ко мне с просьбой договориться и с тех пор после 23:00 у них полная тишина.",
        "full_text": "Как я отучил шумных соседей устраивать вечеринки по ночам. Сверху заселилась компания студентов, которая каждую пятницу и субботу устраивала дискотеки до 4 утра. Разговоры и вызовы участкового не помогали — они просто открывали дверь, извинялись и через полчаса снова включали сабвуфер. Тогда я решил действовать технически. Купил виброколонку, прижал её к потолку в спальне прямо под их полом и настроил таймер на 6:00 утра — как раз когда они только засыпали. На колонку я поставил аудиозапись звука работающей болгарки, дрели и детского плача. Через 3 дня таких утренних подьемов соседи сами пришли ко мне с просьбой договориться и с тех пор после 23:00 у них полная тишина.",
        "upvotes": 24500,
        "num_comments": 1890,
        "word_count": 130
    },
    {
        "id": "askru_story_03",
        "subreddit": "askru",
        "author": "dmitry_v",
        "title": "Какое самое неожиданное совпадение меняло вашу жизнь?",
        "body": "Пять лет назад я опоздал на международный рейс из-за того, что у меня в метро порвался рюкзак и все вещи рассыпались по перрону. Я жутко расстроился, проклинал весь мир и вынужден был покупать новый билет на следующий день. В аэропорту, пока ждал переоформления, разговорился в очереди с девушкой, которая оказалась из моего же города и летела тем же направлением. Мы проговорили 4 часа подряд, обменялись контактами. Прошло пять лет — мы женаты, и у нас растет дочь. Тот порвавшийся рюкзак оказался лучшим событием в моей жизни.",
        "full_text": "Какое самое неожиданное совпадение меняло вашу жизнь? Пять лет назад я опоздал на международный рейс из-за того, что у меня в метро порвался рюкзак и все вещи рассыпались по перрону. Я жутко расстроился, проклинал весь мир и вынужден был покупать новый билет на следующий день. В аэропорту, пока ждал переоформления, разговорился в очереди с девушкой, которая оказалась из моего же города и летела тем же направлением. Мы проговорили 4 часа подряд, обменялись контактами. Прошло пять лет — мы женаты, и у нас растет дочь. Тот порвавшийся рюкзак оказался лучшим событием в моей жизни.",
        "upvotes": 16700,
        "num_comments": 850,
        "word_count": 115
    },
    {
        "id": "trueoffmychest_story_04",
        "subreddit": "TrueOffMyChest",
        "author": "secret_keeper_88",
        "title": "I accidentally discovered a hidden room behind the pantry in my new house",
        "body": "When my wife and I bought our 1920s craftsman home last month, the inspector noted that the kitchen pantry wall seemed hollow. Last weekend I decided to knock down the old wooden shelving to rebuild it. Behind the rear wall, I found a small latch that opened a secret door leading down a spiral staircase into a subterranean room. Inside was a fully functioning vintage ham radio setup, complete with logbooks from 1962 detailing encrypted numbers stations and coordinates across Europe. The last log entry entry was dated just three weeks before we purchased the home.",
        "full_text": "I accidentally discovered a hidden room behind the pantry in my new house. When my wife and I bought our 1920s craftsman home last month, the inspector noted that the kitchen pantry wall seemed hollow. Last weekend I decided to knock down the old wooden shelving to rebuild it. Behind the rear wall, I found a small latch that opened a secret door leading down a spiral staircase into a subterranean room. Inside was a fully functioning vintage ham radio setup, complete with logbooks from 1962 detailing encrypted numbers stations and coordinates across Europe. The last log entry entry was dated just three weeks before we purchased the home.",
        "upvotes": 31200,
        "num_comments": 2100,
        "word_count": 140
    },
    {
        "id": "amitheasshole_story_05",
        "subreddit": "AmItheAsshole",
        "author": "fair_play_guy",
        "title": "AITA for exposing my coworker who took credit for my entire 6-month project?",
        "body": "For six months I worked extra hours developing an automated workflow script for our company that saved over 200 hours of manual data entry per week. During the big quarterly presentation to upper management, a senior coworker presented my entire deck and took full credit, claiming he built it independently over the weekend. Instead of arguing during the meeting, I waited until he demonstrated the tool live. I remotely revoked his API access token from my laptop. When the demo crashed instantly on screen, I raised my hand and politely offered to log in with master developer credentials to fix it. My boss realized what happened immediately.",
        "full_text": "AITA for exposing my coworker who took credit for my entire 6-month project? For six months I worked extra hours developing an automated workflow script for our company that saved over 200 hours of manual data entry per week. During the big quarterly presentation to upper management, a senior coworker presented my entire deck and took full credit, claiming he built it independently over the weekend. Instead of arguing during the meeting, I waited until he demonstrated the tool live. I remotely revoked his API access token from my laptop. When the demo crashed instantly on screen, I raised my hand and politely offered to log in with master developer credentials to fix it. My boss realized what happened immediately.",
        "upvotes": 45800,
        "num_comments": 3400,
        "word_count": 145
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
    time_filter: str = "all",
    limit: int = 100,
    min_words: int = 120,
    max_words: int = 1500
) -> List[Dict[str, Any]]:
    """Fetch top all-time, top year, top month and fresh stories using PullPush API and Reddit endpoints."""
    valid_stories = []
    seen_ids = set()

    # Priority 1: PullPush Live Reddit Mirror API (Top score & top comments & recent)
    pullpush_endpoints = [
        f"https://api.pullpush.io/reddit/submission/search/?subreddit={subreddit}&sort=desc&sort_type=score&size={min(limit, 100)}",
        f"https://api.pullpush.io/reddit/submission/search/?subreddit={subreddit}&sort=desc&sort_type=num_comments&size={min(limit, 100)}",
        f"https://api.pullpush.io/reddit/submission/search/?subreddit={subreddit}&size={min(limit, 100)}"
    ]

    for p_url in pullpush_endpoints:
        try:
            req = urllib.request.Request(p_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw_json = json.loads(resp.read().decode('utf-8'))
                items = raw_json.get("data", [])
                for post_data in items:
                    post_id = post_data.get("id", "")
                    if not post_id or post_id in seen_ids:
                        continue

                    title = post_data.get("title", "").strip()
                    body = clean_reddit_text(post_data.get("selftext", ""))
                    upvotes = post_data.get("score", post_data.get("ups", 0))
                    num_comments = post_data.get("num_comments", 0)
                    author = post_data.get("author", "anonymous")

                    full_text = f"{title}. {body}".strip() if body else title
                    words = len(full_text.split())

                    if min_words <= words <= max_words:
                        seen_ids.add(post_id)
                        valid_stories.append({
                            "id": post_id,
                            "subreddit": subreddit,
                            "author": author,
                            "title": title,
                            "body": body,
                            "full_text": full_text,
                            "upvotes": upvotes,
                            "num_comments": num_comments,
                            "word_count": words
                        })
        except Exception as e:
            pass

    if valid_stories:
        valid_stories.sort(key=lambda x: x.get("upvotes", 0), reverse=True)
        print(f"🔥 Scraped {len(valid_stories)} top all-time & popular Reddit stories from r/{subreddit} via PullPush!")
        return valid_stories[:limit]


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
        # Priority 3: Reddit Atom RSS Feeds
        rss_urls = [
            f"https://www.reddit.com/r/{subreddit}/top.rss?t=all",
            f"https://www.reddit.com/r/{subreddit}/hot.rss"
        ]
        import xml.etree.ElementTree as ET
        import html

        for r_url in rss_urls:
            try:
                req = urllib.request.Request(r_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
                    "Accept": "application/atom+xml,application/xml,text/xml"
                })
                with urllib.request.urlopen(req, timeout=6) as resp:
                    xml_bytes = resp.read()
                    root = ET.fromstring(xml_bytes)
                    for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                        title_el = entry.find('{http://www.w3.org/2005/Atom}title')
                        id_el = entry.find('{http://www.w3.org/2005/Atom}id')
                        content_el = entry.find('{http://www.w3.org/2005/Atom}content')

                        title = title_el.text.strip() if title_el is not None and title_el.text else ""
                        post_id = id_el.text.split('/')[-1] if id_el is not None and id_el.text else f"rss_{hash(title)}"
                        
                        body_raw = content_el.text if content_el is not None and content_el.text else ""
                        body_clean = re.sub(r'<[^>]+>', ' ', body_raw)
                        body_clean = clean_reddit_text(html.unescape(body_clean))

                        full_text = f"{title}. {body_clean}".strip() if body_clean else title
                        words = len(full_text.split())

                        if min_words <= words <= max_words and post_id not in seen_ids:
                            seen_ids.add(post_id)
                            valid_stories.append({
                                "id": post_id,
                                "subreddit": subreddit,
                                "author": "reddit_user",
                                "title": title,
                                "body": body_clean,
                                "full_text": full_text,
                                "upvotes": 5000,
                                "num_comments": 400,
                                "word_count": words
                            })
            except Exception:
                pass

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
