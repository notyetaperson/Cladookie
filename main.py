"""Turn screenshots into Caldruki-style mp4s.

One beat is one picture, a short caption, a reaction face, and a sting.
A Short plays 2 to 4 beats in a row and lasts 15 to 25 seconds.
A wide clip is one beat. A compilation stitches clips so the emotion
changes, up to about eight minutes.

    python main.py
"""

import atexit
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
REACTABLES = ROOT / 'assets' / 'Reactables'
CALDRUKI = ROOT / 'assets' / 'Caldruki'
CALDRUKI_FEEDS = (
    'https://www.reddit.com/r/Caldruki/new/.rss?limit=100',
    'https://www.reddit.com/r/Caldruki/top/.rss?limit=100&t=all',
)
FEED_PAGES = 3
USER_AGENTS = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15',
)
IMAGE_URL = re.compile(
    r'https://(?:i\.redd\.it|i\.imgur\.com)/[A-Za-z0-9]+\.(?:jpeg|jpg|png|webp|gif)',
    re.IGNORECASE,
)
PREVIEW_URL = re.compile(
    r'https://preview\.redd\.it/([A-Za-z0-9]+)\.(jpeg|jpg|png|webp|gif)',
    re.IGNORECASE,
)
VIDEO_URL = re.compile(r'https://v\.redd\.it/([A-Za-z0-9]+)')
VIDEO_EXTS = {'.mp4', '.webm', '.mov', '.mkv'}
VIDEO_MAX = 15.0
VIDEO_CHANCE = 0.65
FACES = ROOT / 'assets' / 'images'
SOUNDS = ROOT / 'assets' / 'sounds'
MUSIC = ROOT / 'assets' / 'BAD PIGGIES DRILL.mp3'
MUSIC_VOLUME = 0.2
VISION = ROOT / 'assets' / 'models' / 'vision' / 'Qwen3VL-8B-Instruct-Q4_K_M.gguf'
MMPROJ = ROOT / 'assets' / 'models' / 'vision' / 'mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf'
TEXT = ROOT / 'assets' / 'models' / 'text' / 'Qwen3.5-4B-Q4_0.gguf'
TTS = ROOT / 'assets' / 'models' / 'tts' / 'Qwen3-TTS-12Hz-1.7B-Base-Q4_K_M.gguf'
TTS_MMPROJ = ROOT / 'assets' / 'models' / 'tts' / 'mmproj-Qwen3-TTS-12Hz-1.7B-Base-Q8_0.gguf'
TTS_URL = (
    'https://huggingface.co/ggml-org/Qwen3-TTS-12Hz-1.7B-Base-GGUF/resolve/main/'
    'Qwen3-TTS-12Hz-1.7B-Base-Q4_K_M.gguf'
)
TTS_MMPROJ_URL = (
    'https://huggingface.co/ggml-org/Qwen3-TTS-12Hz-1.7B-Base-GGUF/resolve/main/'
    'mmproj-Qwen3-TTS-12Hz-1.7B-Base-Q8_0.gguf'
)
VISION_URL = (
    'https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF/resolve/main/'
    'Qwen3VL-8B-Instruct-Q4_K_M.gguf'
)
MMPROJ_URL = (
    'https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF/resolve/main/'
    'mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf'
)
OUTPUT = ROOT / 'output'
USED = ROOT / 'used.txt'
MAX_USES = 3
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}
EMOTIONS = (
    'Anger',
    'Confusion',
    'Cringe',
    'Disappointment',
    'Disgust',
    'Laughing',
    'Shock',
    'Silence',
    'Smug',
    'Unhinged',
)
DEFAULT_STING = {
    'Anger': 'SHUT UP',
    'Confusion': 'Eye or Rah',
    'Cringe': 'AHH ITS SO UNFUNYYYY',
    'Disappointment': 'No',
    'Disgust': 'Fart',
    'Laughing': 'HEHEHE',
    'Shock': 'WTH',
    'Silence': None,
    'Smug': 'Correct',
    'Unhinged': 'Lobotomy',
}
ASPECTS = {
    'short': {
        'w': 1080,
        'h': 1920,
        'font': 46,
        'caption_y': 168,
        'shot_w': 980,
        'shot_h': 1120,
        'shot_y': 460,
        'face_w': 320,
        'face_m': 48,
    },
    'wide': {
        'w': 1920,
        'h': 1080,
        'font': 40,
        'caption_y': 36,
        'shot_w': 1200,
        'shot_h': 760,
        'shot_y': 190,
        'face_w': 280,
        'face_m': 36,
    },
}
THREADS = '8'
COMPILE_SECONDS = 8 * 60
SHORT_MIN = 15.0
SHORT_MAX = 25.0
NONE_STINGS = {'', 'none', 'null', 'silence', 'no sting', 'nothing'}
TITLE_EMOJI = ('😭', '💀', '🌹', '🥷', '✌️', '🗣️')


SKY = (118, 186, 230)
HEAD = (186, 220, 248)
LINE = (80, 150, 210)
DIM = (140, 170, 196)
INK = (220, 234, 246)
OK = (76, 175, 80)
WARN = (255, 167, 38)
ERROR = (239, 83, 80)


def color(text, rgb, dim=False, bold=False):
    if not text or not sys.stdout.isatty():
        return text
    red, green, blue = rgb
    weight = '1;' if bold else '2;' if dim else ''
    return f'\033[{weight}38;2;{red};{green};{blue}m{text}\033[0m'


def mix(start, end, amount):
    return int(start + (end - start) * amount)


def rule():
    width = max(24, min(72, shutil.get_terminal_size((80, 24)).columns - 1))
    print(color('─' * width, LINE), flush=True)


def box(heading, lines):
    width = max(36, min(72, shutil.get_terminal_size((80, 24)).columns))
    inner = width - 2
    label = f' {heading} '
    if len(label) > inner:
        label = label[:inner]
    print(color('┌' + label + '─' * (inner - len(label)) + '┐', LINE), flush=True)
    for line in lines:
        shown = line[:inner - 2]
        gap = ' ' * (inner - 2 - len(shown))
        print(color('│ ', LINE) + color(shown, INK) + gap + color(' │', LINE), flush=True)
    print(color('└' + '─' * inner + '┘', LINE), flush=True)


def title(name):
    print()
    print(f'  {color(name, HEAD, bold=True)}', flush=True)


def step(label, detail=''):
    mark = color(f'{label:<6}', SKY)
    body = color(detail, INK)
    print(f'  {color("●", LINE)} {mark}  {body}', flush=True)


def bar_parts(fraction):
    width = max(12, min(28, shutil.get_terminal_size((80, 24)).columns - 14))
    fraction = max(0.0, min(1.0, fraction))
    filled = int(width * fraction + 0.5)
    if fraction > 0 and filled == 0:
        filled = 1
    if fraction < 1 and filled == width:
        filled = width - 1
    return ('█' * filled) + ('─' * (width - filled)), f'{round(fraction * 100):3d}%'


def paint_bar(fraction):
    if not sys.stdout.isatty():
        return False
    bar, pct = bar_parts(fraction)
    visible = f'  {bar}  {pct}'
    cols = shutil.get_terminal_size((80, 24)).columns
    pad = ' ' * max(0, min(cols - 1, 48) - len(visible))
    sys.stdout.write(f'\r  {color(bar, SKY)}  {color(pct, HEAD)}{pad}')
    sys.stdout.flush()
    return True


def info(text):
    print(f'  {color(text, INK)}', flush=True)


def note(text):
    print(f'            {color(text, DIM, dim=True)}', flush=True)


def warn(text):
    print(f'  {color(text, WARN)}', flush=True)


def show_path(path):
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def done(path, notes=None):
    if isinstance(notes, str):
        notes = [notes] if notes else []
    lines = [show_path(path)]
    lines.extend(notes or [])
    print()
    box('Ready', lines)


def result_notes(meta, path):
    notes = []
    meta = meta or {}
    seconds = meta.get('duration') or media_duration(path)
    beats = meta.get('beats')
    if seconds and beats:
        word = 'picture' if beats == 1 else 'pictures'
        notes.append(f'{float(seconds):.0f} seconds, {beats} {word}')
    elif seconds:
        notes.append(f'{float(seconds):.0f} seconds')
    lines = [line for line in (meta.get('lines') or []) if line]
    if not lines and meta.get('line'):
        lines = [meta['line']]
    notes.extend(lines)
    return notes


def report_error(error):
    if isinstance(error, subprocess.TimeoutExpired):
        command = error.cmd[0] if error.cmd else 'model'
        summary = f'{Path(str(command)).name} took too long and was stopped.'
        detail = ''
    else:
        lines = [line.strip() for line in str(error).splitlines() if line.strip()]
        summary = lines[0] if lines else 'Something went wrong while making the video.'
        detail = lines[-1][:180] if len(lines) > 1 and lines[-1] != lines[0] else ''
    print()
    print(f'  {color(summary, ERROR)}', flush=True)
    if detail:
        print(f'  {color(detail, DIM, dim=True)}', flush=True)
    print(f'  {color("Run the same command again. Finished steps are kept.", DIM, dim=True)}', flush=True)
    raise SystemExit(1)


def tool(name):
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f'{name} is not on PATH.')
    return path


def run(cmd, timeout, cwd=None, expect=None):
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    started = time.monotonic()
    deadline = started + timeout
    drawn = False
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                proc.kill()
                proc.communicate()
                raise subprocess.TimeoutExpired(cmd, timeout)
            wait = min(0.4, remaining) if expect else remaining
            try:
                stdout, stderr = proc.communicate(timeout=wait)
                break
            except subprocess.TimeoutExpired:
                if expect:
                    elapsed = time.monotonic() - started
                    drawn = paint_bar(min(0.95, elapsed / expect)) or drawn
    except KeyboardInterrupt:
        proc.kill()
        proc.communicate()
        if drawn:
            sys.stdout.write('\n')
            sys.stdout.flush()
        raise
    if drawn:
        paint_bar(1)
        sys.stdout.write('\n')
        sys.stdout.flush()
    text = f'{stdout or ""}\n{stderr or ""}'
    if proc.returncode != 0 or 'Failed to initialize samplers' in text:
        tail = text.strip()[-2000:]
        raise RuntimeError(f'{Path(cmd[0]).name} failed ({proc.returncode})\n{tail}')
    return text


def publish(source, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, dest)
    return dest


def discard(path):
    path = Path(path)
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        pass


def clear_idle_work():
    temp = Path(tempfile.gettempdir())
    for path in temp.glob('cladookie-*'):
        discard(path)
    discard(OUTPUT / 'work')
    for root in (OUTPUT, CALDRUKI):
        if not root.exists():
            continue
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            if path.name.endswith('.part'):
                discard(path)
            elif path.suffix.lower() in VIDEO_EXTS and media_duration(path) <= 0:
                discard(path)


def extract_json(text):
    start = text.find('{')
    while start >= 0:
        depth = 0
        for index, char in enumerate(text[start:], start):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:index + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find('{', start + 1)
    return None


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sound_library():
    library = {}
    for path in sorted(SOUNDS.glob('*.ogg')):
        library[path.stem] = path
    if not library:
        raise SystemExit(f'No sounds in {SOUNDS}')
    return library


def ensure_vision():
    needed = (
        (VISION, VISION_URL, 4_800_000_000, 'Qwen3-VL 8B judge (about 5 GB)'),
        (MMPROJ, MMPROJ_URL, 700_000_000, 'Qwen3-VL 8B vision encoder (about 750 MB)'),
    )
    for path, url, minimum, label in needed:
        if path.exists() and path.stat().st_size > minimum:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        info(f'Downloading {label}')
        subprocess.run(
            ['curl.exe', '-L', '--fail', '--retry', '3', '-C', '-', '-o', str(path), url],
            check=True,
        )


def ensure_tts():
    needed = (
        (TTS, TTS_URL, 1_000_000_000, 'Qwen3-TTS voice model (about 1 GB)'),
        (TTS_MMPROJ, TTS_MMPROJ_URL, 400_000_000, 'Qwen3-TTS audio decoder (about 430 MB)'),
    )
    for path, url, minimum, label in needed:
        if path.exists() and path.stat().st_size > minimum:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        info(f'Downloading {label}')
        subprocess.run(
            ['curl.exe', '-L', '--fail', '--retry', '3', '-C', '-', '-o', str(path), url],
            check=True,
        )


def visible_answer(raw):
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('0.') or stripped.startswith('ggml_') or stripped.startswith('<|im_start|>'):
            continue
        lines.append(stripped)
    return '\n'.join(lines).strip()


def screen_read(image):
    prompt = (
        'Read this screenshot. Reply with one JSON object and nothing else. '
        'on_screen is the main caption, post, or message, quoted as written. '
        'also is one or two nearby replies or extra lines that change the meaning, quoted as written. '
        'Leave also empty when the screenshot is only one line. '
        'who is the speaker of the main line, or unknown. '
        'absurd is the strange part in a few words. '
        'keep is yes for a photo, drawing, game, face, meme, or clip, even when a short caption is written on it. '
        'keep is no only for a wall of writing: an article, several paragraphs, a comment thread, or a page of chat. '
        'Skip buttons, timestamps, and like counts. '
        'Do not invent text that is not in the image. '
        'Example: {"on_screen":"...","also":"...","who":"...","absurd":"...","keep":"yes"}'
    )
    cmd = [
        tool('llama-mtmd-cli'),
        '-m', str(VISION),
        '--mmproj', str(MMPROJ),
        '--image', str(image),
        '-p', prompt,
        '-c', '4096',
        '-ngl', '0',
        '-t', THREADS,
        '--temp', '0.2',
        '--top-k', '20',
        '--top-p', '0.9',
        '-n', '420',
        '--no-warmup',
        '--no-mmproj-offload',
        '--mmproj-device', 'none',
    ]
    raw = run(cmd, timeout=600, expect=120)
    parsed = extract_json(raw) or {}
    on_screen = str(parsed.get('on_screen') or '').strip()
    if not on_screen:
        on_screen = visible_answer(raw)
    if not on_screen:
        raise RuntimeError(f'Vision model did not read the screenshot.\n{raw[-1500:]}')
    also = ' '.join(str(parsed.get('also') or '').split())
    read = {
        'on_screen': on_screen[:800],
        'also': also[:360],
        'who': str(parsed.get('who') or 'unknown').strip()[:200],
        'absurd': str(parsed.get('absurd') or '').strip()[:400],
        'keep': str(parsed.get('keep') or '').strip().casefold(),
    }
    return read


def too_much_text(read):
    if read.get('keep') in {'no', 'n', 'false', 'skip', 'many', 'lots', 'long', 'wall', 'heavy'}:
        return True
    quoted = ' '.join(f'{read.get("on_screen", "")} {read.get("also", "")}'.split())
    return len(quoted) > 700


def canon_emotion(value):
    key = str(value or '').strip().casefold()
    for name in EMOTIONS:
        if name.casefold() == key:
            return name
    return 'Unhinged'


def canon_sting(value, library):
    key = str(value or '').strip().casefold()
    if key in NONE_STINGS:
        return None
    for stem in library:
        if stem.casefold() == key:
            return stem
    return False


def react(read, library, theme='', prior_lines=None, emotion=None):
    theme = ' '.join(str(theme or '').split())
    theme_block = ''
    if theme:
        theme_block = (
            f'Theme: {theme}\n'
            'The whole video is about that theme. Write the line so this screenshot serves it. '
            'Do not announce the theme by name.\n'
        )
        earlier = [line for line in (prior_lines or []) if line]
        if earlier:
            joined = '\n'.join(f'- {line}' for line in earlier[-3:])
            theme_block += f'Earlier lines in this video:\n{joined}\nDo not repeat them.\n'
    prompt = (
        'You write the caption for a Caldruki short: a screenshot out of context, '
        'one deadpan line and a reaction face. The sound is chosen separately.\n'
        'The line is one or two short clauses, under 90 characters. '
        'Say the absurd part in plain words. Do not explain the joke. '
        'You may start the line with >>. Silence uses an empty line.\n'
        f'{theme_block}'
        f'The reaction face is {emotion}. Write the line for that reaction.\n'
        f'On screen: {read["on_screen"]}\n'
        + (f'Also on screen: {read["also"]}\n' if read.get('also') else '')
        + f'Who: {read["who"]}\n'
        f'Absurd bit: {read["absurd"]}\n'
        'Reply as JSON with line.'
    )
    cmd = [
        tool('llama-cli'),
        '-m', str(TEXT),
        '--jinja',
        '--reasoning', 'off',
        '-c', '4096',
        '-ngl', '0',
        '-t', THREADS,
        '--temp', '0.3',
        '--top-k', '20',
        '--top-p', '0.8',
        '-n', '200',
        '--no-display-prompt',
        '--single-turn',
        '--simple-io',
        '--no-warmup',
        '--log-disable',
        '-p', prompt,
    ]
    raw = run(cmd, timeout=300, expect=40)
    if extract_json(raw) is None:
        raise RuntimeError(f'Text model did not return JSON.\n{raw[-1500:]}')
    parsed = extract_json(raw) or {}
    emotion = emotion or canon_emotion(parsed.get('emotion'))
    line = ' '.join(str(parsed.get('line') or '').split())
    if len(line) > 140:
        line = line[:137].rstrip() + '...'
    return {'emotion': emotion, 'line': line, 'sting': None, 'theme': theme}


def complete_text(prompt, tokens):
    cmd = [
        tool('llama-cli'),
        '-m', str(TEXT),
        '--jinja',
        '--reasoning', 'off',
        '-c', '4096',
        '-ngl', '0',
        '-t', THREADS,
        '--temp', '0.3',
        '--top-k', '20',
        '--top-p', '0.8',
        '-n', str(tokens),
        '--no-display-prompt',
        '--single-turn',
        '--simple-io',
        '--no-warmup',
        '--log-disable',
        '-p', prompt,
    ]
    return run(cmd, timeout=300, expect=60)


def plain_title(text):
    kept = []
    for char in str(text or ''):
        if char in '<>:"/\\|?*' or ord(char) < 32:
            continue
        if char.isalnum() or char in " '-":
            kept.append(char)
    words = ' '.join(''.join(kept).split()).strip(' .')
    return words[:40]


def clip_title(readout):
    prompt = (
        'Turn this readout into a short file title. '
        'A few plain words, under 40 characters. '
        'No emoji, no hashtags, no quotes.\n'
        'Reply as JSON with title.\n'
        f'Readout: {str(readout)[:400]}'
    )
    words = ''
    try:
        parsed = extract_json(complete_text(prompt, 80)) or {}
        words = plain_title(parsed.get('title'))
    except RuntimeError:
        words = ''
    if not words:
        words = plain_title(readout) or 'clip'
    marks = ' '.join(random.sample(TITLE_EMOJI, 2))
    return f'{words} {marks}'


def titled_dest(folder, title):
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f'{title}.mp4'
    number = 2
    while dest.exists():
        dest = folder / f'{title} {number}.mp4'
        number += 1
    return dest


def readout_for_title(beats):
    videos = [beat for beat in beats if is_video(beat['image']) and beat.get('readout')]
    pool = videos or [beat for beat in beats if beat.get('readout')]
    if not pool:
        return ''
    return random.choice(pool)['readout']


_face_decks = {}
_sting_deck = {'deck': [], 'last': None}
_emotion_deck = {'deck': [], 'last': None}


def deal(state, items):
    pool = list(items)
    if not pool:
        return None
    by_key = {}
    for item in pool:
        by_key[item if isinstance(item, str) else item.name] = item
    deck = [key for key in state.get('deck') or [] if key in by_key]
    last = state.get('last') if state.get('last') in by_key else None
    if not deck:
        deck = list(by_key)
        random.shuffle(deck)
        if last is not None and len(deck) > 1 and deck[-1] == last:
            swap = random.randrange(len(deck) - 1)
            deck[-1], deck[swap] = deck[swap], deck[-1]
    key = deck.pop()
    state['deck'] = deck
    state['last'] = key
    return by_key[key]


def pick_sting(library):
    return deal(_sting_deck, list(library))


def pick_emotion():
    return deal(_emotion_deck, EMOTIONS)


def pick_face(stills):
    folder = str(stills[0].parent)
    state = _face_decks.setdefault(folder, {'deck': [], 'last': None})
    return deal(state, stills)


def cast(beat, library):
    folder = FACES / beat['emotion']
    stills = [path for path in folder.iterdir() if path.suffix.lower() in IMAGE_EXTS] if folder.is_dir() else []
    if not stills:
        raise RuntimeError(f'No reaction stills in {folder}')
    face = pick_face(stills)
    sting_name = beat.get('sting')
    sting = library.get(sting_name) if sting_name else None
    choice = {
        'emotion': beat['emotion'],
        'line': beat['line'],
        'sting': sting_name,
        'face': str(face),
        'sting_file': str(sting) if sting else None,
    }
    return choice


def spoken_line(line):
    text = line.strip()
    if text.startswith('>>'):
        text = text[2:].strip()
    return text


def speak(line, dest):
    text = spoken_line(line)
    if not text:
        return None
    cmd = [
        tool('llama-tts'),
        '-m', str(TTS),
        '--mmproj', str(TTS_MMPROJ),
        '--no-mmproj-offload',
        '--mmproj-device', 'none',
        '-p', text,
        '-o', str(dest),
        '-ngl', '0',
        '-t', THREADS,
        '--tts-lang', 'en',
    ]
    try:
        run(cmd, timeout=180, expect=60)
    except RuntimeError as error:
        dest.unlink(missing_ok=True)
        reason = ''
        for line in str(error).splitlines():
            if ' E ' in line or line.lower().startswith('error'):
                reason = line.split(' E ', 1)[-1].strip()
        warn(reason or 'Voice unavailable. The caption and sting stay.')
        return None
    if not dest.exists() or dest.stat().st_size < 100:
        dest.unlink(missing_ok=True)
        warn('Voice unavailable. The caption and sting stay.')
        return None
    return dest


def media_duration(path):
    if path is None or not Path(path).exists():
        return 0.0
    proc = subprocess.run(
        [
            tool('ffprobe'),
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'csv=p=0',
            str(path),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    try:
        return max(0.0, float(proc.stdout.strip()))
    except ValueError:
        return 0.0


def wrap_caption(line, width=34):
    text = ' '.join(line.split())
    if text and not text.startswith('>>'):
        text = '>> ' + text
    if not text:
        return ''
    rows = []
    current = ''
    for word in text.split():
        trial = word if not current else f'{current} {word}'
        if len(trial) <= width or not current:
            current = trial
        else:
            rows.append(current)
            current = word
    if current:
        rows.append(current)
    return '\n'.join(rows[:3])


def is_video(path):
    return Path(path).suffix.lower() in VIDEO_EXTS


def has_audio(path):
    proc = subprocess.run(
        [
            tool('ffprobe'), '-v', 'error', '-select_streams', 'a',
            '-show_entries', 'stream=index', '-of', 'csv=p=0', str(path),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    return bool(proc.stdout.strip())


def merge_spans(spans, limit):
    clipped = []
    for start, end in spans:
        start = max(0.0, min(limit, start))
        end = max(0.0, min(limit, end))
        if end - start >= 0.05:
            clipped.append((start, end))
    clipped.sort()
    merged = []
    for start, end in clipped:
        if merged and start <= merged[-1][1] + 0.02:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def other_audio_spans(voice, sting, sting_at, clip, duration):
    spans = []
    if voice is not None:
        spans.append((0.0, media_duration(voice)))
    if clip is not None and has_audio(clip):
        spans.append((0.0, min(media_duration(clip), max(0.0, sting_at))))
    if sting is not None:
        start = max(0.0, sting_at)
        spans.append((start, start + media_duration(sting)))
    return merge_spans(spans, duration)


def music_gain(spans):
    if not spans:
        return f'volume={MUSIC_VOLUME}'
    checks = '+'.join(f'between(t\\,{start:.3f}\\,{end:.3f})' for start, end in spans)
    return f"volume='{MUSIC_VOLUME}*if(gte({checks}\\,1)\\,0.7\\,1)':eval=frame"


def render_audio(voice, sting, duration, dest, sting_at, clip=None, music_at=0.0):
    ffmpeg = tool('ffmpeg')
    length = f'{duration:.3f}'
    delay_ms = max(0, int(round(sting_at * 1000)))
    shape = 'aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo'
    # Pitch up and shift the formants so the read sounds lighter and sillier. Tempo stays 1, so the line still ends on time.
    silly = 'rubberband=pitch=1.35:formant=shifted'
    sources = []
    if voice is not None:
        sources.append(('voice', voice))
    if clip is not None and has_audio(clip):
        sources.append(('clip', clip))
    if sting is not None:
        sources.append(('sting', sting))
    if MUSIC.exists():
        sources.append(('music', MUSIC))
    if not sources:
        run([
            ffmpeg, '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
            '-t', length, str(dest),
        ], timeout=60)
        return dest
    cmd = [ffmpeg, '-y']
    filters = []
    labels = []
    for index, (kind, path) in enumerate(sources):
        if kind == 'music':
            cmd += ['-stream_loop', '-1', '-i', str(path)]
        else:
            cmd += ['-i', str(path)]
        if kind == 'voice':
            filters.append(f'[{index}:a]{shape},{silly},volume=2.5,apad,atrim=0:{length},asetpts=PTS-STARTPTS[voice]')
        elif kind == 'clip':
            filters.append(
                f'[{index}:a]{shape},atrim=0:{sting_at:.3f},apad,atrim=0:{length},asetpts=PTS-STARTPTS[clip]'
            )
        elif kind == 'music':
            start = max(0.0, music_at)
            gain = music_gain(other_audio_spans(voice, sting, sting_at, clip, duration))
            filters.append(
                f'[{index}:a]{shape},atrim={start:.3f}:{start + duration:.3f},asetpts=PTS-STARTPTS,'
                f'{gain},apad,atrim=0:{length}[music]'
            )
        else:
            filters.append(
                f'[{index}:a]{shape},adelay={delay_ms}|{delay_ms},apad,atrim=0:{length},asetpts=PTS-STARTPTS[sting]'
            )
        labels.append(f'[{kind}]')
    if len(labels) > 1:
        filters.append(
            f'{"".join(labels)}amix=inputs={len(labels)}:duration=first:dropout_transition=0:normalize=0[a]'
        )
        out_label = '[a]'
    else:
        out_label = labels[0]
    cmd += ['-filter_complex', ';'.join(filters), '-map', out_label, '-t', length, str(dest)]
    run(cmd, timeout=60)
    return dest


def font_file():
    for name in ('arial.ttf', 'segoeui.ttf', 'calibri.ttf'):
        path = Path('C:/Windows/Fonts') / name
        if path.exists():
            return path
    raise SystemExit('No usable font in C:/Windows/Fonts')


def compose(image, choice, voice, duration, reveal, aspect, work, dest, music_at=0.0):
    layout = ASPECTS[aspect]
    caption = wrap_caption(choice['line'])
    (work / 'caption.txt').write_text(caption, encoding='utf-8')
    sting = Path(choice['sting_file']) if choice.get('sting_file') else None
    shot = Path(image)
    clip = shot if is_video(shot) else None
    audio = render_audio(voice, sting, duration, work / 'mix.wav', reveal, clip, music_at)
    face = Path(choice['face'])
    ffmpeg = tool('ffmpeg')
    shutil.copyfile(font_file(), work / 'font.ttf')
    width = layout['w']
    height = layout['h']
    fit = (
        f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1'
    )
    shot_fit = fit if clip is None else f'{fit},tpad=stop_mode=clone:stop=-1,setpts=PTS-STARTPTS'
    graph = (
        f"[1:v]{shot_fit}[shot];"
        f"[2:v]{fit}[face];"
        f"[0:v][shot]overlay=0:0:format=auto[mid];"
        f"[mid][face]overlay=0:0:enable='gte(t\\,{reveal:.3f})':format=auto[laid];"
    )
    if caption:
        previous = 'laid'
        line_h = layout['font'] + 12
        for index, line in enumerate(caption.split('\n')):
            name = f'line{index}.txt'
            (work / name).write_text(line, encoding='utf-8')
            current = f'cap{index}'
            y = layout['caption_y'] + index * line_h
            graph += (
                f"[{previous}]drawtext=fontfile=font.ttf:textfile={name}:expansion=none:fontcolor=white:"
                f"fontsize={layout['font']}:borderw=3:bordercolor=black:"
                f"x=(w-text_w)/2:y={y}[{current}];"
            )
            previous = current
        graph += f"[{previous}]format=yuv420p[v]"
    else:
        graph += '[laid]format=yuv420p[v]'
    length = f'{duration:.3f}'
    cmd = [
        ffmpeg, '-y',
        '-f', 'lavfi', '-i', f"color=c=black:s={layout['w']}x{layout['h']}:r=30:d={length}",
        *(['-i', str(shot.resolve())] if clip is not None else ['-loop', '1', '-i', str(shot.resolve())]),
        '-loop', '1', '-i', str(face.resolve()),
        '-i', str(Path(audio).resolve()),
        '-filter_complex', graph,
        '-map', '[v]', '-map', '3:a',
        '-t', length,
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '160k',
        '-movflags', '+faststart',
        'out.mp4',
    ]
    finished = work / 'out.mp4'
    run(cmd, timeout=180, cwd=work, expect=max(8.0, float(duration)))
    if not finished.exists() or media_duration(finished) <= 0:
        finished.unlink(missing_ok=True)
        raise RuntimeError('The video did not finish.')
    publish(finished, dest)
    return dest


def reactable_key(path):
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def load_used():
    counts = {}
    if not USED.exists():
        return counts
    for line in USED.read_text(encoding='utf-8').splitlines():
        key = line.strip()
        if not key or key.startswith('#'):
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def mark_used(path):
    key = reactable_key(path)
    with USED.open('a', encoding='utf-8') as handle:
        if USED.stat().st_size == 0:
            handle.write('# One line each time a reactable is rendered. Stopped after 3.\n')
        handle.write(key + '\n')


def safe_stem(path):
    cleaned = ''.join(char if char.isalnum() or char in '-_' else '_' for char in path.stem)
    cleaned = cleaned.strip('_')
    return (cleaned[:80] or 'clip')


def random_user_agent():
    return random.choice(USER_AGENTS)


def fetch_url(url, dest, accept, attempts=3):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + '.part')
    for attempt in range(attempts):
        part.unlink(missing_ok=True)
        proc = subprocess.run(
            [
                tool('curl'), '-sS', '-L', '--fail', '--max-time', '30',
                '-A', random_user_agent(),
                '-H', f'Accept: {accept}',
                '-o', str(part),
                url,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        if proc.returncode == 0 and part.exists() and part.stat().st_size > 0:
            os.replace(part, dest)
            return True
        if attempt + 1 < attempts:
            time.sleep(1.5)
    part.unlink(missing_ok=True)
    return False


def looks_like_image(path):
    data = path.read_bytes()[:16]
    if data.startswith(b'\xff\xd8') or data.startswith(b'\x89PNG') or data.startswith(b'GIF8'):
        return True
    return len(data) >= 12 and data.startswith(b'RIFF') and data[8:12] == b'WEBP'


def clock_seconds(value):
    match = re.fullmatch(r'PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?', value or '')
    if match is None or not any(match.groups()):
        return None
    hours, minutes, seconds = (float(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def feed_page(url, listing):
    atom = '{http://www.w3.org/2005/Atom}'
    if not fetch_url(url, listing, 'application/atom+xml', attempts=1):
        return [], ''
    text = listing.read_text(encoding='utf-8', errors='replace')
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return [], ''
    found = []
    last = ''
    for entry in root.findall(f'{atom}entry'):
        entry_id = entry.find(f'{atom}id')
        content = entry.find(f'{atom}content')
        blob = html.unescape(content.text or '') if content is not None and content.text else ''
        if entry_id is not None and entry_id.text:
            match = re.search(r't3_[A-Za-z0-9]+', entry_id.text)
            if match:
                last = match.group(0)
        found.append(blob)
    return found, last


def add_post(posts, seen, kind, value):
    if value in seen:
        return
    seen.add(value)
    posts.append((kind, value))


def posts_in(blob, posts, seen):
    video_ids = VIDEO_URL.findall(blob)
    if video_ids:
        for video_id in video_ids:
            add_post(posts, seen, 'video', video_id)
        return
    images = IMAGE_URL.findall(blob)
    if not images:
        images = [f'https://i.redd.it/{name}.{ext}' for name, ext in PREVIEW_URL.findall(blob)]
    for url in images:
        add_post(posts, seen, 'image', url)


def post_path(kind, value):
    if kind == 'video':
        return CALDRUKI / f'{value}.mp4'
    name = Path(urlparse(value).path).name
    if Path(name).suffix.lower() not in IMAGE_EXTS:
        return None
    return CALDRUKI / name


def still_allowed(path, counts, again):
    uses = counts.get(reactable_key(path), 0)
    return uses < MAX_USES and not (uses and not again)


def unseen_posts(posts, counts, again):
    fresh = 0
    for kind, value in posts:
        path = post_path(kind, value)
        if path is not None and still_allowed(path, counts, again) and not path.exists():
            fresh += 1
    return fresh


def reddit_posts(needed, counts, again):
    posts = []
    seen = set()
    reached = False
    handle = tempfile.NamedTemporaryFile(prefix='cladookie-', suffix='.rss', delete=False)
    listing = Path(handle.name)
    handle.close()
    want = max(needed * 2, 8)
    feeds = list(CALDRUKI_FEEDS)
    random.shuffle(feeds)
    try:
        for feed in feeds:
            url = feed
            for _ in range(FEED_PAGES):
                page, last = feed_page(url, listing)
                if not page and not reached:
                    time.sleep(4)
                    page, last = feed_page(url, listing)
                if not page:
                    break
                reached = True
                for blob in page:
                    posts_in(blob, posts, seen)
                if unseen_posts(posts, counts, again) >= want:
                    return posts, reached
                if not last:
                    break
                joiner = '&' if '?' in feed else '?'
                url = f'{feed}{joiner}after={last}'
                time.sleep(2.5)
    finally:
        listing.unlink(missing_ok=True)
    return posts, reached


def download_reddit_video(video_id, dest):
    scratch = Path(tempfile.mkdtemp(prefix='cladookie-'))
    try:
        playlist = scratch / 'playlist.mpd'
        page = f'https://v.redd.it/{video_id}/DASHPlaylist.mpd'
        if not fetch_url(page, playlist, 'application/dash+xml,*/*'):
            return False
        text = playlist.read_text(encoding='utf-8', errors='replace')
        match = re.search(r'mediaPresentationDuration="(PT[^"]+)"', text)
        length = clock_seconds(match.group(1)) if match else None
        if length is None or length <= 0.2 or length > VIDEO_MAX:
            return False
        names = re.findall(r'<BaseURL>(CMAF_\d+\.mp4)</BaseURL>', text)
        if not names:
            return False
        best = max(names, key=lambda name: int(re.search(r'\d+', name).group()))
        video = scratch / 'video.mp4'
        if not fetch_url(f'https://v.redd.it/{video_id}/{best}', video, 'video/mp4,*/*'):
            return False
        audio_names = re.findall(r'<BaseURL>(CMAF_AUDIO[^<]+)</BaseURL>', text)
        audio = None
        if audio_names:
            audio = scratch / 'audio.mp4'
            if not fetch_url(f'https://v.redd.it/{video_id}/{audio_names[0]}', audio, 'video/mp4,*/*'):
                audio = None
        finished = scratch / 'clip.mp4'
        cmd = [tool('ffmpeg'), '-y', '-i', str(video)]
        if audio is not None and audio.exists():
            cmd += ['-i', str(audio), '-map', '0:v:0', '-map', '1:a:0']
        else:
            cmd += ['-map', '0:v:0']
        cmd += ['-c', 'copy', '-movflags', '+faststart', str(finished)]
        try:
            run(cmd, timeout=60)
        except RuntimeError:
            return False
        if not finished.exists() or not (0 < media_duration(finished) <= VIDEO_MAX + 0.2):
            finished.unlink(missing_ok=True)
            return False
        publish(finished, dest)
        return True
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def extract_frame(video, dest):
    length = media_duration(video)
    stamp = min(0.5, max(0.0, length / 2))
    try:
        run([
            tool('ffmpeg'), '-y', '-ss', f'{stamp:.3f}', '-i', str(video),
            '-frames:v', '1', str(dest),
        ], timeout=30)
    except RuntimeError:
        return False
    return dest.exists() and dest.stat().st_size > 100


def offline_backup():
    warn('Offline. Using the Reactables backup.')
    return screenshots([REACTABLES])


def reddit_images(needed, counts, again):
    info('Getting pictures and videos up to 15 seconds from r/Caldruki')
    posts, reached = reddit_posts(needed, counts, again)
    if not reached:
        return offline_backup()
    CALDRUKI.mkdir(parents=True, exist_ok=True)
    buckets = {'fresh-video': [], 'fresh-image': [], 'cached-video': [], 'cached-image': []}
    for kind, value in posts:
        path = post_path(kind, value)
        if path is None or not still_allowed(path, counts, again):
            continue
        age = 'cached' if path.exists() else 'fresh'
        buckets[f'{age}-{kind if kind == "video" else "image"}'].append((kind, value))
    for bucket in buckets.values():
        random.shuffle(bucket)
    found = sum(len(bucket) for bucket in buckets.values())
    info(f'{found} posts to choose from. New ones come first.')
    saved = []
    download_failed = False
    while len(saved) < needed:
        post = draw_biased(buckets['fresh-video'], buckets['fresh-image'])
        if post is None:
            post = draw_biased(buckets['cached-video'], buckets['cached-image'])
        if post is None:
            break
        kind, value = post
        if kind == 'video':
            path = CALDRUKI / f'{value}.mp4'
        else:
            name = Path(urlparse(value).path).name
            if Path(name).suffix.lower() not in IMAGE_EXTS:
                continue
            path = CALDRUKI / name
        uses = counts.get(reactable_key(path), 0)
        if uses >= MAX_USES or (uses and not again):
            continue
        ready = path.exists() and (
            (is_video(path) and 0 < media_duration(path) <= VIDEO_MAX + 0.2)
            or (not is_video(path) and path.stat().st_size >= 8000 and looks_like_image(path))
        )
        if not ready:
            step('Fetch', path.name)
            if kind == 'video':
                if not download_reddit_video(value, path):
                    continue
            elif not fetch_url(value, path, 'image/avif,image/webp,image/*,*/*;q=0.8'):
                download_failed = True
                continue
        if is_video(path):
            if not path.exists() or not (0 < media_duration(path) <= VIDEO_MAX + 0.2):
                path.unlink(missing_ok=True)
                continue
        elif not path.exists() or path.stat().st_size < 8000 or not looks_like_image(path):
            path.unlink(missing_ok=True)
            continue
        saved.append(path)
        if len(saved) >= needed:
            break
    if saved:
        label = 'clip' if len(saved) == 1 else 'clips'
        info(f'{len(saved)} {label} from r/Caldruki')
        return saved
    if download_failed:
        return offline_backup()
    warn('No new pictures or videos from r/Caldruki.')
    return []


def screenshots(paths):
    files = []
    for path in paths:
        path = Path(path)
        if path.is_dir():
            files.extend(sorted(item for item in path.iterdir() if item.is_file()))
        elif path.is_file():
            files.append(path)
    usable = []
    for path in files:
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTS:
            usable.append(path)
        elif suffix in VIDEO_EXTS and 0 < media_duration(path) <= VIDEO_MAX + 0.2:
            usable.append(path)
    return usable


def prepare_beat(image, aspect, force, library, theme='', prior_lines=None, heading=None, scratch=None):
    theme = ' '.join(str(theme or '').split())
    key = reactable_key(image)
    used = load_used().get(key, 0)
    if used >= MAX_USES:
        title(heading or 'Screenshot')
        note(image.name)
        step('Skip', f'already used {used} times. The limit is {MAX_USES}.')
        return None
    work = Path(scratch) / safe_stem(image)
    work.mkdir(parents=True, exist_ok=True)
    title(heading or 'Screenshot')
    note(image.name)
    step('Look', 'judging the picture. About two minutes.')
    frame = image
    if is_video(image):
        frame = work / 'frame.jpg'
        if not extract_frame(image, frame):
            warn('Could not read that video. Skipping it.')
            return None
    read = screen_read(frame)
    if too_much_text(read):
        step('Skip', 'too much text in that picture')
        return None
    emotion = pick_emotion()
    step('Write', 'picking a reaction and a caption')
    beat = react(read, library, theme, prior_lines if theme else None, emotion=emotion)
    beat['sting'] = None if beat.get('emotion') == 'Silence' else pick_sting(library)
    step('Line', f'{beat["emotion"]}  ·  {beat["line"] or "no caption"}')
    step('Sound', beat.get('sting') or 'none')

    choice = cast(beat, library)
    voice_path = work / 'voice.wav'
    spoken = spoken_line(beat['line'])
    if spoken:
        step('Say', 'reading the caption out loud. About a minute.')
        speak(beat['line'], voice_path)
    else:
        voice_path = None
    voice = voice_path if voice_path and voice_path.exists() else None
    sting = Path(choice['sting_file']) if choice.get('sting_file') else None
    clip_len = media_duration(image) if is_video(image) else 0.0
    reveal = max(media_duration(voice) + 1.0, min(clip_len, VIDEO_MAX))
    minimum = reveal + media_duration(sting)
    return {
        'image': image,
        'choice': choice,
        'voice': voice,
        'reveal': reveal,
        'minimum': minimum,
        'work': work,
        'emotion': beat['emotion'],
        'line': beat['line'],
        'readout': read.get('on_screen') or '',
        'sting': beat.get('sting'),
        'theme': theme,
    }


def make_beat(image, aspect, hold, force, library, theme=''):
    dest_dir = OUTPUT / ('shorts' if aspect == 'short' else 'wide')
    with tempfile.TemporaryDirectory(prefix='cladookie-') as scratch:
        prepared = prepare_beat(
            image, aspect, force, library, theme, heading='Wide clip', scratch=scratch,
        )
        if prepared is None:
            return None
        step('Title', 'naming the file from the readout. About a minute.')
        dest = titled_dest(dest_dir, clip_title(prepared.get('readout') or prepared['line']))
        sting = Path(prepared['choice']['sting_file']) if prepared['choice'].get('sting_file') else None
        duration = prepared['reveal'] + max(media_duration(sting), hold)
        step('Build', f'{duration:.0f} seconds')
        finish_beat(prepared, duration, aspect, dest)
        meta = {
            'duration': round(duration, 3),
            'beats': 1,
            'line': prepared['line'],
            'lines': [prepared['line']],
        }
    return dest, meta


def finish_beat(prepared, duration, aspect, dest):
    compose(
        prepared['image'],
        prepared['choice'],
        prepared['voice'],
        duration,
        prepared['reveal'],
        aspect,
        prepared['work'],
        dest,
    )
    mark_used(prepared['image'])


def draw_biased(videos, images):
    if videos and (not images or random.random() < VIDEO_CHANCE):
        return videos.pop()
    if images:
        return images.pop()
    if videos:
        return videos.pop()
    return None


def draw_clip(pending):
    videos = [item for item in pending if is_video(item)]
    stills = [item for item in pending if not is_video(item)]
    pick = draw_biased(videos, stills)
    if pick is not None:
        pending.remove(pick)
    return pick


def vary_emotions(beats):
    remaining = list(beats)
    ordered = []
    last = None
    while remaining:
        choices = [beat for beat in remaining if beat['emotion'] != last] or list(remaining)
        pick = random.choice(choices)
        remaining.remove(pick)
        ordered.append(pick)
        last = pick['emotion']
    return ordered


def fit_beat(beat, extra):
    if 'sting_len' not in beat:
        beat['sting_len'] = max(0.0, beat['minimum'] - beat['reveal'])
    beat['reveal'] += extra
    beat['duration'] = beat['reveal'] + beat['sting_len']


def plan_durations(beats):
    if not beats:
        return []
    total = sum(beat['minimum'] for beat in beats)
    if total > SHORT_MAX:
        chosen = beats[:min(2, len(beats))]
        total = sum(beat['minimum'] for beat in chosen) or SHORT_MAX
        scale = SHORT_MAX / total
        for beat in chosen:
            beat['duration'] = max(beat['reveal'] + 0.2, beat['minimum'] * scale)
        drift = SHORT_MAX - sum(beat['duration'] for beat in chosen)
        chosen[-1]['duration'] = max(chosen[-1]['reveal'] + 0.2, chosen[-1]['duration'] + drift)
        return vary_emotions(chosen)

    if total < SHORT_MIN:
        target = SHORT_MIN
    else:
        slack = min(1.2, SHORT_MAX - total)
        target = total if slack <= 0.05 else total + random.triangular(0, slack, 0)
    chosen = vary_emotions(list(beats))
    extra = max(0.0, target - total) / len(chosen)
    for beat in chosen:
        fit_beat(beat, extra)
    drift = target - sum(beat['duration'] for beat in chosen)
    fit_beat(chosen[-1], drift)
    return chosen


def concat_segments(segments, listing, dest):
    lines = []
    for segment in segments:
        path = segment.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{path}'")
    listing.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    finished = listing.with_name('joined.mp4')
    run([
        tool('ffmpeg'), '-y', '-f', 'concat', '-safe', '0', '-i', str(listing),
        '-c', 'copy', str(finished),
    ], timeout=180, expect=12)
    if not finished.exists() or media_duration(finished) <= 0:
        finished.unlink(missing_ok=True)
        raise RuntimeError('The video did not finish.')
    publish(finished, dest)


def render_short(prepared, aspect):
    beats = plan_durations(prepared)
    dest_dir = OUTPUT / ('shorts' if aspect == 'short' else 'wide')
    step('Title', 'naming the file from one readout. About a minute.')
    name = clip_title(readout_for_title(beats) or beats[0].get('line') or 'clip')
    dest = titled_dest(dest_dir, name)
    segments = []
    print()
    info('Building the video')
    elapsed = 0.0
    for index, beat in enumerate(beats, 1):
        segment = beat['work'] / 'segment.mp4'
        step('Build', f'picture {index} of {len(beats)}')
        compose(
            beat['image'],
            beat['choice'],
            beat['voice'],
            beat['duration'],
            beat['reveal'],
            aspect,
            beat['work'],
            segment,
            elapsed,
        )
        segments.append(segment)
        elapsed += beat['duration']
    total = sum(beat['duration'] for beat in beats)
    pictures = 'picture' if len(beats) == 1 else 'pictures'
    step('Join', f'{len(beats)} {pictures}, about {total:.0f} seconds')
    concat_segments(segments, beats[0]['work'] / 'short_concat.txt', dest)
    meta = {
        'duration': round(media_duration(dest) or total, 3),
        'beats': len(beats),
        'lines': [beat['line'] for beat in beats],
        'line': beats[0]['line'],
    }
    for beat in beats:
        mark_used(beat['image'])
    return dest, [beat['image'] for beat in prepared if beat not in beats], meta


def put_back(pending, image):
    pending.insert(random.randrange(len(pending) + 1), image)


def render_shorts(pool, limit, force, library, theme=''):
    made = []
    pending = list(pool)
    with tempfile.TemporaryDirectory(prefix='cladookie-') as scratch:
        return _render_shorts(pending, made, limit, force, library, theme, Path(scratch))


def room_for_another(prepared):
    count = len(prepared)
    if count >= 4:
        return False
    if count < 2:
        return True
    total = sum(beat['minimum'] for beat in prepared)
    if total >= SHORT_MAX:
        return False
    if total < SHORT_MIN:
        return True
    room = SHORT_MAX - total
    typical = total / count
    if typical > room:
        return False
    return random.random() < room / (room + typical)


def _render_shorts(pending, made, limit, force, library, theme, scratch):
    while pending and (limit is None or len(made) < limit):
        prepared = []
        prior = []
        number = 0
        while pending and room_for_another(prepared):
            image = draw_clip(pending)
            number += 1
            beat = prepare_beat(
                image, 'short', force, library, theme, prior,
                heading=f'Picture {number}',
                scratch=scratch,
            )
            if beat is None:
                continue
            prepared.append(beat)
            if theme and beat['line']:
                prior.append(beat['line'])
            total = sum(item['minimum'] for item in prepared)
            if len(prepared) >= 2 and total > SHORT_MAX:
                put_back(pending, prepared.pop()['image'])
                if len(prepared) >= 2:
                    break
        if len(prepared) < 2:
            for beat in prepared:
                put_back(pending, beat['image'])
            break
        dest, unused, meta = render_short(prepared, 'short')
        for image in unused:
            put_back(pending, image)
        made.append((dest, meta))
    return made


def order_clips(folder, seconds):
    clips = []
    for video in sorted(folder.glob('*.mp4')):
        clips.append({'video': video, 'emotion': 'Unhinged', 'duration': media_duration(video)})
    random.shuffle(clips)
    ordered = []
    last = None
    total = 0.0
    while clips and total < seconds:
        choices = [clip for clip in clips if clip['emotion'] != last] or list(clips)
        pick = random.choice(choices)
        clips.remove(pick)
        ordered.append(pick)
        last = pick['emotion']
        total += pick['duration']
    return ordered


def compile_videos(aspect):
    folder = OUTPUT / ('shorts' if aspect == 'short' else 'wide')
    ordered = order_clips(folder, COMPILE_SECONDS)
    if not ordered:
        raise SystemExit(f'No clips in {folder} to compile.')
    dest_dir = OUTPUT / 'compilations'
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f'caldruki-{aspect}.mp4'
    clips = 'video' if len(ordered) == 1 else 'videos'
    info(f'Stitching {len(ordered)} {clips} into one file')
    with tempfile.TemporaryDirectory(prefix='cladookie-') as scratch:
        concat_segments(
            [clip['video'] for clip in ordered],
            Path(scratch) / 'list.txt',
            dest,
        )
    return dest


LOGO = """\
  ███████  ██                    ██                        ██       ██
 ██    ██  ██                    ██                        ██
██         ██  ███████    ████████  ████████  ████████     ██    ██ ██  ████████
██         ██       ██   ██    ██  ██     ██ ██     ██     ██   ██  ██ ██     ██
██         ██  ████████  ██    ██  ██     ██ ██     ██     ███████  ██ █████████
 ██    ██  ██ ██    ██   ██   ███  ██     ██ ██     ██     ██   ██  ██ ██
  ███████  ██  ██████ ██  ███████   ████████  ████████     ██    ██ ██  ████████
"""


def show_logo():
    if not sys.stdout.isatty():
        return
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except (OSError, ValueError):
            pass
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel = ctypes.windll.kernel32
            handle = kernel.GetStdHandle(-11)
            mode = ctypes.c_uint()
            if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel.SetConsoleMode(handle, mode.value | 0x0004)
        except OSError:
            pass
    lines = [line.rstrip() for line in LOGO.splitlines() if line.strip()]
    rows = max(1, len(lines) - 1)
    for y, line in enumerate(lines):
        down = y / rows
        amount = down
        red, green, blue = mix(40, 150, amount), mix(130, 210, amount), mix(210, 255, amount)
        bold = '1;' if down < 0.45 else ''
        print(f'\033[{bold}38;2;{red};{green};{blue}m{line}\033[0m')
    print()
    box('Cladookie', ['shorts from screenshots', str(ROOT)])
    print(f'  {color("Type a number, or q to quit.", DIM, dim=True)}', flush=True)
    print()


def prompt(label, default=None):
    hint = '' if default is None else f' [{default}]'
    rule()
    print(f'{color("❯", SKY)} {color(label, INK)}{color(hint, DIM, dim=True)} ', end='', flush=True)
    try:
        text = input().strip()
    except EOFError:
        print()
        raise SystemExit(0) from None
    if text:
        return text
    return '' if default is None else str(default)


def menu(heading, options):
    print()
    print(f'  {color(heading, HEAD, bold=True)}', flush=True)
    print()
    valid = {}
    for key, label in options:
        valid[str(key).lower()] = str(key).lower()
        print(f'    {color(str(key), SKY)}  {color(label, INK)}', flush=True)
    print()
    while True:
        picked = prompt('Choose').lower()
        if picked in valid:
            return valid[picked]
        info('Pick one of the choices above.')


def ask_count():
    while True:
        text = prompt('How many? Or all', '1').lower()
        if text == 'all':
            return None
        if text.isdigit() and int(text) > 0:
            return int(text)
        info('Type a number, or all.')


def ask_yes(label, default=False):
    while True:
        text = prompt(label, 'yes' if default else 'no').lower()
        if text in ('y', 'yes'):
            return True
        if text in ('n', 'no'):
            return False
        info('Answer yes or no.')


def ask_hold():
    while True:
        text = prompt('Seconds the reaction stays up', '5')
        try:
            value = float(text)
        except ValueError:
            value = 0
        if value > 0:
            return value
        info('Type a number of seconds.')


def announce(aspect, limit, hold, available, theme):
    if aspect == 'short':
        if limit is None:
            opening = 'Making shorts until the screenshots run out.'
        elif limit == 1:
            opening = 'Making 1 short.'
        else:
            opening = f'Making {limit} shorts.'
        info(f'{opening} Each one uses 2 to 4 pictures or videos, up to 15 seconds each, and lasts 15 to 25 seconds.')
    else:
        if limit is None:
            opening = 'Making a wide video for every screenshot still available.'
        elif limit == 1:
            opening = 'Making 1 wide video.'
        else:
            opening = f'Making {limit} wide videos.'
        info(f'{opening} The reaction stays on screen for {hold:g} seconds.')
    if theme:
        info(f'About: {theme}')
    ready = 'screenshot' if len(available) == 1 else 'screenshots'
    info(f'{len(available)} {ready} ready.')


def main():
    clear_idle_work()
    show_logo()
    if sys.argv[1:]:
        info('Answer the questions below. Extra words after the command are ignored.')
    choice = menu('What do you want to do?', (
        ('1', 'Make a short'),
        ('2', 'Make a wide video'),
        ('3', 'Stitch videos you already have'),
        ('q', 'Quit'),
    ))
    if choice == 'q':
        print()
        print(f'  {color("Goodbye.", DIM, dim=True)}', flush=True)
        return
    if choice == '3':
        kind = menu('Which videos should I stitch?', (
            ('1', 'Shorts'),
            ('2', 'Wide videos'),
        ))
        done(compile_videos('short' if kind == '1' else 'wide'))
        return
    if not TEXT.exists():
        raise SystemExit(f'Missing model: {TEXT}')
    ensure_vision()
    ensure_tts()
    library = sound_library()
    aspect = 'short' if choice == '1' else 'wide'
    print()
    limit = ask_count()
    theme = ' '.join(prompt('What is it about? Enter skips').split())
    hold = ask_hold() if aspect == 'wide' else 5.0
    again = ask_yes('Use screenshots that were already used?', False)
    counts = load_used()
    if aspect == 'short':
        needed = 24 if limit is None else max(4, limit * 4)
    else:
        needed = 12 if limit is None else max(1, limit)
    found = reddit_images(needed, counts, again)
    if not found:
        print()
        info('No pictures to use.')
        info('Say yes to using pictures again, or wait for new posts on r/Caldruki.')
        return
    available = [path for path in found if counts.get(reactable_key(path), 0) < MAX_USES]
    if not again:
        available = [path for path in available if counts.get(reactable_key(path), 0) == 0]
    if aspect == 'wide' and not again:
        folder = OUTPUT / 'wide'
        available = [path for path in available if not (folder / f'{safe_stem(path)}.mp4').exists()]
    print()
    if available:
        announce(aspect, limit, hold, available, theme)
    else:
        info('No screenshots left to use. They were already used.')
    if aspect == 'short':
        made = render_shorts(available, limit, again, library, theme) if available else []
    else:
        pending = list(available)
        batch = []
        while pending and (limit is None or len(batch) < limit):
            batch.append(draw_clip(pending))
        made = []
        for image in batch:
            clip = make_beat(image, aspect, hold, again, library, theme)
            if clip is not None:
                made.append(clip)
    for path, meta in made:
        done(path, result_notes(meta, path))
    if not made:
        print()
        if available:
            info('No new video this time.')
        info('Say yes to using pictures again, or wait for new posts on r/Caldruki.')
        info('You can also stitch the videos you already have.')


if __name__ == '__main__':
    atexit.register(clear_idle_work)
    try:
        main()
    except KeyboardInterrupt:
        print()
        print(f'  {color("Stopped. Finished videos stay in output/shorts.", DIM, dim=True)}', flush=True)
        raise SystemExit(130) from None
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        report_error(error)
