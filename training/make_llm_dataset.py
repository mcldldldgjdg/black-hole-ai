import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from prompts import REQUIRED, SYSTEM_PROMPT, build_prompt  # noqa: E402
from annotate import room_of  # noqa: E402

DATA = Path(__file__).parent / "data"
ROOM_TYPES = ["living", "bedroom", "kitchen", "office"]
ROOM_SIZE = {"living": ((3.8, 6.0), (3.4, 5.0)), "bedroom": ((3.0, 4.8), (2.8, 4.2)),
             "kitchen": ((2.6, 4.2), (2.2, 3.6)), "office": ((2.6, 4.0), (2.4, 3.4))}
HEIGHTS = [2.5, 2.6, 2.7, 2.7, 2.8, 3.0]
VARIANTS = 3

TYPES = {
    "диван": ("диван", "220x85x95", 45000), "кровать": ("кровать", "160x50x200", 42000), "шкаф": ("шкаф", "120x220x60", 32000),
    "стол": ("стол", "120x75x70", 16000), "столик": ("стол", "90x45x55", 9000), "стул": ("стул", "45x90x50", 6500),
    "кресло": ("кресло", "80x90x80", 18000), "тумба": ("тумба", "50x55x40", 7000), "телевизор": ("телевизор", "125x75x8", 45000),
    "стеллаж": ("стеллаж", "80x180x35", 12000), "лампа": ("лампа", "40x160x40", 6000), "торшер": ("лампа", "40x160x40", 7000),
    "ковёр": ("ковёр", "200x1x300", 12000), "ковер": ("ковёр", "200x1x300", 12000), "зеркало": ("зеркало", "60x150x3", 8000),
    "гарнитур": ("гарнитур", "240x220x60", 85000), "холодильник": ("холодильник", "60x185x65", 48000), "полка": ("стеллаж", "80x25x25", 3000),
}
REQUIRED_ITEMS = {
    "диван": ("Диван", "диван"), "шкаф": ("Шкаф", "шкаф"), "тв": ("Телевизор", "телевизор"), "кровать": ("Кровать двуспальная", "кровать"),
    "гарнитур": ("Кухонный гарнитур", "гарнитур"), "холодос": ("Холодильник", "холодильник"), "стол": ("Стол", "стол"), "стул": ("Стул", "стул"),
}
FLOOR_PRICES = [("паркет", 3500), ("доск", 4000), ("керамогранит", 2200), ("плитк", 1800), ("ламинат", 1300),
                ("линолеум", 700), ("ковролин", 900), ("винил", 1600), ("бетон", 2500)]


def item_kind(name, raw_type):
    text = f"{raw_type} {name}".lower()
    for key in TYPES:
        if key in text:
            return key
    return None


def furniture_from(ann, rng):
    items, seen = [], {}
    for m in ann["мебель"]:
        name = m["название"].strip()
        kind = item_kind(name, m["тип"])
        if not kind or not name:
            continue
        t, dims, price = TYPES[kind]
        color, materials = m["цвет"].strip().lower(), m["материалы"].strip().lower()
        title = name[:1].upper() + name[1:]
        if color and color not in title.lower():
            title = f"{title} {color}"
        key = title.lower()
        if key in seen:
            seen[key]["qty"] = min(seen[key]["qty"] + 1, 8)
            continue
        item = {"item": title[:60], "type": t, "description": f"{title}, {materials}"[:200], "materials": materials[:80],
                "dimensions": dims, "price": int(round(price * rng.uniform(0.8, 1.3), -2)), "qty": 1,
                "search_query": f"{name} {color} {materials}".strip()[:80]}
        seen[key] = item
        items.append(item)
    return items[:7]


def add_required(items, room_type):
    have = " ".join(f"{i['item']} {i['type']}".lower() for i in items)
    words = {"тв": "телевизор", "холодос": "холодильник"}
    for kind in REQUIRED[room_type]:
        if words.get(kind, kind) not in have:
            title, t = REQUIRED_ITEMS[kind]
            _, dims, price = TYPES[t if t in TYPES else "стол"]
            items.insert(0, {"item": title, "type": t, "description": title, "materials": "", "dimensions": dims,
                             "price": price, "qty": 1, "search_query": title})


def floor_of(text):
    low = text.lower()
    hit = next(((k, p) for k, p in FLOOR_PRICES if k in low), None)
    if not hit:
        return {"name": "Ламинат 33 класс, светлый дуб", "price_per_m2": 1300}
    return {"name": text.strip().rstrip(".")[:80], "price_per_m2": hit[1]}


def example(ann, rng):
    room_type = room_of(ann)
    (w0, w1), (l0, l1) = ROOM_SIZE[room_type]
    width, length = round(rng.uniform(w0, w1), 1), round(rng.uniform(l0, l1), 1)
    room = {"type": room_type, "width": width, "length": length, "area": round(width * length, 1), "height": rng.choice(HEIGHTS)}
    furniture = furniture_from(ann, rng)
    if not furniture:
        return None
    wished = rng.sample(furniture, k=min(len(furniture), rng.randint(0, 2)))
    own = ", ".join(w["item"].lower() for w in wished)
    general = rng.choice(["", "", "светлые тона", "есть кот", "больше мест для хранения", "много растений", "уютно и практично"])
    budget = rng.choice([None, None, rng.randrange(150_000, 600_000, 10_000)])
    add_required(furniture, room_type)
    walls = ann["стены"].split(",")[0].strip().rstrip(".")
    answer = {
        "concept": ann["концепция"].strip(),
        "palette": ann["palette"],
        "lighting": ann["освещение"].strip(),
        "floor": floor_of(ann["пол"]),
        "walls": {"paint": f"Краска интерьерная моющаяся, {walls.lower()}"[:100] if walls else "Краска интерьерная моющаяся, белая",
                  "color_hex": ann["palette"][0]["hex"], "price_per_liter": 700},
        "furniture": furniture,
        "image_prompt": ann["caption_en"].strip(),
    }
    return {"messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(room, ann["style"], own, general, budget)},
        {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)},
    ]}


def main():
    rng = random.Random(42)
    anns = [json.loads(line) for line in (DATA / "annotations.jsonl").open(encoding="utf-8")]
    usable = [a for a in anns if a["концепция"].strip() and room_of(a) in ROOM_TYPES]
    rng.shuffle(usable)
    n_val = max(1, len(usable) // 10)
    val = [e for e in (example(a, rng) for a in usable[:n_val]) if e]
    train = [e for a in usable[n_val:] for e in (example(a, rng) for _ in range(VARIANTS)) if e]
    rng.shuffle(train)
    rows = val + train
    n_val = len(val)
    out = DATA / "llm"
    out.mkdir(exist_ok=True)
    for name, part in (("val", rows[:n_val]), ("train", rows[n_val:])):
        with (out / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for r in part:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"примеров: {len(rows)} (train {len(rows) - n_val}, val {n_val}) из {len(anns)} разметок")


if __name__ == "__main__":
    main()
