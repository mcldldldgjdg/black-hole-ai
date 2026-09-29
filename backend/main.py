from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx
import os

app = FastAPI(title="Black Hole Studio AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RoomRequest(BaseModel):
    area: float
    height: float
    style: str
    description: str


@app.post("/generate-design")
async def generate_design(request: RoomRequest):
    prompt = (
        "Создай дизайн интерьера для комнаты:\n"
        f"- Площадь: {request.area} м²\n"
        f"- Высота потолков: {request.height} м\n"
        f"- Стиль: {request.style}\n"
        f"- Пожелания: {request.description}\n\n"
        "Опиши 5 ключевых предмета мебели в формате JSON.\n"
        "Используй только двойные кавычки для ключей и значений.\n"
        'Формат: {"furniture": [{"item": "название", "type": "тип", "description": "описание"}]}'
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:11434/api/generate",
                json={"model": "phi3.5", "prompt": prompt, "stream": False},
                timeout=120.0,
            )

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Ошибка генерации")

        result = response.json()
        return {
            "status": "success",
            "response": result["response"],
            "model": "phi3.5",
            "time": result.get("total_duration", 0),
        }

    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Black Hole Studio AI"}


@app.get("/")
async def serve_index():
    index_path = os.path.join(os.path.dirname(__file__), "..", "web2.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="Frontend not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
