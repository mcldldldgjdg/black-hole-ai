from celery import Celery
import httpx
import json
import math
import random
import os
import re
from datetime import datetime

from database import SessionLocal, Generation
from prompts import DESIGN_SCHEMA, DIVIDERS, SYSTEM_PROMPT, build_prompt, required_kinds, room_key, room_name
from shops import shop_links

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery("tasks", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

LLM_TIMEOUT = httpx.Timeout(300.0, connect=5.0)


DEFAULTS = {
    "диван": {"item": "Диван", "type": "диван", "description": "Мягкий диван для гостиной", "materials": "ткань, дерево", "dimensions": "220x85x95", "price": 35000},
    "шкаф": {"item": "Шкаф", "type": "шкаф", "description": "Вместительный шкаф для вещей", "materials": "ЛДСП, шпон", "dimensions": "100x200x60", "price": 28000},
    "тв": {"item": "Телевизор 55\"", "type": "телевизор", "description": "ТВ для просмотра фильмов", "materials": "пластик, металл", "dimensions": "125x75x8", "price": 45000},
    "кровать": {"item": "Кровать двуспальная", "type": "кровать", "description": "Кровать с ортопедическим основанием", "materials": "дерево, текстиль", "dimensions": "160x50x200", "price": 40000},
    "гарнитур": {"item": "Кухонный гарнитур", "type": "гарнитур", "description": "Линейный гарнитур со столешницей", "materials": "МДФ, пластик", "dimensions": "240x220x60", "price": 65000},
    "холодос": {"item": "Холодильник", "type": "холодильник", "description": "Двухкамерный холодильник No Frost", "materials": "металл, пластик", "dimensions": "60x185x65", "price": 42000},
    "стол": {"item": "Стол", "type": "стол", "description": "Стол из массива", "materials": "дерево, металл", "dimensions": "120x75x70", "price": 15000},
    "стул": {"item": "Стул", "type": "стул", "description": "Удобный стул", "materials": "дерево, ткань", "dimensions": "45x90x45", "price": 6000},
    "ванна": {"item": "Ванна акриловая 170 см", "type": "ванна", "description": "Акриловая ванна с экраном", "materials": "акрил", "dimensions": "170x60x75", "price": 25000},
    "унитаз": {"item": "Унитаз подвесной с инсталляцией", "type": "унитаз", "description": "Подвесной унитаз с инсталляцией и кнопкой", "materials": "фарфор, сталь", "dimensions": "40x80x55", "price": 22000},
    "раковина": {"item": "Раковина с тумбой и зеркалом 60 см", "type": "раковина", "description": "Подвесная тумба с раковиной, смесителем и зеркалом", "materials": "керамика, МДФ", "dimensions": "60x85x45", "price": 15000},
}
PLUMBING = {"ванна", "унитаз", "раковина"}
FOREIGN = {
    "kitchen": {"кровать"} | PLUMBING,
    "living": {"гарнитур", "холодос"} | PLUMBING,
    "bedroom": {"гарнитур", "холодос"} | PLUMBING,
    "office": {"гарнитур", "холодос"} | PLUMBING,
    "bathroom": {"диван", "кровать", "гарнитур", "холодос", "тв", "стол", "стул", "кресло"},
}


def foreign_kinds(key):
    out = set()
    for t in key.split("+"):
        out |= FOREIGN.get(t, set())
    return out - set(required_kinds(key))
DEFAULT_PALETTE = [
    {"name": "Тёплый белый", "hex": "#F2EEE6"},
    {"name": "Светлый дуб", "hex": "#C8A97E"},
    {"name": "Графит", "hex": "#3A3D42"},
    {"name": "Шалфей", "hex": "#9CAF88"},
]

def kind_of(it):
    t = str(it.get("type") or "").lower()
    n = str(it.get("item") or "").lower()
    if "диван" in t or "диван" in n: return "диван"
    if "кровать" in t or "кровать" in n: return "кровать"
    if "холодильник" in t or "холодильник" in n: return "холодос"
    if "гарнитур" in t or "гарнитур" in n: return "гарнитур"
    if "шкаф" in t or "шкаф" in n: return "шкаф"
    if "телевизор" in t or "тв" in t or "телевиз" in n: return "тв"
    text = f"{t} {n}"
    if "ванн" in text or "душ" in text: return "ванна"
    if "унитаз" in text or "инсталляц" in text: return "унитаз"
    if "раковин" in text or "умывальник" in text: return "раковина"
    if any(w in text for w in ("ламп", "торшер", "светильник", "люстр", "бра")): return "лампа"
    if any(w in text for w in ("мультиварк", "микроволн", "чайник", "посудомо", "стиральн", "духов", "варочн", "кофевар", "кофемаш", "тостер", "блендер", "техник")): return "техника"
    if "стол" in t or "стол" in n: return "стол"
    if "стул" in t or "стул" in n: return "стул"
    if "кресл" in text: return "кресло"
    if "тумб" in text: return "тумба"
    if "стеллаж" in text or "полк" in text: return "стеллаж"
    if "ковёр" in text or "ковер" in text or "коврик" in text: return "ковёр"
    return "другое"


def to_number(v):
    if isinstance(v, (int, float)):
        return float(v)
    digits = re.sub(r"[^\d.,]", "", str(v or "")).replace(",", ".")
    try:
        return float(digits)
    except ValueError:
        return 0.0


def sane(v, lo, hi, default):
    v = to_number(v)
    return v if lo <= v <= hi else default


def parse_design_json(text):
    if not text:
        return {}
    candidates = [text]
    for pattern in (r'```json\s*([\s\S]*?)```', r'```\s*([\s\S]*?)```', r'\{[\s\S]*\}'):
        m = re.search(pattern, text)
        if m:
            candidates.append(m.group(1) if m.lastindex else m.group(0))
    for c in candidates:
        try:
            data = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return {"furniture": data}
    return {}


UNASKED_BIG = {"диван": ("диван",), "тв": ("тв", "телевиз"), "кровать": ("кроват",)}
PRICE_RANGES = [
    (("мультиварк",), 3000, 20000), (("микроволн", "свч"), 5000, 30000), (("чайник",), 1000, 10000),
    (("ковёр", "ковер"), 2000, 50000), (("зеркал",), 1500, 30000), (("тумб",), 2000, 30000),
    (("лампа", "торшер", "светильник", "люстр"), 1000, 30000), (("стул",), 2000, 25000), (("штор", "занавес"), 1500, 20000),
]

WISH_ITEMS = [
    (r"стул|стуль", ("стул",), {"item": "Стул", "type": "стул", "description": "Обеденный стул с мягким сиденьем", "materials": "дерево, ткань", "dimensions": "45x90x50", "price": 6000}),
    (r"мультиварк", ("мультиварк",), {"item": "Мультиварка", "type": "техника", "description": "Мультиварка 5 л", "materials": "пластик, металл", "dimensions": "35x30x35", "price": 7000}),
    (r"микроволн|свч", ("микроволн", "свч"), {"item": "Микроволновая печь", "type": "техника", "description": "Микроволновая печь 20 л", "materials": "металл", "dimensions": "45x26x35", "price": 9000}),
    (r"посудомо", ("посудомо",), {"item": "Посудомоечная машина", "type": "техника", "description": "Встраиваемая посудомойка 45 см", "materials": "металл", "dimensions": "45x82x55", "price": 35000}),
    (r"стиральн", ("стиральн",), {"item": "Стиральная машина", "type": "техника", "description": "Стиральная машина 6 кг", "materials": "металл, пластик", "dimensions": "60x85x45", "price": 32000}),
    (r"кресл", ("кресл",), {"item": "Кресло", "type": "кресло", "description": "Мягкое кресло", "materials": "ткань, дерево", "dimensions": "75x90x80", "price": 15000}),
    (r"шкаф", ("шкаф",), DEFAULTS["шкаф"]),
    (r"\bстол\b|стола\b", ("стол",), DEFAULTS["стол"]),
    (r"диван", ("диван",), DEFAULTS["диван"]),
    (r"кроват", ("кроват",), DEFAULTS["кровать"]),
    (r"телевиз|\bтв\b", ("телевиз", "тв"), DEFAULTS["тв"]),
    (r"холодил", ("холодил",), DEFAULTS["холодос"]),
    (r"гарнит", ("гарнитур",), DEFAULTS["гарнитур"]),
]
NUM_WORDS = {"два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "восемь": 8}


def wished_qty(wishes, pattern):
    m = re.search(r"(\d+|" + "|".join(NUM_WORDS) + r")\s*(?:\w+\s+)?(?:" + pattern + r")", wishes)
    if not m:
        return 1
    n = m.group(1)
    return min(int(n) if n.isdigit() else NUM_WORDS[n], 12)


def ensure_wished(items, wishes):
    low = wishes.lower()
    for pattern, words, default in WISH_ITEMS:
        if not re.search(pattern, low):
            continue
        qty = wished_qty(low, pattern)
        have = [it for it in items if any(w in (it["item"] + " " + it["type"]).lower() for w in words)]
        if have:
            have[0]["qty"] = max(have[0]["qty"], qty)
        else:
            d = dict(default, qty=qty, search_query=default["item"])
            items.append(d)


ROOM_MARKERS = {"living": ("гостин", "зал"), "bedroom": ("спальн",), "kitchen": ("кухн",), "office": ("кабинет",), "bathroom": ("ванн", "санузл", "туалет")}
WORKPLACE_RE = re.compile(r"комп|\bпк\b|ноут|рабоч\w*\s+мест|рабоч\w*\s+стол")


def split_wishes(description):
    parts, current = {}, None
    for chunk in re.split(r"[,;.\n]+", description or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        low = chunk.lower()
        for room_type, markers in ROOM_MARKERS.items():
            if any(m in low for m in markers):
                current = room_type
                break
        parts.setdefault(current, []).append(chunk)
    return {k: ", ".join(v) for k, v in parts.items()}


def wishes_for(room, description, single_room):
    parts = split_wishes(description)
    unsplit = len(parts) == 1 and None in parts
    own = [room.get("wishes") or ""]
    if not unsplit:
        own.append(parts.get(room["type"]))
    elif single_room:
        own.append(description)
    general = parts.get(None) if not unsplit else ("" if single_room else description)
    return ", ".join(p for p in own if p), general or ""


def room_metrics(width, length, height):
    area = width * length
    perimeter = 2 * (width + length)
    wall_area = max(perimeter * height - 4.0, 0)
    return {"area": round(area, 1), "perimeter": round(perimeter, 1), "wall_area": round(wall_area, 1)}


def ask_llm(prompt):
    with httpx.Client() as client:
        for temperature, fmt in ((0.6, DESIGN_SCHEMA), (0.8, DESIGN_SCHEMA), (0.6, None)):
            body = {"model": OLLAMA_MODEL, "system": SYSTEM_PROMPT, "prompt": prompt, "stream": False,
                    "options": {"temperature": temperature, "num_ctx": 4096, "num_predict": 2048}}
            if fmt:
                body["format"] = fmt
            response = client.post(f"{OLLAMA_HOST}/api/generate", json=body, timeout=LLM_TIMEOUT)
            if response.status_code != 200:
                raise Exception(f"Ollama статус {response.status_code}: {response.text[:200]}")
            result = response.json()
            if result.get("done") and result.get("response"):
                break
    return result.get("response", ""), result.get("total_duration", 0)


def price_range(item):
    text = (item["item"] + " " + item["type"]).lower()
    for keys, lo, hi in PRICE_RANGES:
        if any(k in text for k in keys):
            return lo, hi
    return None


EXTRA_OK = {
    "living": {"стол", "кресло", "стеллаж", "лампа", "ковёр", "тумба"},
    "bedroom": {"тумба", "кресло", "лампа", "ковёр", "стеллаж"},
    "kitchen": {"стул", "лампа", "техника"},
    "office": {"стеллаж", "лампа", "кресло", "тумба"},
    "bathroom": set(),
}
KIND_WORDS = {
    "стол": ("стол",), "стул": ("стул",), "тв": ("телевиз", "тв"), "диван": ("диван",), "кровать": ("кроват",),
    "тумба": ("тумб",), "кресло": ("кресл",), "стеллаж": ("стеллаж", "полк"), "лампа": ("ламп", "торшер", "светил"),
    "ковёр": ("ковёр", "ковер", "коврик"), "шкаф": ("шкаф",), "холодос": ("холодил",), "гарнитур": ("гарнит",),
    "техника": ("мультиварк", "микроволн", "чайник", "посудомо", "стиральн", "духов"),
}
MAX_EXTRAS = 3


def keep_relevant(items, room_type, wishes, workplace):
    low = (wishes or "").lower()
    required = set(required_kinds(room_type))
    allowed = set()
    for t in room_type.split("+"):
        allowed |= EXTRA_OK.get(t, EXTRA_OK["living"])
    kept, extras, plumbing = [], 0, set()
    for it in items:
        kind = kind_of(it)
        if kind in PLUMBING:
            if kind in plumbing:
                continue
            plumbing.add(kind)
        wished = bool(low) and any(w in low for w in KIND_WORDS.get(kind, ()))
        if kind in required or wished or it.get("workplace") or it.get("divider") or (workplace and kind == "стул"):
            kept.append(it)
        elif kind in allowed and extras < MAX_EXTRAS:
            kept.append(it)
            extras += 1
    return kept


ZONABLE = {"living", "bedroom", "office"}


def add_divider(items, divider):
    d = dict(DIVIDERS.get(divider, DIVIDERS["стеллаж"]))
    d.update(description="Разделяет комнату на две зоны", materials="ЛДСП, металл", qty=1, search_query=d["item"], divider=True)
    items.append(d)


def capital(text):
    return text[:1].upper() + text[1:]


def normalize_furniture(raw, room_type, workplace=False, wishes=None, divider=None):
    items, by_name = [], {}
    foreign = foreign_kinds(room_type)
    if wishes:
        low = wishes.lower()
        foreign |= {k for k, words in UNASKED_BIG.items() if k not in required_kinds(room_type) and not any(w in low for w in words)}
    for it in raw if isinstance(raw, list) else []:
        if not isinstance(it, dict) or not str(it.get("item") or "").strip():
            continue
        item = {
            "item": capital(str(it.get("item")).strip()[:80]),
            "type": str(it.get("type") or "").strip().lower()[:30],
            "description": str(it.get("description") or "").strip()[:240],
            "materials": str(it.get("materials") or "").strip()[:120],
            "dimensions": str(it.get("dimensions") or "").strip()[:30],
            "price": int(sane(it.get("price"), 300, 3_000_000, 0)),
            "search_query": str(it.get("search_query") or it.get("item")).strip()[:120],
            "qty": int(sane(it.get("qty"), 1, 12, 1)),
        }
        if kind_of(item) in foreign:
            continue
        key = item["item"].lower()
        if key in by_name:
            by_name[key]["qty"] = min(by_name[key]["qty"] + item["qty"], 12)
            continue
        default_price = DEFAULTS.get(kind_of(item), {}).get("price")
        if not item["price"] or (default_price and item["price"] < default_price * 0.4):
            item["price"] = default_price or 5000
        rng = price_range(item)
        if rng:
            item["price"] = min(max(item["price"], rng[0]), rng[1])
        by_name[key] = item
        items.append(item)
        if len(items) >= 8:
            break
    present = {kind_of(it) for it in items}
    for kind in required_kinds(room_type):
        if kind not in present:
            d = dict(DEFAULTS[kind])
            d["search_query"] = d["item"]
            d["qty"] = 1
            items.insert(0, d)
    if wishes:
        ensure_wished(items, wishes)
    if (workplace or "+office" in room_type) and room_type != "office":
        ensure_workplace(items)
    if "+" in room_type:
        add_divider(items, divider)
    items = keep_relevant(items, room_type, wishes, workplace or "+office" in room_type)
    for it in items:
        it["category"] = "furniture"
        it["unit"] = "шт"
        it["unit_price"] = it["price"]
        it["price"] = it["unit_price"] * it["qty"]
        it["shops"] = shop_links(it["search_query"], "furniture")
    return items


def ensure_workplace(items):
    desk = next((it for it in items if kind_of(it) == "стол"), None)
    if desk is None:
        desk = {"item": "Компьютерный стол", "type": "стол", "description": "Рабочее место у окна с местом под монитор и системный блок",
                "materials": "ЛДСП, металл", "dimensions": "120x75x60", "price": 12000, "qty": 1}
        items.append(desk)
    elif "компьют" not in desk["item"].lower():
        desk["item"] = "Компьютерный стол"
    desk["search_query"] = "компьютерный стол 120 см"
    desk["workplace"] = True
    if not any(kind_of(it) == "стул" or "кресл" in it["item"].lower() for it in items):
        items.append({"item": "Компьютерное кресло", "type": "стул", "description": "Эргономичное кресло с регулировкой высоты",
                      "materials": "сетка, пластик", "dimensions": "65x120x65", "price": 14000, "qty": 1,
                      "search_query": "компьютерное кресло эргономичное"})


FLOOR_WORDS = ("ламинат", "паркет", "плитк", "доск", "винил", "керамогранит", "линолеум", "ковролин", "пробк", "бетон", "микроцемент", "кварц")


def build_materials(design, room, style):
    floor = design.get("floor") if isinstance(design.get("floor"), dict) else {}
    walls = design.get("walls") if isinstance(design.get("walls"), dict) else {}
    floor_name = str(floor.get("name") or "Ламинат 33 класс, светлый дуб").strip()[:100]
    paint_name = str(walls.get("paint") or "Интерьерная моющаяся краска, тёплый белый").strip()[:100]
    if "краск" not in paint_name.lower():
        paint_name = f"Краска интерьерная моющаяся, {paint_name.lower()}"
    floor_price = int(sane(floor.get("price_per_m2"), 300, 15000, 1500))
    if not any(w in floor_name.lower() for w in FLOOR_WORDS):
        floor_name, floor_price = "Ламинат 33 класс, светлый дуб", 1300
    paint_price = int(sane(walls.get("price_per_liter"), 150, 5000, 700))

    floor_qty = math.ceil(room["area"] * 1.1)
    paint_qty = max(math.ceil(room["wall_area"] * 2 / 9), 1)
    plinth_qty = max(math.ceil(room["perimeter"] - 0.9), 1)

    if room["type"] == "bathroom":
        if not any(w in floor_name.lower() for w in ("керамогранит", "плитк")):
            floor_name, floor_price = "Керамогранит матовый 60x60", 1800
        tile_qty = math.ceil(room["wall_area"] * 1.1)
        materials = [
            {"item": floor_name, "type": "напольное покрытие", "qty": floor_qty, "unit": "м²", "unit_price": floor_price,
             "note": f"{room['area']} м² + 10% запас", "search_query": floor_name},
            {"item": "Плитка настенная керамическая", "type": "плитка", "qty": tile_qty, "unit": "м²", "unit_price": 1500,
             "note": f"стены {room['wall_area']} м² + 10% запас", "search_query": "плитка настенная для ванной " + style.lower()},
            {"item": "Плиточный клей и затирка", "type": "клей", "qty": math.ceil((tile_qty + floor_qty) / 5), "unit": "меш.", "unit_price": 650,
             "note": "мешок 25 кг на ~5 м²", "search_query": "плиточный клей 25 кг"},
        ]
        for m in materials:
            m["category"] = "materials"
            m["price"] = m["qty"] * m["unit_price"]
            m["shops"] = shop_links(m["search_query"], "materials")
        return materials

    materials = [
        {"item": floor_name, "type": "напольное покрытие", "qty": floor_qty, "unit": "м²", "unit_price": floor_price,
         "note": f"{room['area']} м² + 10% запас", "search_query": floor_name},
        {"item": paint_name, "type": "краска", "qty": paint_qty, "unit": "л", "unit_price": paint_price,
         "note": f"стены {room['wall_area']} м², 2 слоя", "search_query": paint_name},
        {"item": "Плинтус напольный в цвет пола", "type": "плинтус", "qty": plinth_qty, "unit": "м", "unit_price": 250,
         "note": f"периметр {room['perimeter']} м", "search_query": "плинтус напольный " + style.lower()},
    ]
    for m in materials:
        m["category"] = "materials"
        m["price"] = m["qty"] * m["unit_price"]
        m["shops"] = shop_links(m["search_query"], "materials")
    return materials


NAMED_COLORS = {
    "Белый": (245, 245, 243), "Молочный": (240, 234, 222), "Кремовый": (238, 226, 200), "Бежевый": (215, 195, 165),
    "Песочный": (196, 170, 130), "Светлый дуб": (200, 169, 126), "Орех": (140, 98, 62), "Тёмное дерево": (85, 58, 40),
    "Мокко": (120, 95, 80), "Светло-серый": (200, 200, 198), "Серый": (165, 165, 165), "Тёмно-серый": (110, 110, 110),
    "Графит": (60, 62, 66), "Розовый": (240, 190, 200), "Песочно-бежевый": (212, 197, 176),
    "Чёрный": (25, 25, 25), "Терракота": (190, 100, 70), "Кирпичный": (150, 70, 50), "Горчичный": (205, 160, 50),
    "Оливковый": (120, 125, 70), "Шалфей": (156, 175, 136), "Изумрудный": (40, 110, 80), "Тёмно-зелёный": (45, 70, 50),
    "Голубой": (170, 200, 220), "Серо-голубой": (120, 145, 165), "Синий": (50, 90, 170), "Тёмно-синий": (40, 55, 90),
    "Пудровый": (220, 185, 180), "Бордовый": (110, 35, 45), "Красный": (200, 50, 45), "Латунь": (180, 150, 80),
}


def color_name(hex_):
    rgb = tuple(int(hex_[k:k + 2], 16) for k in (1, 3, 5))
    return min(NAMED_COLORS, key=lambda n: sum((a - b) ** 2 for a, b in zip(NAMED_COLORS[n], rgb)))


def wall_color(design):
    walls = design.get("walls") if isinstance(design.get("walls"), dict) else {}
    hex_ = str(walls.get("color_hex") or "").strip()
    if re.fullmatch(r"#?[0-9a-fA-F]{6}", hex_):
        return ("#" + hex_.lstrip("#")).upper()
    return normalize_palette(design.get("palette"))[0]["hex"]


def normalize_palette(raw):
    palette, seen = [], set()
    for p in raw if isinstance(raw, list) else []:
        hex_ = str(p.get("hex") or "").strip() if isinstance(p, dict) else ""
        if not re.fullmatch(r"#?[0-9a-fA-F]{6}", hex_):
            continue
        hex_ = ("#" + hex_.lstrip("#")).upper()
        if hex_ in seen:
            continue
        seen.add(hex_)
        palette.append({"name": color_name(hex_), "hex": hex_})
    return palette[:5] if len(palette) >= 3 else DEFAULT_PALETTE


def psycho_room(room):
    return {
        "concept": "Абсолютная белизна. Белый диван и гипсовый конь, обращённый к нему. Больше ничего не нужно.",
        "palette": [{"name": "Белый", "hex": "#FFFFFF"}, {"name": "Ещё белее", "hex": "#FAFAFA"}],
        "lighting": "Ровный бестеневой свет со всех сторон.",
        "furniture": [
            {"item": "Белый диван", "type": "диван", "description": "Монолитный белый диван из микрофибры в абсолютной белизне",
             "materials": "микрофибра, белый каркас", "dimensions": "220x85x95", "price": 0, "qty": 1, "category": "furniture",
             "search_query": "белый диван", "shops": shop_links("белый диван")},
            {"item": "Статуя коня", "type": "статуя", "description": "Гипсовая статуя скачущего коня, обращённая к дивану",
             "materials": "гипс, белый пластик", "dimensions": "60x120x40", "price": 0, "qty": 1, "category": "furniture",
             "search_query": "гипсовая статуя коня", "shops": shop_links("гипсовая статуя коня")},
        ],
        "materials": [],
        "image_url": None,
        "easter_egg": True,
    }


def design_room(room, style, description, budget, single_room=False):
    own_wishes, general_wishes = wishes_for(room, description, single_room)
    desc = (description + " " + own_wishes).lower()
    if room["type"] == "living" and ("психодел" in desc or "psycho" in desc or random.random() < 1e-7):
        print("Выпала пасхалка Психодел!")
        return psycho_room(room), 0

    duration = 0
    design = {}
    try:
        raw_text, duration = ask_llm(build_prompt(room, style, own_wishes, general_wishes, budget))
        design = parse_design_json(raw_text)
        print(f"LLM: {len(raw_text)} символов, предметов: {len(design.get('furniture') or [])}")
    except Exception as e:
        print(f"LLM ошибка, используем базовый набор: {e}")

    data = {
        "concept": str(design.get("concept") or f"{style} интерьер с акцентом на функциональность и свет.").strip()[:600],
        "palette": normalize_palette(design.get("palette")),
        "wall_color": wall_color(design),
        "lighting": str(design.get("lighting") or "Общий потолочный свет + тёплая локальная подсветка зон.").strip()[:300],
        "furniture": normalize_furniture(design.get("furniture"), room_key(room),
                                         bool(WORKPLACE_RE.search(own_wishes.lower())), own_wishes or None, room.get("divider")),
        "materials": build_materials(design, room, style),
        "image_url": None,
        "wishes": own_wishes,
        "llm_ok": bool(design.get("furniture")),
        "_design": design,
    }
    return data, duration


@celery_app.task(bind=True)
def generate_design_task(self, user_id, rooms, style, description, budget=None, open_plan=False):
    started = datetime.utcnow()
    total_area = sum(r["width"] * r["length"] for r in rooms) or 1
    result_rooms = []
    llm_ns = 0

    for i, spec in enumerate(rooms):
        room = {"type": spec["type"], "width": spec["width"], "length": spec["length"], "height": spec["height"], "wishes": spec.get("wishes", "")}
        zone = spec.get("zone")
        if zone and zone != room["type"] and room["type"] in ZONABLE and zone in ZONABLE:
            room.update(zone=zone, divider=spec.get("divider") or "стеллаж")
        room.update(room_metrics(room["width"], room["length"], room["height"]))
        name = room_name(room)
        room_budget = budget * room["area"] / total_area * 0.8 if budget else None
        progress = {"room_index": i + 1, "room_total": len(rooms), "room_name": name}

        self.update_state(state="PROGRESS", meta={**progress, "stage": "text", "status": f"{name}: нейросеть проектирует..."})
        data, duration = design_room(room, style, description, room_budget, single_room=len(rooms) == 1)
        llm_ns += duration

        data.pop("_design", None)
        data.update({
            "room_type": room_key(room),
            "divider": room.get("divider"),
            "room_name": name,
            "room_dimensions": {"width": room["width"], "depth": room["length"], "height": room["height"]},
            "area": room["area"],
            "subtotal": sum(x["price"] for x in data["furniture"] + data["materials"]),
        })
        result_rooms.append(data)

    total = sum(r["subtotal"] for r in result_rooms)
    now = datetime.utcnow()
    result = {
        "status": "success",
        "model": f"{OLLAMA_MODEL} + SD",
        "task_id": self.request.id,
        "open_plan": bool(open_plan),
        "time_sec": str(round(llm_ns / 1e9, 1)) if llm_ns else str(round((now - started).total_seconds(), 1)),
        "date": f"{now.day:02d}.{now.month:02d}.{now.year} {now.hour:02d}:{now.minute:02d}",
        "user_id": user_id,
        "style": style,
        "description": description,
        "budget": budget,
        "total": total,
        "total_area": round(sum(r["area"] for r in result_rooms), 1),
        "rooms": result_rooms,
    }
    save_generation(self.request.id, result)
    return result


def save_generation(task_id, result):
    rooms = result["rooms"]
    db = SessionLocal()
    try:
        db.add(Generation(
            task_id=task_id,
            user_id=result["user_id"],
            room_type=rooms[0]["room_type"] if len(rooms) == 1 else "apartment",
            area=result["total_area"],
            height=rooms[0]["room_dimensions"]["height"],
            style=result["style"],
            description=result["description"],
            furniture_json=json.dumps([f for r in rooms for f in r["furniture"]], ensure_ascii=False),
            result_json=json.dumps(result, ensure_ascii=False),
            time_sec=result["time_sec"],
        ))
        db.commit()
    except Exception as e:
        print(f"Ошибка БД: {e}")
        db.rollback()
    finally:
        db.close()
