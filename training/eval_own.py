import argparse
import base64
import io
import json
import time
from pathlib import Path

import httpx
from PIL import Image, ImageOps

API = "http://localhost:8000"
LABELS = {"спальня": "bedroom", "ванна": "bathroom", "санузел": "bathroom", "кухня": "kitchen",
          "гостиная": "living", "кабинет": "office", "коридор": "hallway", "вход": "hallway"}
AREA_RANGE = {"bedroom": (7, 30), "living": (12, 40), "kitchen": (5, 16), "office": (6, 20), "bathroom": (1.2, 7)}
ROOM_RU = {"bedroom": "спальня", "living": "гостиная", "kitchen": "кухня", "office": "кабинет",
           "bathroom": "санузел", "hallway": "коридор", None: "—"}


def label_of(path):
    head = path.stem.split("_")[0].lower()
    return LABELS.get(head)


def to_data_url(path, size=1024):
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def measure(client, path):
    started = time.time()
    r = client.post(f"{API}/vision/rooms", json={"image": to_data_url(path), "kind": "photo"})
    r.raise_for_status()
    data = r.json()
    room = (data.get("rooms") or [None])[0]
    return {
        "file": path.name,
        "label": label_of(path),
        "type": room and room["type"],
        "width": room and room["width"],
        "length": room and room["length"],
        "height": room and room["height"],
        "typical": bool(room and room.get("typical")),
        "skipped": data.get("skipped") or [],
        "notes": data.get("notes", ""),
        "seconds": round(time.time() - started, 1),
    }


def verdict(row):
    if row.get("error"):
        return False
    if row["label"] == "hallway":
        return row["type"] is None or row["type"] not in AREA_RANGE
    return row["type"] == row["label"]


def area_ok(row):
    lo, hi = AREA_RANGE.get(row["label"], (0, 0))
    return bool(row["width"]) and lo <= row["width"] * row["length"] <= hi


def report(rows, out_dir):
    rooms = [r for r in rows if r["label"] in AREA_RANGE]
    lines = ["# Проверка на реальных фото квартир", "",
             f"Фото: {len(rows)}, из них комнат: {len(rooms)}, коридоров: {len(rows) - len(rooms)}.", "",
             f"- тип комнаты угадан: {sum(verdict(r) for r in rooms)}/{len(rooms)}",
             f"- коридор не принят за комнату: {sum(verdict(r) for r in rows if r['label'] == 'hallway')}/{len(rows) - len(rooms)}",
             f"- размер оценён по самому фото: {sum(not r.get('typical') and bool(r['width']) for r in rooms)}/{len(rooms)}, "
             f"из них в реалистичных пределах: {sum(area_ok(r) and not r.get('typical') for r in rooms)}",
             f"- размер не определился, подставлен типичный для комнаты: {sum(bool(r.get('typical')) for r in rooms)}/{len(rooms)}",
             f"- среднее время ответа: {sum(r['seconds'] for r in rows) / max(len(rows), 1):.1f} с", "",
             "| Фото | Ожидалось | Распознано | Размеры, м | Площадь | Верно |", "|---|---|---|---|---|---|"]
    for r in rows:
        size = (f"{r['width']} × {r['length']}" + (" (типичный)" if r.get("typical") else "")) if r["width"] else "—"
        area = f"{r['width'] * r['length']:.1f} м²" if r["width"] else "—"
        mark = "✅" if verdict(r) and (r["label"] == "hallway" or area_ok(r)) else ("⚠️ размер" if verdict(r) else "❌")
        lines.append(f"| {r['file']} | {ROOM_RU[r['label']]} | {ROOM_RU.get(r['type'], r['type'])} | {size} | {area} | {mark} |")
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Проверка распознавания комнат на своих фото")
    parser.add_argument("--photos", default="data/own")
    parser.add_argument("--out", default="data/own_out")
    args = parser.parse_args()
    photos = sorted(p for p in Path(args.photos).iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png") and label_of(p))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    with httpx.Client(timeout=600) as client:
        for path in photos:
            try:
                rows.append(measure(client, path))
            except httpx.HTTPError as e:
                rows.append({"file": path.name, "label": label_of(path), "type": None, "width": None, "length": None,
                             "height": None, "skipped": [], "notes": f"ошибка: {e}", "seconds": 0, "error": True})
            print(path.name, "→", rows[-1]["type"], rows[-1]["width"], rows[-1]["length"], flush=True)
    report(rows, out_dir)


if __name__ == "__main__":
    main()
