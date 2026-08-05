"""
Full Reddit TikTok Video Generator Orchestrator (Tampermonkey Voiceover Workflow)
Executes full end-to-end pipeline:
1. Reddit Story Scraping & Selection
2. Tagged Text Formatting for ElevenLabs Assistant Userscript
3. Reddit Post Card Generation
4. Audio Narration Resolution (User Tampermonkey Voiceover)
5. Whisper Karaoke Subtitles Generation
6. FFmpeg TikTok Vertical Video Composition
"""

import sys
import os
import json
import argparse
from reddit_scraper import fetch_top_stories, get_single_story
from reddit_card_generator import generate_reddit_card
from narration_pipeline import process_story_audio, export_story_for_userscript
from subtitle_generator import generate_ass_subtitles
from video_assembler import assemble_tiktok_video

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def run_pipeline(
    subreddit: str = "AskReddit",
    story_idx: int = 0,
    voice_name: str = "Den",
    bg_dir: str = "backgrounds",
    out_mp4: str = "tiktok_story_video.mp4",
    audio_path: str = "narration.mp3",
    wait_audio: bool = False
) -> str:
    print("\n==================================================")
    print("🎬 STARTING REDDIT TIKTOK VIDEO GENERATION PIPELINE")
    print("==================================================\n")

    # Step 1: Fetch Story
    print(f"📖 Step 1: Fetching top story from r/{subreddit}...")
    story = get_single_story(subreddit=subreddit, story_idx=story_idx)
    if not story:
        print("❌ Failed to retrieve Reddit story.")
        return ""

    print(f"📌 Story Selected: \"{story['title']}\" by u/{story['author']} ({story['word_count']} words)")
    
    # Save story json for reference
    with open("current_story.json", "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=2)

    # Step 2: Format Story with ElevenLabs Tags for Userscript
    print("\n✍️ Step 2: Formatting Reddit story with ElevenLabs tags ([sigh], [whisper], [gasp])...")
    txt_path = export_story_for_userscript(story, output_txt_path="formatted_story_elevenlabs.txt")

    # Step 3: Generate Post Card PNG
    print("\n🖼️ Step 3: Generating dark mode Reddit post card...")
    card_path = generate_reddit_card(story, output_path="reddit_card.png")

    # Step 4: ElevenLabs Audio Narration Resolution
    print("\n🎙️ Step 4: Resolving ElevenLabs audio narration...")
    audio_path = process_story_audio(story, output_path=audio_path, voice_name=voice_name, wait_for_user=wait_audio)

    if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 5000:
        print(f"\n⚠️ Audio narration file '{audio_path}' is missing or empty.")
        print(f"👉 Please use Tampermonkey 'ElevenLabs Assistant' on '{txt_path}', save the result as '{audio_path}', and re-run with --audio {audio_path} or --wait-audio!")
        return ""

    # Step 5: Karaoke Subtitles
    print("\n📝 Step 5: Transcribing audio and generating Karaoke ASS Subtitles...")
    subtitle_path = generate_ass_subtitles(audio_path, output_ass_path="subtitles.ass", model_size="tiny")

    # Step 6: Assemble Final Video
    print("\n🎥 Step 6: Assembling final 1080x1920 video for TikTok...")
    final_video = assemble_tiktok_video(
        audio_path=audio_path,
        card_png_path=card_path,
        subtitle_ass_path=subtitle_path,
        background_dir=bg_dir,
        output_mp4_path=out_mp4
    )

    print("\n==================================================")
    print(f"🎉 PIPELINE COMPLETE! Final Video: {os.path.abspath(final_video)}")
    print("==================================================\n")
    return final_video

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full Reddit to TikTok Video Pipeline Generator")
    parser.add_argument("--subreddit", type=str, default="AskReddit", help="Subreddit name (AskReddit, AmItheAsshole, tifu, stories)")
    parser.add_argument("--index", type=int, default=0, help="Story index from top posts (0 = top 1, 1 = top 2)")
    parser.add_argument("--voice", type=str, default="Den", help="Voice name for narration")
    parser.add_argument("--audio", type=str, default="narration.mp3", help="Input narration MP3 file")
    parser.add_argument("--wait-audio", action="store_true", help="Wait for user to drop narration.mp3 file into project folder")
    parser.add_argument("--bg-dir", type=str, default="backgrounds", help="Background video folder")
    parser.add_argument("--out", type=str, default="tiktok_story_video.mp4", help="Output MP3/MP4 file name")
    args = parser.parse_args()

    run_pipeline(
        subreddit=args.subreddit,
        story_idx=args.index,
        voice_name=args.voice,
        bg_dir=args.bg_dir,
        out_mp4=args.out,
        audio_path=args.audio,
        wait_audio=args.wait_audio
    )

