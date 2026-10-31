import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from prompts import DESIGN_SCHEMA, REQUIRED, SYSTEM_PROMPT  # noqa: E402

DATA = Path(__file__).parent / "data"
OLLAMA = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODELS = sys.argv[1:] or ["qwen2.5:3b", "bhs-designer"]
KIND_WORDS = {"диван": "диван", "шкаф": "шкаф", "тв": "телевиз", "кровать": "кроват", "гарнитур": "гарнитур",
              "холодос": "холодильн", "стол": "стол", "стул": "стул"}
TYPICAL = {"диван": 45000, "кроват": 42000, "шкаф": 32000, "стол": 16000, "стул": 6500, "кресл": 18000,
           "телевиз": 45000, "гарнитур": 85000, "холодильн": 48000, "тумб": 7000}


def room_type_of(prompt):
    for t, name in (("living", "гостиная"), ("bedroom", "спальня"), ("kitchen", "кухня"), ("office", "кабинет")):
        if f"интерьер: {name}" in prompt:
            return t
    return "living"


def wishes_of(prompt):
    m = re.search(r"Пожелания к этому помещению: (.*)", prompt)
    text = m.group(1).strip() if m else "нет"
    return [] if text == "нет" else [w.strip() for w in text.split(",") if w.strip()]


def score(prompt, text):
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        return {"json_ok": 0}
    items = [f for f in d.get("furniture") or [] if isinstance(f, dict)]
    names = " ".join(f"{f.get('item', '')} {f.get('type', '')}".lower() for f in items)
    need = REQUIRED[room_type_of(prompt)]
    wishes = wishes_of(prompt)
    palette = [p for p in d.get("palette") or [] if isinstance(p, dict) and re.fullmatch(r"#[0-9A-Fa-f]{6}", str(p.get("hex", "")))]
    concept = str(d.get("concept") or "")
    cyr = len(re.findall(r"[а-яё]", concept, re.I)) / max(1, len(re.findall(r"[a-zа-яё]", concept, re.I)))
    priced = []
    for f in items:
        key = next((k for k in TYPICAL if k in f"{f.get('item', '')} {f.get('type', '')}".lower()), None)
        if key and isinstance(f.get("price"), (int, float)):
            priced.append(0.4 * TYPICAL[key] <= f["price"] <= 2.5 * TYPICAL[key])
    return {
        "json_ok": 1,
        "required_ok": int(all(KIND_WORDS[k] in names for k in need)),
        "wishes_ok": sum(w.split()[0].lower()[:5] in names for w in wishes) / len(wishes) if wishes else None,
        "palette_ok": int(3 <= len(palette) <= 5),
        "russian_ok": int(cyr > 0.8),
        "prices_ok": sum(priced) / len(priced) if priced else None,
        "furniture_n": len(items),
    }


def run(model, prompt):
    t = time.time()
    r = httpx.post(f"{OLLAMA}/api/generate", timeout=600, json={
        "model": model, "system": SYSTEM_PROMPT, "prompt": prompt, "format": DESIGN_SCHEMA, "stream": False,
        "options": {"temperature": 0.6, "num_ctx": 4096, "num_predict": 2048, "seed": 1},
    })
    r.raise_for_status()
    return r.json()["response"], time.time() - t


def mean(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def main():
    val = [json.loads(line) for line in (DATA / "llm" / "val.jsonl").open(encoding="utf-8")]
    report = {}
    for model in MODELS:
        rows = []
        for ex in val:
            prompt = ex["messages"][1]["content"]
            text, sec = run(model, prompt)
            rows.append({**score(prompt, text), "sec": sec})
        report[model] = {k: mean(rows, k) for k in ("json_ok", "required_ok", "wishes_ok", "palette_ok", "russian_ok", "prices_ok", "furniture_n", "sec")}
        print(model, report[model], flush=True)
    out = DATA / "out" / "llm" / "eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"examples": len(val), "models": report}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
