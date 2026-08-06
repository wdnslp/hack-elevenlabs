"""
FFmpeg TikTok Video Assembler & Compositor
Combines background 1080x1920 video/gradient, Reddit post card overlay, narration audio, and ASS Karaoke subtitles into vertical TikTok MP4.
"""

import sys
import os
import glob
import subprocess
import argparse
from typing import Optional

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def get_audio_duration(audio_path: str) -> float:
    """Get exact audio duration in seconds via ffprobe or Python fallback."""
    abs_path = os.path.abspath(audio_path)

    # Method 1: ffprobe csv format
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        abs_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        dur = float(res.stdout.strip())
        if dur > 0:
            return dur
    except Exception:
        pass

    # Method 2: ffprobe json format
    cmd_json = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        abs_path
    ]
    try:
        res = subprocess.run(cmd_json, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(res.stdout)
        dur = float(data.get("format", {}).get("duration", 0))
        if dur > 0:
            return dur
    except Exception:
        pass

    # Method 3: Mutagen fallback if available
    try:
        from mutagen.mp3 import MP3
        audio = MP3(abs_path)
        if audio.info.length > 0:
            return float(audio.info.length)
    except Exception:
        pass

    return 30.0

def assemble_tiktok_video(
    audio_path: str = "narration.mp3",
    card_png_path: str = "reddit_card.png",
    subtitle_ass_path: str = "subtitles.ass",
    background_dir: str = "backgrounds",
    output_mp4_path: str = "output_tiktok_video.mp4"
) -> str:
    """Assemble final 1080x1920 vertical video for TikTok."""
    abs_audio = os.path.abspath(audio_path)
    abs_card = os.path.abspath(card_png_path)
    abs_ass = os.path.abspath(subtitle_ass_path)
    abs_out = os.path.abspath(output_mp4_path)

    if not os.path.exists(abs_audio):
        print(f"❌ Audio file missing: {abs_audio}")
        return abs_out

    duration = get_audio_duration(abs_audio)
    print(f"🎬 Assembling video... Audio Duration: {duration:.2f}s")

    # Search for background videos in background_dir
    bg_files = glob.glob(os.path.join(background_dir, "*.mp4")) if os.path.exists(background_dir) else []
    
    # Escape paths for FFmpeg filter syntax
    escaped_ass = abs_ass.replace('\\', '/').replace(':', '\\:')
    escaped_card = abs_card.replace('\\', '/').replace(':', '\\:')

    import random
    if len(bg_files) >= 2:
        bg1, bg2 = random.sample(bg_files, 2)
        half_dur = round(duration / 2.0, 2)
        rem_dur = round(duration - half_dur, 2)
        
        print(f"📹 Dual Background Sequential Cut: [{os.path.basename(bg1)}] ({half_dur}s) -> [{os.path.basename(bg2)}] ({rem_dur}s)")
        print("✂️ Full Screen 9:16 (1080x1920) Video 1 for 1st half -> Video 2 for 2nd half")
        
        bg_filter = (
            f"[0:v]trim=duration={half_dur},scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,setpts=PTS-STARTPTS[v1part];"
            f"[1:v]trim=duration={rem_dur},scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,setpts=PTS-STARTPTS[v2part];"
            f"[v1part][v2part]concat=n=2:v=1:a=0[bg];"
        )

        card_overlay = f"[2:v]scale=900:-1[scaled_card];[bg][scaled_card]overlay=x=(W-w)/2:y=240:enable='lte(t,4.5)':eval=frame[v1]"
        if os.path.exists(abs_ass):
            vf_filter = bg_filter + card_overlay + f";[v1]subtitles=filename='{escaped_ass}'[outv]"
        else:
            vf_filter = bg_filter + card_overlay + f";[v1]copy[outv]"

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-stream_loop", "-1", "-i", bg1,
            "-stream_loop", "-1", "-i", bg2,
            "-i", abs_card,
            "-i", abs_audio,
            "-filter_complex", vf_filter,
            "-map", "[outv]",
            "-map", "3:a",  # Narration audio only (background video audio is muted!)
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-t", str(duration),
            abs_out
        ]
    elif len(bg_files) == 1:
        bg1 = bg_files[0]
        print(f"📹 Single Background Video: [{os.path.basename(bg1)}]")
        bg_filter = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[bg];"
        card_overlay = f"[1:v]scale=900:-1[scaled_card];[bg][scaled_card]overlay=x=(W-w)/2:y=240:enable='lte(t,4.5)':eval=frame[v1]"
        if os.path.exists(abs_ass):
            vf_filter = bg_filter + card_overlay + f";[v1]subtitles=filename='{escaped_ass}'[outv]"
        else:
            vf_filter = bg_filter + card_overlay + f";[v1]copy[outv]"

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-stream_loop", "-1", "-i", bg1,
            "-i", abs_card,
            "-i", abs_audio,
            "-filter_complex", vf_filter,
            "-map", "[outv]",
            "-map", "2:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-t", str(duration),
            abs_out
        ]
    else:
        print("🎨 No background MP4 found in backgrounds/. Generating animated dark gradient...")
        bg_gen = f"color=c=0x0f1419:s=1080x1920:d={duration}"
        card_overlay = f"[1:v]scale=900:-1[scaled_card];[bg][scaled_card]overlay=x=(W-w)/2:y=240:enable='lte(t,4.5)':eval=frame[v1]"
        if os.path.exists(abs_ass):
            vf_filter = f"[0:v]setsar=1[bg];" + card_overlay + f";[v1]subtitles=filename='{escaped_ass}'[outv]"
        else:
            vf_filter = f"[0:v]setsar=1[bg];" + card_overlay + f";[v1]copy[outv]"

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", bg_gen,
            "-i", abs_card,
            "-i", abs_audio,
            "-filter_complex", vf_filter,
            "-map", "[outv]",
            "-map", "2:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-t", str(duration),
            abs_out
        ]

    try:
        res = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and os.path.exists(abs_out):
            print(f"🎉 FINAL TIKTOK VIDEO CREATED SUCCESSFULLY -> {abs_out}")
        else:
            print(f"❌ FFmpeg rendering failed: {res.stderr}")
    except Exception as e:
        print(f"❌ FFmpeg error: {e}")

    return abs_out

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Assemble vertical TikTok video from elements")
    parser.add_argument("--audio", type=str, default="narration.mp3", help="Input audio MP3")
    parser.add_argument("--card", type=str, default="reddit_card.png", help="Input Reddit card PNG")
    parser.add_argument("--subtitles", type=str, default="subtitles.ass", help="Input ASS subtitles")
    parser.add_argument("--bg-dir", type=str, default="backgrounds", help="Background videos folder")
    parser.add_argument("--out", type=str, default="output_tiktok_video.mp4", help="Output MP4 video")
    args = parser.parse_args()

    assemble_tiktok_video(
        audio_path=args.audio,
        card_png_path=args.card,
        subtitle_ass_path=args.subtitles,
        background_dir=args.bg_dir,
        output_mp4_path=args.out
    )
