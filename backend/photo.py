import os

import httpx
from PIL import Image, ImageDraw, ImageFilter

from vision import box_pixels, decode_image, encode_image

SD_HOST = os.getenv("SD_HOST", "http://stable-diffusion:7860")
SD_TIMEOUT = httpx.Timeout(300.0, connect=5.0)
BASE_MODEL = os.getenv("SD_BASE_MODEL", "v1-5-pruned-emaonly.safetensors")
INPAINT_MODEL = os.getenv("SD_INPAINT_MODEL", "sd-v1-5-inpainting.ckpt")
STYLE_LORA = os.getenv("SD_STYLE_LORA", "")

STYLES_EN = {
    "Скандинавский": "scandinavian",
    "Лофт": "industrial loft",
    "Минимализм": "minimalist",
    "Неоклассика": "neoclassical",
    "Современный": "modern contemporary",
    "Japandi": "japandi",
}
ROOM_NAMES_EN = {"living": "living room", "bedroom": "bedroom", "kitchen": "kitchen", "office": "home office", "bathroom": "bathroom", "custom": "room"}


def room_en(key):
    parts = [ROOM_NAMES_EN.get(t, "room") for t in key.split("+")]
    return parts[0] + "".join(f" with {p} zone" for p in parts[1:])
NEGATIVE = "ugly, blurry, low quality, distorted, deformed, people, text, watermark, cartoon, drawing"
QUALITY = "interior photography, realistic, natural light, high detail"


def with_lora(prompt):
    return f"bhsinterior, {prompt}, <lora:{STYLE_LORA}:0.6>" if STYLE_LORA else prompt


def sd_size(img, max_side=768):
    img = img.copy()
    img.thumbnail((max_side, max_side))
    w, h = (img.width // 8) * 8, (img.height // 8) * 8
    return img.resize((w, h))


async def sd_img2img(payload):
    async with httpx.AsyncClient(timeout=SD_TIMEOUT) as client:
        r = await client.post(f"{SD_HOST}/sdapi/v1/img2img", json=payload)
    if r.status_code != 200:
        raise RuntimeError(f"Stable Diffusion {r.status_code}: {r.text[:200]}")
    images = r.json().get("images") or []
    if not images:
        raise RuntimeError("Stable Diffusion не вернул изображение")
    return "data:image/png;base64," + images[0]


def mask_from(img, box=None, mask_url=None):
    if mask_url:
        mask = decode_image(mask_url, max(img.size)).convert("L").resize(img.size)
        return mask.point(lambda v: 255 if v > 32 else 0)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rectangle(box_pixels(img, box), fill=255)
    return mask


async def inpaint(data_url, prompt, style, box=None, mask_url=None):
    img = sd_size(decode_image(data_url))
    mask = mask_from(img, box, mask_url).filter(ImageFilter.MaxFilter(9))
    return await sd_img2img({
        "init_images": [encode_image(img, "PNG")],
        "mask": encode_image(mask.convert("RGB"), "PNG"),
        "prompt": f"{prompt}, {STYLES_EN.get(style, 'modern')} style, {QUALITY}",
        "negative_prompt": NEGATIVE,
        "denoising_strength": 1.0,
        "inpainting_fill": 1,
        "inpaint_full_res": True,
        "inpaint_full_res_padding": 48,
        "mask_blur": 8,
        "steps": 28,
        "cfg_scale": 7,
        "width": img.width,
        "height": img.height,
        "override_settings": {"sd_model_checkpoint": INPAINT_MODEL},
    })


def controlnet_unit(module, model, weight, end=1.0):
    return {"enabled": True, "module": module, "model": model, "weight": weight, "guidance_end": end,
            "processor_res": 512, "control_mode": "Balanced", "pixel_perfect": True}


MLSD = "control_v11p_sd15_mlsd_fp16"
DEPTH = "control_v11f1p_sd15_depth_fp16"


async def restyle(data_url, style, prompt="", room_name="room", strength=0.75, mode="restyle"):
    img = sd_size(decode_image(data_url))
    if mode == "furnish":
        text = f"fully furnished {STYLES_EN.get(style, 'modern')} {room_name}, {prompt or 'furniture'}, cozy interior"
        units = [controlnet_unit("mlsd", MLSD, 0.55, end=0.6)]
        strength = max(strength, 0.9)
    else:
        text = f"{STYLES_EN.get(style, 'modern')} {room_name} interior, {prompt}".strip(", ")
        units = [controlnet_unit("mlsd", MLSD, 0.9), controlnet_unit("depth", DEPTH, 0.6)]
    return await sd_img2img({
        "init_images": [encode_image(img, "PNG")],
        "prompt": with_lora(f"{text}, {QUALITY}"),
        "negative_prompt": NEGATIVE,
        "denoising_strength": strength,
        "steps": 28,
        "cfg_scale": 7,
        "width": img.width,
        "height": img.height,
        "override_settings": {"sd_model_checkpoint": BASE_MODEL},
        "alwayson_scripts": {"controlnet": {"args": units}},
    })


async def render_from_3d(image_url, depth_url, style, room_name, items, absent, look=""):
    img = sd_size(decode_image(image_url))
    depth = decode_image(depth_url, max(img.size)).resize(img.size)
    furniture = ", ".join(items) if items else "furniture"
    prompt = f"{STYLES_EN.get(style, 'modern')} {room_name} interior with {furniture}" + (f", {look}" if look else "")
    return await sd_img2img({
        "init_images": [encode_image(img, "PNG")],
        "denoising_strength": 0.78,
        "prompt": with_lora(f"{prompt}, {QUALITY}, wide angle, balanced exposure, rich contrast"),
        "negative_prompt": ", ".join([NEGATIVE, "3d render, cgi, flat colors, overexposed, washed out, blown highlights, low contrast", *absent]),
        "steps": 30,
        "cfg_scale": 7,
        "width": img.width,
        "height": img.height,
        "override_settings": {"sd_model_checkpoint": BASE_MODEL},
        "alwayson_scripts": {"controlnet": {"args": [
            {"enabled": True, "module": "none", "model": DEPTH, "weight": 1.0, "guidance_end": 0.85,
             "image": encode_image(depth, "PNG"), "control_mode": "Balanced", "pixel_perfect": True},
            {"enabled": True, "module": "mlsd", "model": MLSD, "weight": 0.7, "guidance_end": 0.75,
             "image": encode_image(img, "PNG"), "processor_res": 512, "control_mode": "Balanced", "pixel_perfect": True},
        ]}},
    })
