import io
import json
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

DATA = Path(__file__).parent / "data"
PHOTOS = DATA / "photos"
META = DATA / "photos.jsonl"
API = "https://api.openverse.org/v1/images/"
LICENSES = "cc0,pdm,by,by-sa"
MIN_SIDE = 700
MAX_SIDE = 1024

ROOMS = {
    "living": ["living room", "living room interior", "lounge interior", "sofa living room"],
    "bedroom": ["bedroom", "bedroom interior", "bed room design"],
    "kitchen": ["kitchen interior", "modern kitchen", "kitchen design"],
    "office": ["home office", "study room interior", "workspace interior"],
}
STYLES = ["scandinavian", "loft", "industrial", "minimalist", "modern", "classic", "japandi", "cozy"]
EXTRA = {
    "living": ["apartment interior", "flat interior", "home interior design", "интерьер гостиной", "интерьер квартиры", "гостиная"],
    "bedroom": ["bedroom apartment", "master bedroom", "интерьер спальни", "спальня"],
    "kitchen": ["apartment kitchen", "kitchen dining", "интерьер кухни", "кухня в квартире"],
    "office": ["home workspace desk", "домашний кабинет", "рабочее место дома"],
}


def queries(only_extra=False):
    for room, base in ROOMS.items():
        if not only_extra:
            for q in base:
                yield room, q
            for style in STYLES:
                yield room, f"{style} {base[0]}"
        for q in EXTRA[room]:
            yield room, q


def search(client, q, page):
    params = {"q": q, "license": LICENSES, "category": "photograph", "mature": "false", "page_size": 20, "page": page}
    for attempt in range(4):
        r = client.get(API, params=params)
        if r.status_code == 429:
            time.sleep(60 * (attempt + 1))
            continue
        if r.status_code != 200:
            return []
        return r.json().get("results", [])
    return []


def fetch_image(client, url):
    r = client.get(url, follow_redirects=True)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    if min(img.size) < MIN_SIDE:
        raise ValueError("слишком маленькое")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return img


def main(only_extra=False, pages=6):
    PHOTOS.mkdir(parents=True, exist_ok=True)
    seen = set()
    if META.exists():
        seen = {json.loads(line)["id"] for line in META.open(encoding="utf-8")}
    titles = set()
    with httpx.Client(timeout=60, headers={"User-Agent": "black-hole-studio-coursework/1.0"}) as client, META.open("a", encoding="utf-8") as out:
        for room, q in queries(only_extra):
            for page in range(1, pages + 1):
                results = search(client, q, page)
                if not results:
                    break
                for it in results:
                    key = (it.get("title") or "").lower().strip()
                    if it["id"] in seen or (key and key in titles):
                        continue
                    if (it.get("width") or 0) and min(it["width"], it.get("height") or 0) < MIN_SIDE:
                        continue
                    try:
                        img = fetch_image(client, it["url"])
                    except Exception:
                        continue
                    img.save(PHOTOS / f"{it['id']}.jpg", quality=92)
                    seen.add(it["id"])
                    titles.add(key)
                    out.write(json.dumps({
                        "id": it["id"], "room": room, "query": q, "title": it.get("title"),
                        "tags": [t["name"] for t in it.get("tags") or []][:20],
                        "license": it.get("license"), "license_url": it.get("license_url"),
                        "creator": it.get("creator"), "source": it.get("source"),
                        "landing_url": it.get("foreign_landing_url"), "attribution": it.get("attribution"),
                    }, ensure_ascii=False) + "\n")
                    out.flush()
                print(f"{q} стр.{page}: всего {len(seen)}", flush=True)


if __name__ == "__main__":
    main(only_extra="--extra" in sys.argv)
