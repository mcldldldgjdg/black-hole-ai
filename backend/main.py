from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from sqlalchemy.orm import Session
import os, json, httpx, re
from urllib.parse import unquote, quote

from database import Generation, User, get_db
from prompts import ROOM_NAMES
from tasks import celery_app, generate_design_task
import photo
import vision

app = FastAPI(title="Black Hole Studio AI", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ROOM_TYPE = Literal["living", "bedroom", "kitchen", "office", "bathroom", "custom"]
ROOM_KEY = Field(default="living", pattern=r"^[a-z]+(\+[a-z]+)?$", max_length=40)

class RoomSpec(BaseModel):
    type: ROOM_TYPE = "custom"
    zone: Optional[Literal["living", "bedroom", "office"]] = None
    divider: Literal["шкаф", "стеллаж", "полка"] = "стеллаж"
    width: float = Field(ge=1.2, le=15)
    length: float = Field(ge=1.2, le=15)
    height: float = Field(default=2.7, ge=2.0, le=5.0)
    wishes: str = Field(default="", max_length=500)

class DesignRequest(BaseModel):
    user_id: int
    rooms: List[RoomSpec] = Field(min_length=1, max_length=6)
    style: str = Field(max_length=40)
    budget: Optional[int] = Field(default=None, ge=0, le=100_000_000)
    description: str = Field(default="", max_length=1000)
    open_plan: bool = False

IMAGE_MAX = 12_000_000

class Box(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0.01, le=1)
    h: float = Field(gt=0.01, le=1)

class RoomsFromImage(BaseModel):
    image: str = Field(max_length=IMAGE_MAX)
    kind: Literal["plan", "photo"] = "plan"

class SuggestRequest(BaseModel):
    image: str = Field(max_length=IMAGE_MAX)
    box: Box
    style: str = Field(default="Современный", max_length=40)

class InpaintRequest(BaseModel):
    image: str = Field(max_length=IMAGE_MAX)
    prompt: str = Field(min_length=2, max_length=300)
    style: str = Field(default="Современный", max_length=40)
    box: Optional[Box] = None
    mask: Optional[str] = Field(default=None, max_length=IMAGE_MAX)

class RestyleRequest(BaseModel):
    image: str = Field(max_length=IMAGE_MAX)
    style: str = Field(default="Современный", max_length=40)
    prompt: str = Field(default="", max_length=300)
    room_type: ROOM_TYPE = "living"
    strength: float = Field(default=0.75, ge=0.3, le=0.95)
    mode: Literal["restyle", "furnish"] = "restyle"

class CameraInfo(BaseModel):
    x: float = Field(ge=-20, le=40)
    z: float = Field(ge=-20, le=40)
    tx: float = Field(ge=-20, le=40)
    tz: float = Field(ge=-20, le=40)
    hfov: float = Field(gt=0, lt=180)
    side: Optional[Literal["front", "back", "left", "right"]] = None

class RenderRequest(BaseModel):
    image: str = Field(max_length=IMAGE_MAX)
    depth: str = Field(max_length=IMAGE_MAX)
    style: str = Field(default="Современный", max_length=40)
    room_type: str = ROOM_KEY
    items: List[str] = Field(default=[], max_length=20)
    absent: List[str] = Field(default=[], max_length=20)
    task_id: Optional[str] = Field(default=None, max_length=64)
    room_index: int = Field(default=0, ge=0, le=5)
    camera: Optional[CameraInfo] = None
    version: int = Field(default=1, ge=1, le=100)
    wall_color: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    look: str = Field(default="", max_length=200)

class UserCreate(BaseModel):
    username: str

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
}

def clean(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s or '')).strip()

def decode_ddg(url):
    if 'uddg=' in url:
        m = re.search(r'uddg=([^&]+)', url)
        if m:
            return unquote(m.group(1))
    if url.startswith('//'):
        return 'https:' + url
    return url

def parse_ddg(html):
    out = []
    blocks = re.split(r'<div[^>]+class="result[^"]*"', html)[1:]
    for b in blocks:
        a = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', b, re.DOTALL)
        s = re.search(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', b, re.DOTALL)
        if a:
            url = decode_ddg(a.group(1))
            title = clean(a.group(2))
            if url and title and 'duckduckgo.com' not in url and len(title) > 3:
                out.append({"title": title[:140], "text": clean(s.group(1))[:200] if s else "", "url": url})
    return out

def parse_mojeek(html):
    out = []
    blocks = re.split(r'<li[^>]*class="result', html)[1:]
    for b in blocks:
        a = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', b, re.DOTALL)
        s = re.search(r'<p[^>]+class="s"[^>]*>(.*?)</p>', b, re.DOTALL)
        if a:
            url = a.group(1)
            title = clean(a.group(2))
            if url.startswith('http') and title and len(title) > 3:
                out.append({"title": title[:140], "text": clean(s.group(1))[:200] if s else "", "url": url})
    return out

def parse_bing(html):
    out = []
    blocks = re.split(r'<li[^>]*class="b_algo"', html)[1:]
    for b in blocks:
        a = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', b, re.DOTALL)
        s = re.search(r'<p[^>]*>(.*?)</p>', b, re.DOTALL)
        if a:
            url = a.group(1)
            title = clean(a.group(2))
            if url.startswith('http') and title and len(title) > 3:
                out.append({"title": title[:140], "text": clean(s.group(1))[:200] if s else "", "url": url})
    return out

SOURCES = [
    ("ddg", "https://html.duckduckgo.com/html/?q={q}&kl=ru-ru", parse_ddg),
    ("mojeek", "https://www.mojeek.com/search?q={q}", parse_mojeek),
    ("bing", "https://www.bing.com/search?q={q}&setlang=ru", parse_bing),
]

@app.get("/search")
async def search_furniture(q: str = Query(..., min_length=1, max_length=200)):
    results, seen = [], set()
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=HEADERS) as client:
        for name, tmpl, parser in SOURCES:
            if len(results) >= 8:
                break
            try:
                r = await client.get(tmpl.format(q=quote(q)))
                if r.status_code != 200:
                    print(f"{name}: HTTP {r.status_code}")
                    continue
                items = parser(r.text)
                added = 0
                for it in items:
                    if it["url"] in seen:
                        continue
                    seen.add(it["url"])
                    results.append(it)
                    added += 1
                    if len(results) >= 8:
                        break
                print(f"{name}: +{added} (всего {len(results)})")
            except Exception as e:
                print(f"{name}: {e}")
    return {"query": q, "results": results, "duckduckgo_url": f"https://duckduckgo.com/?q={quote(q)}&kl=ru-ru"}

@app.post("/users")
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    new_user = User(username=user.username)
    db.add(new_user); db.commit(); db.refresh(new_user)
    return {"id": new_user.id, "username": new_user.username}

@app.get("/users")
async def get_users(db: Session = Depends(get_db)):
    return [{"id": u.id, "username": u.username} for u in db.query(User).order_by(User.created_at.desc()).all()]

@app.delete("/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(status_code=404, detail="Пользователь не найден")
    db.delete(user); db.commit()
    return {"message": "Пользователь удалён"}

@app.post("/generate-design")
async def generate_design(request: DesignRequest, db: Session = Depends(get_db)):
    if not db.query(User).filter(User.id == request.user_id).first():
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    task = generate_design_task.delay(user_id=request.user_id, rooms=[r.model_dump() for r in request.rooms], style=request.style, description=request.description, budget=request.budget or None, open_plan=request.open_plan)
    return {"task_id": task.id, "status": "queued"}

@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    task = celery_app.AsyncResult(task_id)
    if task.state == "PENDING": return {"status": "queued", "message": "Задача в очереди"}
    elif task.state == "PROGRESS":
        info = task.info or {}
        return {"status": "processing", "message": info.get("status", "Обработка..."), "stage": info.get("stage"), "room_index": info.get("room_index"), "room_total": info.get("room_total")}
    elif task.state == "SUCCESS": return {"status": "completed", "result": task.result}
    elif task.state == "FAILURE": return {"status": "failed", "error": str(task.result)}
    return {"status": task.state}

@app.get("/history")
async def get_history(user_id: int = Query(None), db: Session = Depends(get_db)):
    if user_id is None: return []
    generations = db.query(Generation).filter(Generation.user_id == user_id).order_by(Generation.created_at.desc()).limit(20).all()
    return [history_item(gen) for gen in generations]

def history_item(gen):
    result = json.loads(gen.result_json) if gen.result_json else None
    rooms = result["rooms"] if result else []
    if len(rooms) > 1:
        room_name = f"Квартира · {len(rooms)} помещ."
    elif rooms:
        room_name = rooms[0]["room_name"]
    else:
        room_name = ROOM_NAMES.get(gen.room_type, "Комната")
    return {
        "id": gen.id, "user_id": gen.user_id, "username": gen.user.username if gen.user else "Unknown",
        "room_type": gen.room_type, "room_name": room_name, "area": gen.area, "height": gen.height,
        "style": gen.style, "description": gen.description or "",
        "furniture": json.loads(gen.furniture_json) if gen.furniture_json else [],
        "total": result.get("total") if result else None,
        "result": result,
        "time_sec": gen.time_sec,
        "date": f"{gen.created_at.day:02d}.{gen.created_at.month:02d}.{gen.created_at.year} {gen.created_at.hour:02d}:{gen.created_at.minute:02d}",
    }

@app.delete("/history/{generation_id}")
async def delete_generation(generation_id: int, db: Session = Depends(get_db)):
    generation = db.query(Generation).filter(Generation.id == generation_id).first()
    if not generation: raise HTTPException(status_code=404, detail="Запись не найдена")
    db.delete(generation); db.commit()
    return {"message": "Запись удалена"}

@app.delete("/history")
async def clear_history(user_id: int = Query(None), db: Session = Depends(get_db)):
    query = db.query(Generation)
    if user_id is not None: query = query.filter(Generation.user_id == user_id)
    query.delete(); db.commit()
    return {"message": "История очищена"}

async def run_model(coro):
    try:
        return await coro
    except Exception as e:
        print(f"Ошибка модели: {e}")
        raise HTTPException(status_code=502, detail=f"Нейросеть недоступна или не справилась: {e}")

@app.post("/vision/rooms")
async def rooms_from_image(req: RoomsFromImage):
    return await run_model(vision.extract_rooms(req.image, req.kind))

@app.post("/photo/suggest")
async def photo_suggest(req: SuggestRequest):
    return await run_model(vision.suggest_edits(req.image, req.box.model_dump(), req.style))

@app.post("/photo/inpaint")
async def photo_inpaint(req: InpaintRequest):
    if not req.box and not req.mask:
        raise HTTPException(status_code=422, detail="Выделите область на фото")
    box = req.box.model_dump() if req.box else None
    prompt = req.prompt
    if vision.CYRILLIC.search(prompt):
        prompt = (await run_model(vision.translate([prompt])))[0]
    return {"image": await run_model(photo.inpaint(req.image, prompt, req.style, box, req.mask))}

@app.post("/photo/restyle")
async def photo_restyle(req: RestyleRequest):
    room = photo.ROOM_NAMES_EN.get(req.room_type, "room")
    prompt = req.prompt
    if vision.CYRILLIC.search(prompt):
        prompt = (await run_model(vision.translate([prompt])))[0]
    return {"image": await run_model(photo.restyle(req.image, req.style, prompt, room, req.strength, req.mode))}

@app.post("/render-room")
async def render_room(req: RenderRequest, db: Session = Depends(get_db)):
    room = photo.room_en(req.room_type)
    items = [i[:80] for i in req.items]
    absent = [a[:40] for a in req.absent]
    image = await run_model(photo.render_from_3d(req.image, req.depth, req.style, room, items, absent, req.look))
    if req.task_id:
        gen = db.query(Generation).filter(Generation.task_id == req.task_id).first()
        if gen and gen.result_json:
            result = json.loads(gen.result_json)
            if req.room_index < len(result["rooms"]):
                result["rooms"][req.room_index]["image_url"] = image
                result["rooms"][req.room_index]["image_source"] = "3d"
                result["rooms"][req.room_index]["photo_camera"] = req.camera.model_dump() if req.camera else None
                result["rooms"][req.room_index]["photo_version"] = req.version
                if req.wall_color:
                    result["rooms"][req.room_index]["wall_color"] = req.wall_color.upper()
                gen.result_json = json.dumps(result, ensure_ascii=False)
                db.commit()
    return {"image": image}

@app.get("/health")
async def health_check(): return {"status": "ok", "service": "Black Hole Studio AI"}

@app.get("/")
async def serve_index():
    if os.path.isfile("/web2.html"): return FileResponse("/web2.html", media_type="text/html", headers={"Cache-Control": "no-cache"})
    raise HTTPException(status_code=404, detail="Frontend not found")

@app.get("/libs/{filename}")
async def serve_lib(filename: str):
    lib_path = f"/libs/{filename}"
    if os.path.isfile(lib_path):
        if filename.endswith('.js'): return FileResponse(lib_path, media_type="application/javascript")
        return FileResponse(lib_path)
    raise HTTPException(status_code=404, detail="Library not found")

if os.path.isdir("/static"):
    app.mount("/static", StaticFiles(directory="/static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
