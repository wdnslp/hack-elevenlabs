"""
ElevenLabs Narration & Text Tagging Pipeline (Tampermonkey Assistant Mode)
Formats Reddit stories with expressive ElevenLabs tags ([sigh], [whisper], [gasp], [dramatic])
and exports text for user semi-automated voiceover via Tampermonkey Userscript.
"""

import sys
import os
import re
import json
import time
import argparse
from typing import Dict, Any, List, Optional

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

TAG_PALETTE = [
    "[narrator]", "[softly]", "[dramatic]", "[excited]",
    "[mysterious]", "[whisper]", "[gasp]", "[sigh]",
    "[fast]", "[pause]", "[curious]", "[surprised]"
]

def merge_mp3_chunks(chunk_files: List[str], output_path: str) -> bool:
    """Merge multiple MP3 chunk files into a single output file using FFmpeg or binary concat."""
    import shutil
    import subprocess
    if not chunk_files:
        return False

    abs_output = os.path.abspath(output_path)
    if len(chunk_files) == 1:
        shutil.copy(chunk_files[0], abs_output)
        print(f"✅ Single chunk narration saved -> {abs_output}")
        return True

    list_file = os.path.abspath("temp_ffmpeg_list.txt")
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for p in chunk_files:
                escaped_p = os.path.abspath(p).replace("\\", "/")
                f.write(f"file '{escaped_p}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            abs_output
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and os.path.exists(abs_output) and os.path.getsize(abs_output) > 1000:
            print(f"✅ Successfully merged {len(chunk_files)} MP3 chunks via FFmpeg -> {abs_output}")
            if os.path.exists(list_file):
                os.remove(list_file)
            return True
    except Exception as e:
        print(f"⚠️ FFmpeg MP3 concat notice: {e}")

    try:
        print("🎙️ Merging MP3 chunks via binary concatenation fallback...")
        with open(abs_output, "wb") as outfile:
            for p in chunk_files:
                with open(p, "rb") as infile:
                    outfile.write(infile.read())
        print(f"✅ Merged {len(chunk_files)} MP3 chunks -> {abs_output}")
        if os.path.exists(list_file):
            os.remove(list_file)
        return True
    except Exception as e:
        print(f"❌ Failed to merge MP3 chunks: {e}")
        if os.path.exists(list_file):
            os.remove(list_file)
        return False

FEMALE_VERBS_MAP = {
    'был': 'была', 'стал': 'стала', 'пошел': 'пошла', 'пришел': 'пришла', 'ушел': 'ушла',
    'решил': 'решила', 'подумал': 'подумала', 'заметил': 'заметила', 'понял': 'поняла',
    'хотел': 'хотела', 'сказал': 'сказала', 'начал': 'начала', 'остался': 'осталась',
    'наткнулся': 'наткнулась', 'пытался': 'пыталась', 'надеялся': 'надеялась',
    'почувствовал': 'почувствовала', 'вернулся': 'вернулась', 'увидел': 'увидела',
    'услышал': 'услышала', 'сделал': 'сделала', 'взял': 'взяла', 'сбежал': 'сбежала',
    'застрял': 'застряла', 'проснулся': 'проснулась', 'сдал': 'сдала', 'расцвел': 'расцвела',
    'побежал': 'побежала', 'купил': 'купила', 'открыл': 'открыла', 'закрыл': 'закрыла',
    'забыл': 'забыла', 'вспомнил': 'вспомнила', 'нашел': 'нашла', 'потерял': 'потеряла',
    'попросил': 'попросила', 'спросил': 'спросила', 'ответил': 'ответила', 'дал': 'дала',
    'шокирован': 'шокирована', 'расстроен': 'расстроена', 'удивлен': 'удивлена',
    'напуган': 'напугана', 'уверен': 'уверена', 'ошарашен': 'ошарашена',
    'разочарован': 'разочарована', 'обижен': 'обижена', 'поражен': 'поражена',
    'взбешен': 'взбешена', 'унижен': 'унижена', 'ошеломлен': 'ошеломлена'
}

def is_female_narrator(eng_title: str, eng_body: str) -> bool:
    """Detect if the English story is narrated by a female author."""
    full_eng = f"{eng_title} {eng_body}".lower()
    female_patterns = [
        r'\b\d{2}\s*f\b', r'\bfemale\b', r'\bmy husband\b', r'\bmy boyfriend\b',
        r'\bas a woman\b', r'\bas a girl\b', r'\bwhen i was pregnant\b', r'\bmy fiancé\b',
        r'\bi\s*[\(\[]?\s*\d{2}\s*f\b', r'\b(i|me|my)\s+.*?\b(woman|girl|mother|mom|wife|sister|daughter)\b'
    ]
    male_patterns = [
        r'\b\d{2}\s*m\b', r'\bmale\b', r'\bmy wife\b', r'\bmy girlfriend\b',
        r'\bas a man\b', r'\bas a guy\b', r'\bmy fiancée\b'
    ]
    female_score = sum(1 for p in female_patterns if re.search(p, full_eng))
    male_score = sum(1 for p in male_patterns if re.search(p, full_eng))
    return female_score > male_score

def fix_female_gender_endings(russian_text: str) -> str:
    """Post-process Russian translation to ensure consistent female verb endings for 1st-person narrator."""
    if not russian_text:
        return ""
    clauses = re.split(r'([,.;!?…\n]+)', russian_text)
    res = []
    for clause in clauses:
        if re.search(r'\b(я|мне|меня|мной|мною)\b', clause, re.IGNORECASE):
            def fix_word(match):
                word = match.group(0)
                w_low = word.lower()
                if w_low in FEMALE_VERBS_MAP:
                    mapped = FEMALE_VERBS_MAP[w_low]
                    return mapped.capitalize() if word[0].isupper() else mapped
                if w_low.endswith('лся'):
                    mapped = w_low[:-3] + 'лась'
                    return mapped.capitalize() if word[0].isupper() else mapped
                if re.search(r'(ел|ал|ил|ул|ол)$', w_low) and not re.search(r'(вышел|нашел|пришел|ушел|пошел|зашел|перешел|посол|козел|осел|стол|пол|угол|чехол|сокол|ствол|узел|футбол)', w_low):
                    mapped = w_low + 'а'
                    return mapped.capitalize() if word[0].isupper() else mapped
                return word

            clause = re.sub(r'\b[а-яА-ЯёЁ]+\b', fix_word, clause)
        res.append(clause)
    return ''.join(res)

def translate_to_russian(text: str, eng_context: str = "") -> str:
    """Translate English text to fluent Russian if not already in Russian."""
    if not text or not text.strip():
        return ""

    cyrillic_count = len(re.findall(r'[\u0400-\u04FF]', text))
    if cyrillic_count > len(text) * 0.25:
        return text.strip()

    try:
        import urllib.request
        import urllib.parse
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ru&dt=t&q=" + urllib.parse.quote(text)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            translated_chunks = []
            if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                for item in data[0]:
                    if item and isinstance(item, list) and len(item) > 0 and item[0]:
                        translated_chunks.append(item[0])
            res_text = "".join(translated_chunks).strip()
            if res_text:
                if is_female_narrator(eng_context or text, text):
                    res_text = fix_female_gender_endings(res_text)
                print(f"🌐 Translated to Russian: \"{res_text[:60]}...\"")
                return res_text
            return text
    except Exception as e:
        print(f"⚠️ Translation notice: {e}")
        return text

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


def tag_and_translate_story_with_gemini(title: str, body: str) -> str:
    """Use Gemini Flash API to translate English Reddit text to expressive, natural Russian and insert ElevenLabs v3 audio tags."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ GEMINI_API_KEY is missing in environment! Gemini translation & tagging skipped, using Google Translate fallback.")
        return ""

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        is_female = is_female_narrator(title, body)
        if is_female:
            gender_instruction = (
                "🚨 КРИТИЧЕСКИ ВАЖНОЕ ПРАВИЛО ГРАММАТИЧЕСКОГО РОДА:\n"
                "Автор истории — ЖЕНЩИНА (девушка). Весь рассказ от первого лица ('я') ДОЛЖЕН БЫТЬ СТРОГО В ЖЕНСКОМ РОДЕ!\n"
                "Используй исключительно женские окончания в прошедшем времени и причастиях:\n"
                "(я пошла, я подумала, я была, я осталась, я решила, я увидела, я была шокирована, я вернулась).\n"
                "СТРОЖАЙШЕ ЗАПРЕЩЕНО использовать мужской род (я пошел, подумал, был) или менять пол в течение истории!"
            )
        else:
            gender_instruction = (
                "🚨 КРИТИЧЕСКИ ВАЖНОЕ ПРАВИЛО ГРАММАТИЧЕСКОГО РОДА:\n"
                "Внимательно определи пол автора истории по контексту (мужчина или женщина) и соблюдай 100% ЕДИНЫЙ грамматический род от первого лица ('я') от первого до последнего слова!\n"
                "СТРОЖАЙШЕ ЗАПРЕЩЕНО путать пол или сменять мужской род на женский (или наоборот) в пределах одной истории!"
            )

        prompt = (
            "Ты признанный переводчик художественной литературы и режиссер дубляжа мирового уровня.\n"
            "Переведи данный пост с Reddit на живой, эмоциональный, богатый и естественный русский язык.\n\n"
            f"{gender_instruction}\n\n"
            "═════════════════════════════════════════════════════════════════════════\n"
            "ОФИЦИАЛЬНОЕ РУКОВОДСТВО ПО АУДИО-ТЕГАМ И ОЗВУЧКЕ ELEVENLABS V3:\n"
            "═════════════════════════════════════════════════════════════════════════\n"
            "⚠️ КРИТИЧЕСКИ ВАЖНО: Модель ElevenLabs v3 НЕ ПОДДЕРЖИВАЕТ SSML (<break>, <prosody>, <emphasis>).\n"
            "НИКОГДА НЕ ИСПОЛЬЗУЙ XML/HTML ТЕГИ! Заменяй все элементы режиссуры только на Натуральные Теги в квадратных скобках [tag] и знаки препинания:\n\n"
            "1. ТАБЛИЦА ЗАМЕНЫ SSML И РЕГУЛИРОВКИ ТЕМПА:\n"
            "   - Вместо <break time='1s'> ➔ используй теги [pauses], [pause] или многоточие '...'\n"
            "   - Вместо <prosody rate='slow'> ➔ используй [slowly] или [drawn out]\n"
            "   - Вместо <prosody rate='fast'> ➔ используй [rushed]\n"
            "   - Вместо <emphasis> ➔ используй [shouts] или ПИШИ ВАЖНЫЕ СЛОВА КАПСОМ (например: 'ИМЕННО ТАК', 'НИКОГДА')\n"
            "   - Вместо <prosody pitch='high'> ➔ используй [excited], [surprised], [awe]\n"
            "   - Вместо <prosody pitch='low'> ➔ используй [softly], [sorrowful], [whisper]\n\n"
            "2. КАТЕГОРИИ АУДИО-ТЕГОВ (вставляй в квадратных скобках [tag] перед фразами):\n"
            "   - Эмоциональный тон: [happy], [sad], [angry], [sorrowful], [dramatic], [excited], [tired], [nervous], [frustrated], [furious], [calm], [panicking], [cautiously], [dismissive], [cheeky], [awe], [booming], [worried], [upset]\n"
            "   - Подача и темп: [whisper], [shouts], [softly], [drawn out], [slowly], [rushed], [pauses], [flatly], [mumbles], [starting to speak], [beginning to speak], [interrupting], [overlapping]\n"
            "   - Человеческие реакции: [sigh], [gasp], [laughs], [giggles], [big laugh], [light chuckle], [clears throat], [snorts], [gulps], [yawns], [coughing]\n"
            "   - Акценты / Персонажи (в диалогах): [French accent], [British accent], [Australian accent], [pirate voice]\n"
            "   - Звуковые эффекты: [gunshot], [explosion], [clapping]\n\n"
            "3. КОМБИНИРОВАНИЕ И ПРЕПИНАНИЕ:\n"
            "   - Можно комбинировать несколько тегов подряд для глубокой подачи: [tired] [upset], [dramatic] [gasp], [coughing] [beginning to speak].\n"
            "   - Используй многоточия (...) для колеблющихся пауз, запятые для естественного дыхания и КАПС для акцентирования слов.\n\n"
            "ФОРМАТ ОТВЕТА: Верни ТОЛЬКО итоговый переведённый текст истории на русском языке с вкрапленными тегами [tag]. Без пояснений, без вводных слов и без markdown блоков.\n\n"
            f"Заголовок:\n{title}\n\nИстория:\n{body}"
        )

        for model_name in [
            "models/gemini-3.5-flash-lite",
            "models/gemini-3.5-flash",
            "models/gemini-3.1-flash-lite",
            "models/gemini-3-flash-preview",
            "models/gemini-flash-lite-latest"
        ]:
            try:
                print(f"🤖 Requesting Gemini 3.5 Flash translation & ElevenLabs tags from {model_name}...")
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )

                if resp and resp.text and len(resp.text.strip()) > 10:
                    clean_text = resp.text.strip().replace("```markdown", "").replace("```", "").strip()
                    print(f"✨ {model_name} successfully translated & tagged story with strict gender consistency!")
                    return clean_text
            except Exception as model_err:
                print(f"⚠️ {model_name} unavailable, trying next model: {model_err}")
                continue
    except Exception as e:
        print(f"⚠️ Gemini translation error: {e}")

    return ""

def format_text_with_elevenlabs_tags(title: str, body: str, translate_ru: bool = True) -> str:
    """Format title and body into expressive ElevenLabs tagged script via Gemini 3.5 Flash AI."""
    if translate_ru:
        gemini_result = tag_and_translate_story_with_gemini(title, body)
        if gemini_result:
            return gemini_result
            
        print("⚠️ Gemini translation unavailable! Using native text formatting.")

    rule_tagged = f"[narrator] [calm] {title}\n\n[narrator] {body}"
    if is_female_narrator(title, body):
        rule_tagged = fix_female_gender_endings(rule_tagged)
    return rule_tagged




    lines = []
    
    # Title Tagging
    clean_title = title.strip()
    if not clean_title.endswith(('.', '!', '?')):
        clean_title += '.'
    
    if '?' in clean_title:
        lines.append(f"[narrator] [curious] {clean_title}")
    else:
        lines.append(f"[narrator] [dramatic] {clean_title}")
    
    lines.append("")  # paragraph gap

    # Body Tagging
    if body:
        sentences = re.split(r'(?<=[.!?…])\s+', body.strip())
        tag_idx = 0
        
        for idx, s in enumerate(sentences):
            s = s.strip()
            if not s:
                continue

            if idx == 0:
                tag = "[softly]"
            elif '?' in s:
                tag = "[curious]"
            elif '!' in s:
                tag = "[gasp] [excited]" if (idx % 2 == 0) else "[dramatic]"
            elif '"' in s or "'" in s or "“" in s:
                tag = "[whisper]" if (idx % 3 == 0) else "[dramatic]"
            else:
                tags = ["[softly]", "[mysterious]", "[fast]", "[sigh]", "[dramatic]", "[pause]"]
                tag = tags[tag_idx % len(tags)]
                tag_idx += 1

            lines.append(f"{tag} {s}")

    return "\n".join(lines)

def export_story_for_userscript(story: Dict[str, Any], output_txt_path: str = "formatted_story_elevenlabs.txt") -> str:
    """Export formatted story text with ElevenLabs tags for Tampermonkey Assistant."""
    abs_out = os.path.abspath(output_txt_path)
    title = story.get("title", "")
    body = story.get("body", "")

    formatted_script = format_text_with_elevenlabs_tags(title, body)

    with open(abs_out, "w", encoding="utf-8") as f:
        f.write(formatted_script)

    print(f"✅ Exported ElevenLabs Tagged Story -> {abs_out}")
    return abs_out

def process_story_audio(story: Dict[str, Any], output_path: str = "narration.mp3", voice_name: str = "Den", wait_for_user: bool = False) -> str:
    """Prepare tagged story text, start local API server, and resolve audio narration file."""
    from story_api_server import start_story_api_server, set_current_story

    abs_audio = os.path.abspath(output_path)
    title = story.get("title", "")
    body = story.get("body", "")
    formatted_text = format_text_with_elevenlabs_tags(title, body)

    # Export TXT file as fallback
    txt_path = export_story_for_userscript(story, output_txt_path="formatted_story_elevenlabs.txt")

    # Start local API server on 127.0.0.1:5000 and serve story to Tampermonkey
    start_story_api_server(host="127.0.0.1", port=5000)
    set_current_story(story, formatted_text=formatted_text)

    print("\n==================================================")
    print("🎙️ ELEVENLABS ASSISTANT USER WORKFLOW")
    print("📡 Story published to Local API Server: http://127.0.0.1:5000/api/story")
    print("👉 Open ElevenLabs in browser — Tampermonkey v2.4 will AUTO-FETCH this story!")
    print(f"   Save/place the downloaded audio file as: {abs_audio}")
    print("==================================================\n")

    if os.path.exists(abs_audio) and os.path.getsize(abs_audio) > 5000:
        print(f"✅ Found audio narration file ({os.path.getsize(abs_audio)} bytes) -> {abs_audio}")
        return abs_audio

    if wait_for_user:
        print(f"⏳ Waiting for audio file '{os.path.basename(abs_audio)}' to be placed in project directory...")
        while True:
            if os.path.exists(abs_audio) and os.path.getsize(abs_audio) > 5000:
                print(f"🎉 Audio file detected ({os.path.getsize(abs_audio)} bytes)! Resuming pipeline...")
                return abs_audio
            time.sleep(2)

    return abs_audio

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Format story for ElevenLabs Assistant Tampermonkey userscript")
    parser.add_argument("--json", type=str, default="story.json", help="Input story JSON file")
    parser.add_argument("--out-txt", type=str, default="formatted_story_elevenlabs.txt", help="Output tagged TXT file")
    args = parser.parse_args()

    if os.path.exists(args.json):
        with open(args.json, "r", encoding="utf-8") as f:
            story_data = json.load(f)
    else:
        story_data = {
            "title": "What is the most unsettling secret you discovered by accident?",
            "body": "A few years ago, while cleaning out my grandfather's old attic, I stumbled across a small wooden box locked with a rusty padlock. When I got it open, I found hand-drawn maps with red X marks."
        }

    export_story_for_userscript(story_data, output_txt_path=args.out_txt)


