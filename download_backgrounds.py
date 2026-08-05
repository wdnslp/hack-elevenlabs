import os
import sys
import subprocess

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BACKGROUNDS_DIR = os.path.abspath("backgrounds")
os.makedirs(BACKGROUNDS_DIR, exist_ok=True)

SEARCH_QUERIES = [
    ("minecraft_parkour", "ytsearch5:minecraft parkour gameplay shorts no commentary"),
    ("gta5_ramp", "ytsearch5:gta 5 mega ramp gameplay shorts no commentary"),
    ("subway_surfers", "ytsearch5:subway surfers gameplay shorts no commentary"),
    ("kinetic_sand", "ytsearch5:satisfying ASMR kinetic sand shorts"),
    ("soap_cutting", "ytsearch5:oddly satisfying soap cutting ASMR shorts"),
    ("satisfying_cooking", "ytsearch5:satisfying cooking ASMR shorts")
]

def download_category(category_name, search_query):
    output_template = os.path.join(BACKGROUNDS_DIR, f"{category_name}_%(id)s.mp4")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--format", "bestvideo[height>=1080]+bestaudio/bestvideo[height>=720]+bestaudio/best[height>=1080]/best",
        "--max-filesize", "80M",
        "--no-playlist",
        "-o", output_template,
        search_query
    ]
    try:
        print(f"📥 Downloading background videos for: {category_name}...")
        subprocess.run(cmd, check=True)
    except Exception as e:
        print(f"⚠️ Notice downloading {category_name}: {e}")

if __name__ == "__main__":
    for cat, query in SEARCH_QUERIES:
        download_category(cat, query)
