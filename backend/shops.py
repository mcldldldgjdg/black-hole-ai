from urllib.parse import quote_plus

STORES = {
    "ozon": {"name": "Ozon", "url": "https://www.ozon.ru/search/?text={q}"},
    "wb": {"name": "Wildberries", "url": "https://www.wildberries.ru/catalog/0/search.aspx?search={q}"},
    "market": {"name": "Яндекс Маркет", "url": "https://market.yandex.ru/search?text={q}"},
    "avito": {"name": "Авито", "url": "https://www.avito.ru/rossiya?q={q}"},
    "lemana": {"name": "Лемана ПРО", "url": "https://lemanapro.ru/search/?q={q}"},
}

CATEGORY_STORES = {
    "furniture": ["market", "ozon", "wb", "avito"],
    "materials": ["lemana", "market", "ozon"],
}


def shop_links(query, category="furniture"):
    q = quote_plus(query.strip())
    return [
        {"store": STORES[key]["name"], "url": STORES[key]["url"].format(q=q)}
        for key in CATEGORY_STORES.get(category, CATEGORY_STORES["furniture"])
    ]
