ROOM_NAMES = {
    "living": "Гостиная",
    "bedroom": "Спальня",
    "kitchen": "Кухня",
    "office": "Кабинет",
    "bathroom": "Санузел",
    "custom": "Комната"
}
DIVIDERS = {
    "шкаф": {"item": "Шкаф-перегородка двусторонний", "type": "шкаф", "dimensions": "200x220x60", "price": 45000},
    "стеллаж": {"item": "Стеллаж-перегородка сквозной", "type": "стеллаж", "dimensions": "200x180x40", "price": 18000},
    "полка": {"item": "Книжная полка-перегородка", "type": "стеллаж", "dimensions": "180x150x30", "price": 12000},
}


def room_types(room):
    return [t for t in (room.get("type"), room.get("zone")) if t]


def room_key(room):
    return "+".join(room_types(room))


def room_name(room):
    names = [ROOM_NAMES.get(t, "Комната") for t in room_types(room)]
    return names[0] + "".join(" + " + n.lower() for n in names[1:])


def required_kinds(key):
    out = []
    for t in key.split("+"):
        out += [k for k in REQUIRED.get(t, []) if k not in out]
    return out

SYSTEM_PROMPT = "Ты опытный дизайнер интерьеров и сметчик. Отвечай только валидным JSON на русском языке."

REQUIRED = {
    "living": ["диван", "шкаф", "тв"],
    "bedroom": ["кровать", "шкаф"],
    "kitchen": ["гарнитур", "холодос", "стол"],
    "office": ["шкаф", "стол", "стул"],
    "bathroom": ["ванна", "унитаз", "раковина", "стиралка"],
}
REQUIRED_HINT = {
    "диван": "диван", "шкаф": "шкаф", "тв": "телевизор", "кровать": "кровать",
    "гарнитур": "кухонный гарнитур", "холодос": "холодильник", "стол": "стол", "стул": "стул",
    "ванна": "ванна или душевая", "унитаз": "унитаз", "раковина": "раковина с тумбой и зеркалом", "стиралка": "стиральная машина",
}
DESIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "concept": {"type": "string"},
        "palette": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "hex": {"type": "string"}}, "required": ["name", "hex"]}},
        "lighting": {"type": "string"},
        "floor": {"type": "object", "properties": {"name": {"type": "string"}, "price_per_m2": {"type": "number"}}, "required": ["name", "price_per_m2"]},
        "walls": {"type": "object", "properties": {"paint": {"type": "string"}, "color_hex": {"type": "string"}, "price_per_liter": {"type": "number"}}, "required": ["paint", "color_hex", "price_per_liter"]},
        "furniture": {"type": "array", "items": {"type": "object", "properties": {
            "item": {"type": "string"}, "type": {"type": "string"}, "description": {"type": "string"},
            "materials": {"type": "string"}, "dimensions": {"type": "string"}, "price": {"type": "number"},
            "qty": {"type": "integer"}, "search_query": {"type": "string"},
        }, "required": ["item", "type", "description", "materials", "dimensions", "price", "qty", "search_query"]}},
        "image_prompt": {"type": "string"},
    },
    "required": ["concept", "palette", "lighting", "floor", "walls", "furniture", "image_prompt"],
}


def build_prompt(room, style, own_wishes, general_wishes, budget):
    name = room_name(room)
    required = ", ".join(REQUIRED_HINT[k] for k in required_kinds(room_key(room)))
    budget_line = f"- Бюджет на мебель для этой комнаты: около {int(budget)} ₽\n" if budget else ""
    if room.get("zone"):
        divider = DIVIDERS.get(room.get("divider"), DIVIDERS["стеллаж"])["item"].lower()
        budget_line += f"- Комната зонирована: {name.lower()}, зоны разделены перегородкой — {divider}\n"
    if room["type"] == "bathroom":
        budget_line += "- Это совмещённый санузел: стены и пол — плитка. Мебель — ровно четыре предмета: ванна или душевая, унитаз, раковина с тумбой и зеркалом, стиральная машина\n"
    return (
        f"Спроектируй интерьер: {name.lower()}, стиль «{style}».\n\n"
        f"Обмеры:\n"
        f"- Размеры: {room['width']} x {room['length']} м, площадь {room['area']} м²\n"
        f"- Высота потолков: {room['height']} м\n"
        f"{budget_line}"
        f"- Пожелания к этому помещению: {own_wishes or 'нет'}\n"
        f"- Общие пожелания ко всей квартире: {general_wishes or 'нет'}\n"
        "  Обязательно включи всё, что перечислено в пожеланиях к помещению. Мебель других комнат сюда не добавляй.\n\n"
        "Верни JSON:\n"
        "- concept: 2-3 предложения — идея интерьера, зонирование, акценты\n"
        "- palette: 3-5 цветов {name, hex}\n"
        "- lighting: сценарий освещения (1-2 предложения)\n"
        "- floor: {name: конкретное покрытие пола, price_per_m2: цена за м² в рублях}\n"
        "- walls: {paint: краска и её цвет, color_hex, price_per_liter: цена за литр}\n"
        f"- furniture: 4-7 предметов, обязательно: {required or 'основная мебель'}. "
        "Для каждого: item (название), type (одно слово: диван, кровать, шкаф, стол, стул, кресло, тумба, телевизор, стеллаж, лампа, ковёр, зеркало, гарнитур, холодильник), "
        "description, materials, dimensions (ШxВxГ в см, например 200x90x80; у холодильника и шкафа высота самая большая), "
        "price (цена ОДНОЙ штуки в рублях, числом), qty (количество штук: 4 одинаковых стула — это один предмет с qty 4), "
        "search_query (запрос для поиска в интернет-магазине, например \"диван угловой серый велюр 220 см\")\n"
        "- image_prompt: короткое описание комнаты НА АНГЛИЙСКОМ для генерации фото\n\n"
        "Размеры мебели должны помещаться в комнату. Цены — реальные для российских магазинов."
    )
