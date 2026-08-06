"""
Karaoke ASS Subtitle Generator using Gemini API & faster-whisper
Extracts word-level timestamps from audio and generates animated ASS (Advanced SubStation Alpha) karaoke subtitles.
Supports Google Gemini Flash API transcription and faster-whisper fallback.
"""

import sys
import os
import re
import json
import argparse
from typing import List, Dict, Any, Optional

def load_env_file(env_path: str = ".env"):
    """Load environment variables from .env file without external dependencies."""
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() not in os.environ:
                            os.environ[k.strip()] = v.strip().strip("'\"")
        except Exception:
            pass

load_env_file()


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
Style: Karaoke,Impact,76,&H00FFFFFF,&H0000E6FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,40,40,500,1

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

def build_ass_from_words_data(words_data: List[Dict[str, Any]], output_ass_path: str, chunk_size: int = 2) -> str:
    """Build ASS Karaoke subtitle file from list of word timestamp dictionaries."""
    abs_ass = os.path.abspath(output_ass_path)
    if not words_data:
        print("⚠️ No word timestamps provided to build ASS subtitles.")
        return abs_ass

    lines = []
    for i in range(0, len(words_data), chunk_size):
        chunk = words_data[i:i + chunk_size]
        start_time = chunk[0]["start"]
        end_time = chunk[-1]["end"]
        
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

    os.makedirs(os.path.dirname(abs_ass), exist_ok=True) if os.path.dirname(abs_ass) else None
    with open(abs_ass, "w", encoding="utf-8") as f:
        f.write(ASS_HEADER)
        f.write("\n".join(lines) + "\n")

    print(f"✅ Generated ASS Karaoke Subtitles -> {abs_ass} ({len(lines)} lines)")
    return abs_ass

def generate_ass_subtitles_gemini(audio_path: str, output_ass_path: str = "subtitles.ass", api_key: Optional[str] = None) -> Optional[str]:
    """Transcribe audio with Gemini API and export karaoke ASS subtitles."""
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        print("⚠️ Gemini API key not found in environment (GEMINI_API_KEY). Skipping Gemini transcription.")
        return None

    abs_audio = os.path.abspath(audio_path)
    if not os.path.exists(abs_audio):
        print(f"❌ Audio file not found: {abs_audio}")
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        print(f"🤖 Uploading audio to Gemini API: {os.path.basename(abs_audio)}...")
        uploaded_file = client.files.upload(file=abs_audio)

        prompt = (
            "You are an accurate audio transcription tool.\n"
            "Listen to the audio file and transcribe the spoken words accurately in Russian.\n"
            "Extract word-level or short phrase-level timestamps.\n"
            "Return ONLY a valid JSON array of objects with the exact schema:\n"
            "[\n"
            '  {"word": "слово", "start": 0.12, "end": 0.45},\n'
            "  ...\n"
            "]\n"
            "Field 'word' MUST be a string, 'start' MUST be start timestamp in seconds (float), 'end' MUST be end timestamp in seconds (float).\n"
            "Do not include any explanation or markdown formatting outside of the JSON array."
        )

        models_to_try = [
            "models/gemini-3.5-flash-lite",
            "models/gemini-2.5-flash-lite",
            "models/gemini-3.5-flash",
            "models/gemini-2.5-flash"
        ]


        words_data = []
        try:
            for model_name in models_to_try:
                try:
                    print(f"🤖 Requesting audio transcription with timestamps from Gemini ({model_name})...")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[uploaded_file, prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )

                    if response and response.text:
                        raw_json = response.text.strip()
                        if raw_json.startswith("```"):
                            lines = raw_json.splitlines()
                            if lines[0].startswith("```"):
                                lines = lines[1:]
                            if lines and lines[-1].startswith("```"):
                                lines = lines[:-1]
                            raw_json = "\n".join(lines).strip()

                        parsed = json.loads(raw_json)
                        if isinstance(parsed, dict):
                            for k in ["words", "subtitles", "transcript", "items", "segments"]:
                                if k in parsed and isinstance(parsed[k], list):
                                    parsed = parsed[k]
                                    break

                        if isinstance(parsed, list):
                            for item in parsed:
                                if isinstance(item, dict):
                                    w = str(item.get("word") or item.get("text") or "").strip()
                                    s = float(item.get("start", 0.0))
                                    e = float(item.get("end", s + 0.3))
                                    clean_w = re.sub(r'\[.*?\]', '', w).strip()
                                    if clean_w and e > s:
                                        words_data.append({"word": clean_w, "start": s, "end": e})

                        if words_data:
                            print(f"✨ Gemini ({model_name}) extracted {len(words_data)} word timestamps!")
                            break
                except Exception as model_err:
                    print(f"⚠️ Gemini model {model_name} failed: {model_err}")
                    continue
        finally:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass

        if words_data:
            return build_ass_from_words_data(words_data, output_ass_path)
        else:
            print("⚠️ Gemini transcription returned no valid word timestamps.")
            return None

    except Exception as e:
        print(f"⚠️ Gemini transcription notice: {e}")
        return None

def generate_ass_subtitles_whisper(audio_path: str, output_ass_path: str = "subtitles.ass", model_size: str = "base") -> str:
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
                raw_word = word.word.strip()
                clean_word = re.sub(r'\[.*?\]', '', raw_word).strip()
                if clean_word:
                    words_data.append({
                        "word": clean_word,
                        "start": word.start,
                        "end": word.end
                    })

    return build_ass_from_words_data(words_data, abs_ass)

def generate_ass_subtitles(
    audio_path: str,
    output_ass_path: str = "subtitles.ass",
    model_size: str = "base",
    engine: str = "auto",
    api_key: Optional[str] = None
) -> str:
    """Generate ASS subtitles using Gemini API or faster-whisper.
    
    engine options:
    - 'auto': try Gemini API first if GEMINI_API_KEY is set, fallback to whisper
    - 'gemini': use Gemini API, fallback to whisper on error
    - 'whisper': use faster-whisper directly
    """
    abs_audio = os.path.abspath(audio_path)
    abs_ass = os.path.abspath(output_ass_path)

    if engine in ("auto", "gemini"):
        print("🤖 Attempting subtitle generation via Gemini API...")
        res = generate_ass_subtitles_gemini(abs_audio, abs_ass, api_key=api_key)
        if res and os.path.exists(res):
            return res
        print("🔄 Falling back to faster-whisper for subtitle generation...")

    return generate_ass_subtitles_whisper(abs_audio, abs_ass, model_size=model_size)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate ASS Karaoke Subtitles from Audio using Gemini API or faster-whisper")
    parser.add_argument("--audio", type=str, default="narration.mp3", help="Input audio file")
    parser.add_argument("--out", type=str, default="subtitles.ass", help="Output ASS subtitle file")
    parser.add_argument("--model", type=str, default="base", help="Whisper model size (tiny, base, small)")
    parser.add_argument("--engine", type=str, default="auto", choices=["auto", "gemini", "whisper"], help="Subtitle engine (auto, gemini, whisper)")
    parser.add_argument("--api-key", type=str, default=None, help="Gemini API Key (optional, defaults to GEMINI_API_KEY env var)")
    args = parser.parse_args()

    generate_ass_subtitles(args.audio, output_ass_path=args.out, model_size=args.model, engine=args.engine, api_key=args.api_key)
