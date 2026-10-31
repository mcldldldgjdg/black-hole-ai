import json
import math
import shutil
import sys
from pathlib import Path

from annotate import room_of

DATA = Path(__file__).parent / "data"
TRIGGER = "bhsinterior"
TARGET_STEPS_PER_EPOCH = 400

ROOM_EN = {"living": "living room", "bedroom": "bedroom", "kitchen": "kitchen", "office": "home office"}
STYLE_EN = {"Скандинавский": "scandinavian", "Лофт": "industrial loft", "Минимализм": "minimalist",
            "Неоклассика": "neoclassical", "Современный": "modern", "Japandi": "japandi"}


def caption(a):
    room = ROOM_EN.get(room_of(a)) or ROOM_EN.get(a["query_room"], "room")
    text = a["caption_en"].strip().rstrip(".")
    return f"{TRIGGER}, {STYLE_EN.get(a['style'], 'modern')} {room} interior, {text}, interior photography"


def main(batch_size=2):
    anns = [json.loads(line) for line in (DATA / "annotations.jsonl").open(encoding="utf-8")]
    good = [a for a in anns if not a["has_people"] and a["caption_en"].strip()]
    repeats = max(1, math.ceil(TARGET_STEPS_PER_EPOCH * batch_size / max(len(good), 1)))
    root = DATA / "sd" / "img"
    shutil.rmtree(DATA / "sd", ignore_errors=True)
    folder = root / f"{repeats}_{TRIGGER}"
    folder.mkdir(parents=True)
    for a in good:
        shutil.copy(DATA / "photos" / f"{a['id']}.jpg", folder / f"{a['id']}.jpg")
        (folder / f"{a['id']}.txt").write_text(caption(a), encoding="utf-8")
    print(f"фото: {len(good)} из {len(anns)}, повторов: {repeats}, папка: {folder}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
