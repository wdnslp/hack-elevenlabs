"""
Batch Reddit TikTok Video Generator (Infinite Loop Workflow)

Runs a continuous, infinite loop over Reddit stories until stopped with Ctrl+C:
1. Continuously fetches top/trending stories from Reddit.
2. Serves story to Tampermonkey userscript via Local API Server (http://127.0.0.1:5000/api/story).
3. Automatically receives audio chunks directly from browser via API (zero manual file renaming!).
4. Isolates audio chunks per story_id, merges audio, generates subtitles, and renders 1080x1920 video.
5. Advances to the next story automatically!
"""

import sys
import os
import re
import json
import time
import argparse
from typing import List, Dict, Any, Set

from reddit_scraper import fetch_top_stories
from reddit_card_generator import generate_reddit_card
from subtitle_generator import generate_ass_subtitles
from video_assembler import assemble_tiktok_video
from narration_pipeline import format_text_with_elevenlabs_tags, merge_mp3_chunks
from story_api_server import start_story_api_server, set_current_story, wait_for_story_chunks

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def split_text_into_chunks(text: str, max_len: int = 920) -> List[str]:
    """Sentence-greedy chunking matching Tampermonkey userscript logic."""
    sentences = re.split(r'(?<=[.!?…])\s+', text)
    chunks = []
    curr = ''

    for s in sentences:
        s = s.strip()
        if not s:
            continue
        sep = '\n\n' if (curr and ('Часть' in s or s.startswith('['))) else ' '
        test = curr + sep + s if curr else s
        if len(test) <= max_len:
            curr = test
        else:
            if curr:
                chunks.append(curr.strip())
            curr = s

    if curr:
        chunks.append(curr.strip())

    return chunks

def run_infinite_batch_pipeline(
    subreddit: str = "AskReddit",
    count: int = 0,  # 0 means infinite until Ctrl+C
    bg_dir: str = "backgrounds",
    output_dir: str = "output_batch_videos"
):
    is_infinite = (count <= 0)
    target_str = "∞ INFINITE MODE (Press Ctrl+C to stop)" if is_infinite else f"{count} videos"

    print("\n==================================================================")
    print(f"🎬 BATCH REDDIT TIKTOK GENERATOR LOOP (Subreddit: r/{subreddit}, Target: {target_str})")
    print("==================================================================\n")

    # Step 1: Start local API server
    start_story_api_server(host="127.0.0.1", port=5000)

    # Setup output directories
    abs_out_dir = os.path.abspath(output_dir)
    os.makedirs(os.path.join(abs_out_dir, "cards"), exist_ok=True)
    os.makedirs(os.path.join(abs_out_dir, "audio"), exist_ok=True)
    os.makedirs(os.path.join(abs_out_dir, "subtitles"), exist_ok=True)
    os.makedirs(os.path.join(abs_out_dir, "videos"), exist_ok=True)

    completed_videos: List[str] = []
    processed_story_ids: Set[str] = set()
    story_queue: List[Dict[str, Any]] = []

    story_counter = 0

    try:
        while True:
            # Check if target count reached
            if not is_infinite and story_counter >= count:
                break

            # Replenish queue if empty
            if not story_queue:
                print(f"📖 Fetching fresh stories from r/{subreddit}...")
                fetched = fetch_top_stories(subreddit=subreddit, limit=25)
                for f_story in fetched:
                    s_id = f_story.get("id")
                    if s_id and s_id not in processed_story_ids:
                        story_queue.append(f_story)

                if not story_queue:
                    print("⚠️ All available stories processed. Resetting history log for infinite loop...")
                    processed_story_ids.clear()
                    for f_story in fetched:
                        story_queue.append(f_story)

            # Pick next story from queue
            story = story_queue.pop(0)
            raw_id = story.get("id", f"sample_{story_counter+1}")
            if raw_id in processed_story_ids:
                continue

            processed_story_ids.add(raw_id)
            story_counter += 1

            from narration_pipeline import translate_to_russian
            title_ru = translate_to_russian(story.get("title", ""))
            body_ru = translate_to_russian(story.get("body", ""))
            story["title"] = title_ru
            story["body"] = body_ru
            story["full_text"] = f"{title_ru}. {body_ru}".strip()

            story_id = f"{subreddit.lower()}_story_{story_counter:03d}_{raw_id}"
            total_display = "∞" if is_infinite else str(count)

            print("\n------------------------------------------------------------------")
            print(f"📌 BATCH ITEM [{story_counter}/{total_display}]: \"{title_ru[:65]}...\" (ID: {story_id})")
            print("------------------------------------------------------------------")

            # Format text with ElevenLabs tags
            formatted_script = format_text_with_elevenlabs_tags(title_ru, body_ru, translate_ru=False)
            chunks = split_text_into_chunks(formatted_script, max_len=920)
            total_chunks = len(chunks)

            print(f"✍️ Story formatted into {total_chunks} chunks for ElevenLabs synthesis.")

            # Publish story to local API server
            set_current_story(
                story,
                formatted_text=formatted_script,
                story_id=story_id,
                story_idx=story_counter,
                total_stories=0 if is_infinite else count,
                total_chunks=total_chunks
            )

            # Generate post card PNG
            card_png_path = os.path.join(abs_out_dir, "cards", f"{story_id}_card.png")
            generate_reddit_card(story, output_path=card_png_path)

            print(f"\n📡 STORY PUBLISHED TO SERVER! Open/switch to ElevenLabs in browser.")
            print(f"👉 Tampermonkey v2.5 will auto-load Story #{story_counter} ({total_chunks} chunks) and upload audio!")

            # Wait for Tampermonkey userscript to auto-send audio chunks
            chunk_mp3_paths = wait_for_story_chunks(story_id=story_id, expected_chunks=total_chunks)

            # Merge audio chunks for this specific story_id
            merged_audio_path = os.path.join(abs_out_dir, "audio", f"{story_id}_narration.mp3")
            merge_mp3_chunks(chunk_mp3_paths, merged_audio_path)

            # Generate Karaoke ASS Subtitles
            subtitle_ass_path = os.path.join(abs_out_dir, "subtitles", f"{story_id}_subtitles.ass")
            generate_ass_subtitles(merged_audio_path, output_ass_path=subtitle_ass_path, model_size="tiny")

            # Assemble TikTok Vertical Video
            final_mp4_path = os.path.join(abs_out_dir, "videos", f"{story_id}_tiktok.mp4")
            assemble_tiktok_video(
                audio_path=merged_audio_path,
                card_png_path=card_png_path,
                subtitle_ass_path=subtitle_ass_path,
                background_dir=bg_dir,
                output_mp4_path=final_mp4_path
            )

            completed_videos.append(final_mp4_path)
            print(f"\n🎉 COMPLETED BATCH ITEM [{story_counter}/{total_display}] -> {final_mp4_path}")

    except KeyboardInterrupt:
        print("\n\n🛑 Batch processing loop interrupted by user (Ctrl+C).")

    print("\n==================================================================")
    print(f"🏆 BATCH SESSION COMPLETE! Created {len(completed_videos)} videos.")
    for idx, v in enumerate(completed_videos, start=1):
        print(f"  🎬 [{idx}] {v}")
    print("==================================================================\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Infinite Batch Reddit TikTok Video Generator Loop")
    parser.add_argument("--subreddit", type=str, default="AskReddit", help="Subreddit name (AskReddit, AmItheAsshole, tifu, stories)")
    parser.add_argument("--count", type=int, default=0, help="Number of videos to generate (0 = infinite loop until Ctrl+C)")
    parser.add_argument("--bg-dir", type=str, default="backgrounds", help="Background videos directory")
    parser.add_argument("--out-dir", type=str, default="output_batch_videos", help="Output directory for generated videos")
    args = parser.parse_args()

    run_infinite_batch_pipeline(
        subreddit=args.subreddit,
        count=args.count,
        bg_dir=args.bg_dir,
        output_dir=args.out_dir
    )
