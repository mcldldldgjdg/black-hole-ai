import base64
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

DATA = Path(__file__).parent / "data"
OLLAMA = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.getenv("VISION_MODEL", "qwen2.5vl:3b")
STYLES = ["Скандинавский", "Лофт", "Минимализм", "Неоклассика", "Современный", "Japandi"]
ROOMS = ["living", "bedroom", "kitchen", "office", "other"]

STYLE_HINTS = {
    "Скандинавский": "светлое дерево, белые стены, текстиль, уют",
    "Лофт": "кирпич, бетон, металл, открытые коммуникации",
    "Минимализм": "очень мало предметов, гладкие поверхности, монохром",
    "Неоклассика": "молдинги, симметрия, классическая мебель, благородные цвета",
    "Современный": "гладкие формы, нейтральные цвета, смесь материалов",
    "Japandi": "низкая мебель, натуральное дерево и камень, японская сдержанность",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "has_people": {"type": "boolean"},
        "концепция": {"type": "string", "maxLength": 400},
        "освещение": {"type": "string", "maxLength": 200},
        "пол": {"type": "string", "maxLength": 100},
        "стены": {"type": "string", "maxLength": 120},
        "мебель": {"type": "array", "maxItems": 10, "items": {"type": "object", "properties": {
            "название": {"type": "string", "maxLength": 60}, "тип": {"type": "string", "maxLength": 20},
            "материалы": {"type": "string", "maxLength": 60}, "цвет": {"type": "string", "maxLength": 30},
        }, "required": ["название", "тип", "материалы", "цвет"]}},
        "room_type": {"type": "string", "enum": ROOMS},
        "style": {"type": "string", "enum": STYLES},
        "caption_en": {"type": "string", "maxLength": 300},
    },
    "required": ["has_people", "room_type", "style", "caption_en", "концепция", "освещение", "пол", "стены", "мебель"],
}

PROMPT = (
    "Опиши интерьер на фото.\n"
    "has_people — есть ли на фото люди.\n"
    f"room_type — одно из: {', '.join(ROOMS)}.\n"
    "style — выбери по признакам из описанного выше (если признаки не очевидны — Современный):\n" + "\n".join(f"- {k}: {v}" for k, v in STYLE_HINTS.items()) + "\n"
    "caption_en — ПО-АНГЛИЙСКИ одно предложение: стиль, комната, главная мебель, материалы, цвета, свет.\n"
    "Все остальные поля — ТОЛЬКО ПО-РУССКИ: концепция — 2 предложения об идее интерьера и зонировании; "
    "освещение — какой свет; пол — материал напольного покрытия под коврами (паркет, ламинат, доска, плитка, керамогранит, бетон, винил) и его цвет; "
    "стены — отделка и цвет стен (коротко); "
    "мебель — все заметные предметы мебели и техники: название, тип (одно слово: диван, кровать, шкаф, стол, стул, "
    "кресло, тумба, телевизор, стеллаж, лампа, ковёр, зеркало, гарнитур, холодильник), материалы, цвет."
)

NAMED_COLORS = {
    "Белый": (245, 245, 243), "Молочный": (240, 234, 222), "Кремовый": (238, 226, 200), "Бежевый": (215, 195, 165),
    "Песочный": (196, 170, 130), "Светлый дуб": (200, 169, 126), "Орех": (140, 98, 62), "Тёмное дерево": (85, 58, 40),
    "Мокко": (120, 95, 80), "Светло-серый": (200, 200, 198), "Серый": (140, 140, 140), "Графит": (60, 62, 66),
    "Чёрный": (25, 25, 25), "Терракота": (190, 100, 70), "Кирпичный": (150, 70, 50), "Горчичный": (205, 160, 50),
    "Оливковый": (120, 125, 70), "Шалфей": (156, 175, 136), "Изумрудный": (40, 110, 80), "Тёмно-зелёный": (45, 70, 50),
    "Голубой": (170, 200, 220), "Серо-голубой": (120, 145, 165), "Тёмно-синий": (40, 55, 90), "Пудровый": (220, 185, 180),
    "Бордовый": (110, 35, 45), "Латунь": (180, 150, 80),
}


def room_of(ann):
    has_bed = any("кроват" in f"{m['название']} {m['тип']}".lower() for m in ann["мебель"])
    if ann["room_type"] == "bedroom" and not has_bed:
        return ann["query_room"]
    return ann["room_type"]


def palette(img, k=5):
    px = np.asarray(img.convert("RGB").resize((80, 80)), dtype=np.float32).reshape(-1, 3)
    rng = np.random.default_rng(0)
    centers = px[rng.choice(len(px), k, replace=False)]
    for _ in range(15):
        labels = np.argmin(((px[:, None] - centers[None]) ** 2).sum(-1), axis=1)
        centers = np.array([px[labels == i].mean(0) if (labels == i).any() else centers[i] for i in range(k)])
    sizes = np.bincount(labels, minlength=k)
    out, used = [], set()
    for i in np.argsort(-sizes):
        rgb = centers[i]
        name = min(NAMED_COLORS, key=lambda n: sum((a - b) ** 2 for a, b in zip(NAMED_COLORS[n], rgb)))
        if name in used:
            continue
        used.add(name)
        out.append({"name": name, "hex": "#%02X%02X%02X" % tuple(int(c) for c in rgb)})
    return out


def ask(img):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    image = base64.b64encode(buf.getvalue()).decode()
    for temperature in (0, 0.3, 0.6):
        r = httpx.post(f"{OLLAMA}/api/generate", timeout=300, json={
            "model": MODEL, "prompt": PROMPT, "images": [image], "format": SCHEMA, "stream": False, "keep_alive": "10m",
            "options": {"temperature": temperature, "num_ctx": 4096, "num_predict": 1200},
        })
        r.raise_for_status()
        data = r.json()
        if data.get("done") and data.get("response"):
            return json.loads(data["response"])
    raise RuntimeError(data.get("error") or "пустой ответ модели")


def restart_ollama():
    subprocess.run(["docker", "restart", os.getenv("OLLAMA_CONTAINER", "ollama-bhs")], check=True, capture_output=True)
    for _ in range(60):
        try:
            httpx.get(f"{OLLAMA}/api/version", timeout=2)
            return
        except httpx.HTTPError:
            time.sleep(1)


def main(limit=None):
    out_path = DATA / "annotations.jsonl"
    done = set()
    if out_path.exists():
        done = {json.loads(line)["id"] for line in out_path.open(encoding="utf-8")}
    photos = [json.loads(line) for line in (DATA / "photos.jsonl").open(encoding="utf-8")]
    todo = [p for p in photos if p["id"] not in done][:limit]
    with out_path.open("a", encoding="utf-8") as out:
        for n, meta in enumerate(todo, 1):
            img = Image.open(DATA / "photos" / f"{meta['id']}.jpg").convert("RGB")
            small = img.copy()
            small.thumbnail((768, 768))
            try:
                ann = ask(small)
            except Exception:
                restart_ollama()
                try:
                    ann = ask(small)
                except Exception as e:
                    print(f"{meta['id']}: ошибка {e}", flush=True)
                    continue
            ann["palette"] = palette(img)
            ann["id"] = meta["id"]
            ann["query_room"] = meta["room"]
            out.write(json.dumps(ann, ensure_ascii=False) + "\n")
            out.flush()
            print(f"[{n}/{len(todo)}] {meta['id']}: {ann['room_type']} / {ann['style']} / люди={ann['has_people']}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
