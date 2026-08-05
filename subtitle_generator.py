"""
Karaoke ASS Subtitle Generator using faster-whisper
Extracts word-level timestamps from audio and generates animated ASS (Advanced SubStation Alpha) karaoke subtitles.
"""

import sys
import os
import argparse
from typing import List, Dict, Any

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ASS_HEADER = """[Script Info]
Title: TikTok Karaoke Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Arial,68,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,60,60,450,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

def format_timestamp(seconds: float) -> str:
    """Format float seconds into ASS timestamp H:MM:SS.cs"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"

def generate_ass_subtitles(audio_path: str, output_ass_path: str = "subtitles.ass", model_size: str = "tiny") -> str:
    """Transcribe audio with faster-whisper and export karaoke ASS subtitles."""
    abs_audio = os.path.abspath(audio_path)
    abs_ass = os.path.abspath(output_ass_path)
    
    if not os.path.exists(abs_audio):
        print(f"❌ Audio file not found: {abs_audio}")
        return abs_ass

    print(f"🎙️ Transcribing {abs_audio} with faster-whisper ({model_size} model)...")
    from faster_whisper import WhisperModel
    
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(abs_audio, word_timestamps=True, language="ru")

    words_data = []
    for segment in segments:
        if segment.words:
            for word in segment.words:
                clean_word = word.word.strip()
                if clean_word:
                    words_data.append({
                        "word": clean_word,
                        "start": word.start,
                        "end": word.end
                    })

    if not words_data:
        print("⚠️ No word timestamps extracted from audio.")
        return abs_ass

    # Chunk words into groups of 2-4 words per subtitle line
    lines = []
    chunk_size = 3
    for i in range(0, len(words_data), chunk_size):
        chunk = words_data[i:i + chunk_size]
        start_time = chunk[0]["start"]
        end_time = chunk[-1]["end"]
        
        # Build Karaoke ASS string with \kf tags (centiseconds highlight)
        ass_text_parts = []
        for w in chunk:
            duration_cs = int(round((w["end"] - w["start"]) * 100))
            if duration_cs < 5:
                duration_cs = 5
            ass_text_parts.append(f"{{\\kf{duration_cs}}}{w['word']}")
            
        line_text = " ".join(ass_text_parts)
        start_str = format_timestamp(start_time)
        end_str = format_timestamp(end_time)
        
        lines.append(f"Dialogue: 0,{start_str},{end_str},Karaoke,,0,0,0,,{line_text}")

    with open(abs_ass, "w", encoding="utf-8") as f:
        f.write(ASS_HEADER)
        f.write("\n".join(lines) + "\n")

    print(f"✅ Generated ASS Karaoke Subtitles -> {abs_ass} ({len(lines)} lines)")
    return abs_ass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate ASS Karaoke Subtitles from Audio using faster-whisper")
    parser.add_argument("--audio", type=str, default="narration.mp3", help="Input audio file")
    parser.add_argument("--out", type=str, default="subtitles.ass", help="Output ASS subtitle file")
    parser.add_argument("--model", type=str, default="tiny", help="Whisper model size (tiny, base, small)")
    args = parser.parse_args()

    generate_ass_subtitles(args.audio, output_ass_path=args.out, model_size=args.model)
