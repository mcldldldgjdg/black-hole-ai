import base64
import io
import os
import sys
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

SD = os.getenv("SD_HOST", "http://localhost:7860")
LORA = sys.argv[1] if len(sys.argv) > 1 else "bhs_interior"
WEIGHT = float(sys.argv[2]) if len(sys.argv) > 2 else 0.6
OUT = Path(__file__).parent / "data" / "out" / "sd"
PROMPTS = [
    "scandinavian living room interior, sofa, coffee table, window",
    "industrial loft bedroom interior, bed, brick wall",
    "modern kitchen interior, kitchen cabinets, dining table, chairs",
    "japandi home office interior, wooden desk, chair, shelves",
]
NEGATIVE = "ugly, blurry, low quality, distorted, people, text, watermark"
SIZE = (512, 384)


def generate(prompt, seed):
    r = httpx.post(f"{SD}/sdapi/v1/txt2img", timeout=300, json={
        "prompt": f"{prompt}, interior photography, natural light", "negative_prompt": NEGATIVE,
        "steps": 25, "cfg_scale": 7, "width": SIZE[0], "height": SIZE[1], "seed": seed,
        "override_settings": {"sd_model_checkpoint": "v1-5-pruned-emaonly.safetensors"},
    })
    r.raise_for_status()
    return Image.open(io.BytesIO(base64.b64decode(r.json()["images"][0])))


def main():
    w, h = SIZE
    label_h = 28
    grid = Image.new("RGB", (w * 2, (h + label_h) * len(PROMPTS)), "white")
    draw = ImageDraw.Draw(grid)
    for row, prompt in enumerate(PROMPTS):
        y = row * (h + label_h)
        base = generate(prompt, 1000 + row)
        tuned = generate(f"bhsinterior, {prompt}, <lora:{LORA}:{WEIGHT}>", 1000 + row)
        grid.paste(base, (0, y + label_h))
        grid.paste(tuned, (w, y + label_h))
        draw.text((6, y + 8), f"SD 1.5: {prompt[:60]}", fill="black")
        draw.text((w + 6, y + 8), f"SD 1.5 + LoRA {LORA}:{WEIGHT}", fill="black")
        print(f"{row + 1}/{len(PROMPTS)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"compare_{LORA}_{WEIGHT}.jpg"
    grid.save(path, quality=90)
    print(path)


if __name__ == "__main__":
    main()
