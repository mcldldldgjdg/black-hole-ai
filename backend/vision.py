import base64
import io
import json
import os
import re

import httpx
from PIL import Image, ImageDraw

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:3b")
TEXT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
VISION_TIMEOUT = httpx.Timeout(300.0, connect=5.0)

SUPPORTED_TYPES = {"living", "bedroom", "kitchen", "office", "bathroom"}
TYPICAL_SIZE = {"living": (5.0, 4.0), "bedroom": (4.0, 3.5), "kitchen": (3.5, 3.0), "office": (3.5, 3.0), "bathroom": (2.3, 1.7)}
TYPE_WORDS = {
    "living": ("гостин", "зал", "living", "общая"),
    "bedroom": ("спальн", "bedroom", "детск", "жилая"),
    "kitchen": ("кухн", "kitchen", "столов"),
    "office": ("кабинет", "office", "рабоч"),
    "bathroom": ("ванн", "санузел", "с/у", "туалет", "bath", "wc"),
    "hallway": ("коридор", "прихож", "холл", "hall"),
    "balcony": ("балкон", "лоджи", "balcon"),
}

ROOMS_SCHEMA = {
    "type": "object",
    "properties": {
        "rooms": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "type": {"type": "string"},
            "width": {"type": "number"}, "length": {"type": "number"}, "area": {"type": "number"},
        }, "required": ["name", "type", "width", "length", "area"]}},
        "height": {"type": "number"},
        "notes": {"type": "string"},
    },
    "required": ["rooms", "height", "notes"],
}

SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "object": {"type": "string"},
        "suggestions": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "description": {"type": "string"}, "prompt": {"type": "string"},
        }, "required": ["title", "description", "prompt"]}},
    },
    "required": ["object", "suggestions"],
}

PLAN_PROMPT = (
    "На изображении план квартиры. Найди все помещения.\n"
    "Для каждого верни: name (подпись на плане или понятное название), "
    "type (living, bedroom, kitchen, office, bathroom, hallway, balcony), "
    "width и length — стороны в метрах, area — площадь в м² (если подписана; иначе 0).\n"
    "Размеры на планах часто в миллиметрах (5200 = 5.2 м) или сантиметрах (520 = 5.2 м). "
    "Если подписана только площадь, оцени стороны по пропорциям прямоугольника комнаты на чертеже. "
    "Проверь: width * length должно быть близко к подписанной площади.\n"
    "height — 0. notes — коротко, что не удалось прочитать."
)

PHOTO_PROMPT = (
    "На фото комната. Определи её тип (living, bedroom, kitchen, office; если комната пустая — по окнам, "
    "розеткам и выводам коммуникаций) и оцени размеры в метрах по ориентирам: межкомнатная дверь 0.8 x 2.0 м, "
    "окно около 1.4 м в ширину, потолок 2.5-2.8 м, розетка на высоте 0.3 м. Верни одно помещение в rooms "
    "(name, type, width, length, area=width*length), height — оценка высоты потолка. "
    "В notes опиши, что видно: окна, двери, пол, стены, что уже стоит."
)

SUGGEST_PROMPT = (
    "Первое изображение — фото интерьера, на нём красной рамкой выделена область. Второе — эта область крупно.\n"
    "object — какой предмет или поверхность в выделенной области (по-русски, 1-4 слова, например «серый диван», «стена», «окно»).\n"
    "suggestions — ровно 3 непохожих варианта в стиле «{style}»: 1) тот же предмет в другом цвете или материале; "
    "2) другая форма или модель этого предмета; 3) смелое необычное решение. Для каждого: "
    "title (по-русски, 2-4 слова), description (по-русски, одно предложение: как это будет выглядеть), "
    "prompt (ТОЛЬКО по-английски, 5-12 слов: что нарисовать на этом месте).\n"
    'Пример: {{"object": "серый диван", "suggestions": [{{"title": "Льняной диван", '
    '"description": "Светлый льняной диван с деревянными ножками сделает зону отдыха легче.", '
    '"prompt": "light beige linen sofa with wooden legs and white cushions"}}]}}'
)
CYRILLIC = re.compile(r"[а-яё]", re.I)
TRANSLATE_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "string"}}}, "required": ["items"]}


def decode_image(data_url, max_side=1024):
    raw = data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url
    img = Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB")
    img.thumbnail((max_side, max_side))
    return img


def encode_image(img, fmt="JPEG"):
    buf = io.BytesIO()
    img.save(buf, format=fmt, quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def box_pixels(img, box):
    w, h = img.size
    x0 = max(0, min(w - 1, round(box["x"] * w)))
    y0 = max(0, min(h - 1, round(box["y"] * h)))
    x1 = max(x0 + 1, min(w, round((box["x"] + box["w"]) * w)))
    y1 = max(y0 + 1, min(h, round((box["y"] + box["h"]) * h)))
    return x0, y0, x1, y1


async def ask_vision(prompt, images, schema, temperature=0.0):
    encoded = [encode_image(i) for i in images]
    async with httpx.AsyncClient(timeout=VISION_TIMEOUT) as client:
        for t, fmt in ((temperature, schema), (temperature + 0.3, schema), (temperature, None)):
            body = {"model": VISION_MODEL, "prompt": prompt, "images": encoded, "stream": False, "keep_alive": "2m",
                    "options": {"temperature": min(t, 1.0), "num_ctx": 4096}}
            if fmt:
                body["format"] = fmt
            r = await client.post(f"{OLLAMA_HOST}/api/generate", json=body)
            if r.status_code != 200:
                raise RuntimeError(f"Ollama {r.status_code}: {r.text[:200]}")
            data = r.json()
            if data.get("done") and data.get("response"):
                break
    text = data.get("response", "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        return json.loads(m.group(0)) if m else {}


def guess_type(raw_type, name):
    text = f"{raw_type} {name}".lower()
    for room_type, words in TYPE_WORDS.items():
        if any(w in text for w in words):
            return room_type
    return "living"


def to_meters(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if v > 100:
        v /= 1000 if v > 1000 else 100
    return round(v, 2)


def clean_rooms(data, typical_if_unknown=False):
    rooms, skipped = [], []
    for r in data.get("rooms") or []:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name") or "").strip()[:40]
        room_type = guess_type(r.get("type"), name)
        w, l = to_meters(r.get("width")), to_meters(r.get("length"))
        try:
            area = float(r.get("area") or 0)
        except (TypeError, ValueError):
            area = 0.0
        if area > 1 and (w < 1 or l < 1):
            w = l = round(area ** 0.5, 2)
        elif area > 1 and abs(w * l - area) / area > 0.25:
            k = (area / (w * l)) ** 0.5
            w, l = round(w * k, 2), round(l * k, 2)
        if room_type not in SUPPORTED_TYPES:
            skipped.append(name or room_type)
            continue
        if not (1.2 <= w <= 15 and 1.2 <= l <= 15) and typical_if_unknown:
            w, l = TYPICAL_SIZE[room_type]
        if not (1.2 <= w <= 15 and 1.2 <= l <= 15):
            skipped.append(f"{name or room_type} (размеры не распознаны)")
            continue
        rooms.append({"type": room_type, "name": name, "width": w, "length": l})
    if rooms and not any(r["type"] == "living" for r in rooms):
        bedrooms = [r for r in rooms if r["type"] == "bedroom"]
        if len(bedrooms) > 1:
            max(bedrooms, key=lambda r: r["width"] * r["length"])["type"] = "living"
    height = to_meters(data.get("height"))
    return rooms[:6], skipped, height if 2.0 <= height <= 5.0 else 2.7


async def extract_rooms(data_url, kind):
    img = decode_image(data_url, 1280)
    data = await ask_vision(PLAN_PROMPT if kind == "plan" else PHOTO_PROMPT, [img], ROOMS_SCHEMA)
    rooms, skipped, height = clean_rooms(data, typical_if_unknown=kind != "plan")
    if kind == "plan":
        height = 2.7
    else:
        rooms, skipped = rooms[:1], []
    return {
        "rooms": [dict(r, height=height) for r in rooms],
        "skipped": skipped,
        "estimate": kind != "plan",
        "notes": str(data.get("notes") or "").strip()[:400],
    }


async def suggest_edits(data_url, box, style):
    img = decode_image(data_url)
    x0, y0, x1, y1 = box_pixels(img, box)
    marked = img.copy()
    ImageDraw.Draw(marked).rectangle([x0, y0, x1, y1], outline=(255, 0, 0), width=max(3, img.width // 200))
    crop = img.crop((x0, y0, x1, y1))
    data = await ask_vision(SUGGEST_PROMPT.format(style=style), [marked, crop], SUGGEST_SCHEMA, temperature=0.7)
    suggestions, seen = [], set()
    for s in data.get("suggestions") or []:
        if isinstance(s, dict) and s.get("prompt") and s["prompt"].lower() not in seen:
            seen.add(s["prompt"].lower())
            suggestions.append({k: str(s.get(k) or "").strip()[:200] for k in ("title", "description", "prompt")})
    suggestions = suggestions[:3]
    need = [i for i, s in enumerate(suggestions) if CYRILLIC.search(s["prompt"])]
    if need:
        english = await translate([suggestions[i]["prompt"] for i in need])
        for i, text in zip(need, english):
            suggestions[i]["prompt"] = text
    return {"object": str(data.get("object") or "").strip()[:60], "suggestions": suggestions}


async def translate(texts):
    prompt = ("Переведи на английский каждую строку как короткое описание предмета интерьера для генерации картинки "
              "(5-12 слов, без лишних слов). Верни items в том же порядке.\n" + "\n".join(f"- {t}" for t in texts))
    async with httpx.AsyncClient(timeout=VISION_TIMEOUT) as client:
        r = await client.post(f"{OLLAMA_HOST}/api/generate", json={
            "model": TEXT_MODEL, "prompt": prompt, "format": TRANSLATE_SCHEMA, "stream": False,
            "options": {"temperature": 0.1},
        })
    items = json.loads(r.json().get("response", "{}")).get("items") or []
    return [str(e).strip()[:200] if e and not CYRILLIC.search(str(e)) else t for t, e in zip(texts, items + [None] * len(texts))]
