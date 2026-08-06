"""
Local Story API HTTP Server for Tampermonkey ElevenLabs Assistant (Batch Workflow)
Serves current Reddit story & receives audio chunks directly from Tampermonkey userscript.
"""

import sys
import os
import json
import base64
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List, Optional

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CURRENT_STORY_DATA: Dict[str, Any] = {
    "story_id": "",
    "story_idx": 1,
    "total_stories": 1,
    "title": "",
    "body": "",
    "formatted_text": "",
    "subreddit": "",
    "author": "",
    "total_chunks": 1,
    "status": "idle"
}

# Mapping: story_id -> dict of {chunk_idx: chunk_file_path}
RECEIVED_STORY_CHUNKS: Dict[str, Dict[int, str]] = {}
CHUNKS_LOCK = threading.Lock()

def rotate_vpn_ip() -> bool:
    """Automated IP rotation using Cloudflare WARP CLI."""
    import subprocess
    warp_cli_path = r"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe"

    print("⚡ [AUTOROTATE] Initiating auto IP rotation via Cloudflare WARP CLI...")
    try:
        cmd = warp_cli_path if os.path.exists(warp_cli_path) else "warp-cli"
        try:
            subprocess.run([cmd, "registration", "new"], capture_output=True, timeout=10)
        except Exception:
            pass

        subprocess.run([cmd, "disconnect"], capture_output=True, timeout=10)
        time.sleep(1.5)
        res = subprocess.run([cmd, "connect"], capture_output=True, timeout=10)
        time.sleep(2.5)
        print("✅ [AUTOROTATE] Cloudflare WARP IP successfully rotated!")
        return True
    except Exception as e:
        print(f"⚠️ [AUTOROTATE WARN] Automatic WARP CLI rotation failed: {e}")
        return False

class StoryApiRequestHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path in ("/api/story", "/api/story/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._send_cors_headers()
            self.end_headers()
            response_bytes = json.dumps(CURRENT_STORY_DATA, ensure_ascii=False).encode("utf-8")
            self.wfile.write(response_bytes)
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def do_POST(self):
        if self.path in ("/api/upload_chunk", "/api/upload_chunk/"):
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                raw_sid = payload.get("story_id")
                curr_sid = CURRENT_STORY_DATA.get("story_id") or "default_story"
                story_id = raw_sid if (raw_sid and raw_sid != "default_story") else curr_sid

                chunk_idx = int(payload.get("chunk_idx", 0))
                total_chunks = int(payload.get("total_chunks", CURRENT_STORY_DATA.get("total_chunks", 1)))
                audio_b64 = payload.get("audio_base64", "")

                if not audio_b64:
                    raise ValueError("No audio_base64 provided")

                audio_bytes = base64.b64decode(audio_b64)
                
                # Save chunk to temp folder
                story_temp_dir = os.path.abspath(os.path.join("temp_chunks", story_id))
                os.makedirs(story_temp_dir, exist_ok=True)
                chunk_path = os.path.join(story_temp_dir, f"chunk_{chunk_idx + 1:02d}.mp3")

                with open(chunk_path, "wb") as f:
                    f.write(audio_bytes)

                with CHUNKS_LOCK:
                    if story_id not in RECEIVED_STORY_CHUNKS:
                        RECEIVED_STORY_CHUNKS[story_id] = {}
                    RECEIVED_STORY_CHUNKS[story_id][chunk_idx] = chunk_path
                    received_count = len(RECEIVED_STORY_CHUNKS[story_id])
                    is_complete = (received_count >= total_chunks)

                print(f"📥 API: Received chunk {chunk_idx + 1}/{total_chunks} for story [{story_id}] ({len(audio_bytes)} bytes)")

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._send_cors_headers()
                self.end_headers()
                resp = {
                    "status": "ok",
                    "story_id": story_id,
                    "chunk_idx": chunk_idx,
                    "received_count": received_count,
                    "total_chunks": total_chunks,
                    "is_complete": is_complete
                }
                self.wfile.write(json.dumps(resp, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        
        elif self.path in ("/api/story", "/api/story/"):
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode("utf-8"))
                set_current_story(data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        elif self.path in ("/api/limit_reached", "/api/limit_reached/"):
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode("utf-8")) if post_data else {}
                reason = data.get("reason", "unknown")
                resets = data.get("resets", 0)
                print(f"\n\a🚨 [SERVER ALERT] ELEVENLABS LIMIT DETECTED! Reason: {reason}")
                
                # Execute automatic VPN IP rotation in background thread
                threading.Thread(target=rotate_vpn_ip, daemon=True).start()

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "message": "Auto IP rotation initiated"}, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()



    def log_message(self, format, *args):
        # Suppress standard HTTP request noise in console
        pass

_SERVER_INSTANCE: Optional[HTTPServer] = None
_SERVER_THREAD: Optional[threading.Thread] = None

def set_current_story(story: Dict[str, Any], formatted_text: str = "", story_id: str = "", story_idx: int = 1, total_stories: int = 1, total_chunks: int = 1):
    global CURRENT_STORY_DATA
    try:
        from narration_pipeline import translate_to_russian, format_text_with_elevenlabs_tags
        raw_title = story.get("title", "")
        raw_body = story.get("body", "")
        title = translate_to_russian(raw_title)
        body = translate_to_russian(raw_body)
        if not formatted_text or (raw_title and raw_title in formatted_text):
            formatted_text = format_text_with_elevenlabs_tags(title, body, translate_ru=False)
    except Exception:
        title = story.get("title", "")
        body = story.get("body", "")

    s_id = story_id or story.get("story_id") or story.get("id") or f"story_{story_idx:02d}"
    CURRENT_STORY_DATA = {
        "story_id": s_id,
        "story_idx": story_idx,
        "total_stories": total_stories,
        "title": title,
        "body": body,
        "formatted_text": formatted_text,
        "subreddit": story.get("subreddit", "AskReddit"),
        "author": story.get("author", "anonymous"),
        "total_chunks": total_chunks,
        "status": "ready"
    }

def get_received_chunks_for_story(story_id: str) -> List[str]:
    with CHUNKS_LOCK:
        chunks_map = RECEIVED_STORY_CHUNKS.get(story_id, {})
        sorted_indices = sorted(chunks_map.keys())
        return [chunks_map[i] for i in sorted_indices]

AUDIO_EXTS = ('.mp3', '.wav', '.m4a', '.aac', '.ogg')

def check_downloads_or_local_chunks(story_id: str, expected_chunks: int) -> List[str]:
    import glob
    import shutil

    temp_dir = os.path.abspath(os.path.join("temp_chunks", story_id))
    if os.path.exists(temp_dir):
        files = sorted(glob.glob(os.path.join(temp_dir, "*.mp3")) + glob.glob(os.path.join(temp_dir, "*.wav")))
        valid_files = [f for f in files if os.path.exists(f) and os.path.getsize(f) > 3000]
        if len(valid_files) >= expected_chunks:
            return valid_files

    now = time.time()

    # Search Downloads folder
    downloads_dir = os.path.expanduser("~/Downloads")
    if os.path.exists(downloads_dir):
        dl_candidates = glob.glob(os.path.join(downloads_dir, "chunk*")) + glob.glob(os.path.join(downloads_dir, "narration*"))
        valid_dl = [
            f for f in sorted(dl_candidates, key=os.path.getmtime)
            if os.path.isfile(f) and f.lower().endswith(AUDIO_EXTS) and os.path.getsize(f) > 3000 and (now - os.path.getmtime(f)) < 600
        ]
        if valid_dl:
            os.makedirs(temp_dir, exist_ok=True)
            imported = []
            for idx, fpath in enumerate(valid_dl[:expected_chunks]):
                ext = os.path.splitext(fpath)[1] or ".mp3"
                dest = os.path.join(temp_dir, f"chunk_{idx+1:02d}{ext}")
                try:
                    shutil.move(fpath, dest)
                    imported.append(dest)
                    print(f"📥 Fallback pickup: Moved '{os.path.basename(fpath)}' from Downloads -> '{dest}'")
                except Exception as e:
                    print(f"⚠️ Move error: {e}")
            if len(imported) >= expected_chunks:
                return imported

    # Search current working directory
    local_candidates = glob.glob("chunk*") + glob.glob("narration*")
    valid_local = [
        f for f in sorted(local_candidates, key=os.path.getmtime)
        if os.path.isfile(f) and f.lower().endswith(AUDIO_EXTS) and os.path.getsize(f) > 3000 and (now - os.path.getmtime(f)) < 600 and not f.startswith("temp_")
    ]
    if valid_local:
        os.makedirs(temp_dir, exist_ok=True)
        imported = []
        for idx, fpath in enumerate(valid_local[:expected_chunks]):
            ext = os.path.splitext(fpath)[1] or ".mp3"
            dest = os.path.join(temp_dir, f"chunk_{idx+1:02d}{ext}")
            try:
                shutil.move(fpath, dest)
                imported.append(dest)
                print(f"📥 Fallback pickup: Moved '{os.path.basename(fpath)}' from workspace -> '{dest}'")
            except Exception as e:
                print(f"⚠️ Move error: {e}")
        if len(imported) >= expected_chunks:
            return imported

    return []

import queue

_CONSOLE_INPUT_QUEUE = queue.Queue()
_CONSOLE_THREAD_STARTED = False

def _console_input_reader():
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            cmd = line.strip().lower()
            if cmd:
                _CONSOLE_INPUT_QUEUE.put(cmd)
        except Exception:
            break

def start_console_input_listener():
    global _CONSOLE_THREAD_STARTED
    if not _CONSOLE_THREAD_STARTED and hasattr(sys.stdin, 'isatty') and sys.stdin.isatty():
        t = threading.Thread(target=_console_input_reader, daemon=True)
        t.start()
        _CONSOLE_THREAD_STARTED = True

class SkipStoryException(Exception):
    pass

def wait_for_story_chunks(story_id: str, expected_chunks: int, poll_interval: float = 1.0) -> List[str]:
    """Block until all expected audio chunks for story_id have been received via API/pickup, or return [] if skipped by user."""
    start_console_input_listener()
    print(f"⏳ Waiting for audio ({expected_chunks} chunks) for story [{story_id}]...")
    print(f"👉 Type 'skip' (or 's') + Enter to skip this story at any time!\n")

    while True:
        while not _CONSOLE_INPUT_QUEUE.empty():
            try:
                cmd = _CONSOLE_INPUT_QUEUE.get_nowait()
                if cmd in ("skip", "s", "next"):
                    print(f"\n⏩ 'skip' command received! Skipping story [{story_id}]...")
                    return []
            except queue.Empty:
                break

        with CHUNKS_LOCK:
            chunks_map = RECEIVED_STORY_CHUNKS.get(story_id, {})
            if len(chunks_map) >= expected_chunks:
                sorted_indices = sorted(chunks_map.keys())
                chunk_paths = [chunks_map[i] for i in sorted_indices]
                print(f"🎉 Received all {len(chunk_paths)}/{expected_chunks} audio chunks via API for story [{story_id}]!")
                return chunk_paths

        fallback_paths = check_downloads_or_local_chunks(story_id, expected_chunks)
        if fallback_paths:
            print(f"🎉 Auto-picked {len(fallback_paths)}/{expected_chunks} audio chunks from Downloads/workspace!")
            return fallback_paths

        time.sleep(poll_interval)


def start_story_api_server(host: str = "127.0.0.1", port: int = 5000) -> int:
    global _SERVER_INSTANCE, _SERVER_THREAD
    if _SERVER_INSTANCE is not None:
        return port

    try:
        _SERVER_INSTANCE = HTTPServer((host, port), StoryApiRequestHandler)
        _SERVER_THREAD = threading.Thread(target=_SERVER_INSTANCE.serve_forever, daemon=True)
        _SERVER_THREAD.start()
        print(f"📡 Local Story API Server active on http://{host}:{port}/api/story")
        return port
    except Exception as e:
        print(f"⚠️ Could not start Story API server on port {port}: {e}")
        return port

if __name__ == "__main__":
    test_story = {
        "title": "What is the most unsettling secret you discovered by accident?",
        "body": "A few years ago, while cleaning out my grandfather's old attic..."
    }
    set_current_story(test_story, formatted_text="[narrator] [curious] What is the most unsettling secret...", story_id="test_01", total_chunks=2)
    port = start_story_api_server(port=5000)
    print("Server running. Listening for story chunks...")
    chunks = wait_for_story_chunks("test_01", expected_chunks=2)
    print("All chunks received:", chunks)
