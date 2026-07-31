"""The in-app library: a 500+ title catalog spanning every CEFR level and a
mix of genres. Catalog metadata (titles, genre, level, one-line blurb) is
free, static, and instantly available — built once at import time from
templates, no network call involved. The actual book *text* is what's
expensive (an HF chat-model generation), so it is created on first read and
cached to disk from then on (backend/hf_client.py's generate_book_content,
using the same lazy-generate-and-cache pattern already used there for vocab
images and TTS audio). This lets the catalog show 500+ real, browsable titles
immediately while never pre-paying to generate content nobody asked to read.
"""

from __future__ import annotations

import re

from .models import BookStub, CEFRLevel

_GENRES: dict[str, str] = {
    "adventure": "Aventura",
    "mystery": "Misterio",
    "romance": "Romance",
    "scifi": "Ciencia ficción",
    "fantasy": "Fantasía",
    "history": "Historia",
    "comedy": "Comedia",
    "horror": "Terror",
    "biography": "Biografía",
    "daily_life": "Vida cotidiana",
}

_TEMPLATES: dict[str, list[str]] = {
    "adventure": ["El tesoro de {x}", "La expedición a {x}", "Perdidos en {x}", "El mapa secreto de {x}", "Escape de {x}"],
    "mystery": ["El misterio de {x}", "El secreto de {x}", "¿Qué escondía {x}?", "La sombra de {x}", "El enigma de {x}"],
    "romance": ["Un amor en {x}", "Cartas desde {x}", "El reencuentro en {x}", "Bajo el cielo de {x}", "Dos corazones en {x}"],
    "scifi": ["La nave de {x}", "El último día de {x}", "Robots en {x}", "El futuro de {x}", "Viaje a {x}"],
    "fantasy": ["El reino de {x}", "La profecía de {x}", "El dragón de {x}", "La espada de {x}", "El hechizo de {x}"],
    "history": ["Los días de {x}", "La caída de {x}", "El imperio de {x}", "Crónicas de {x}", "El legado de {x}"],
    "comedy": ["Un día loco en {x}", "Enredos en {x}", "La boda en {x}", "Vacaciones en {x}", "Caos en {x}"],
    "horror": ["La casa de {x}", "La noche en {x}", "El eco de {x}", "Lo que acecha en {x}", "El pacto de {x}"],
    "biography": ["La vida de {x}", "El camino de {x}", "Recuerdos de {x}", "La historia de {x}", "El legado de {x}"],
    "daily_life": ["Un día en {x}", "Mi vecindario en {x}", "La rutina de {x}", "Café en {x}", "Cartas desde {x}"],
}

_FILL_INS: dict[str, list[str]] = {
    "adventure": ["la selva", "la montaña", "el desierto", "la isla", "el volcán", "el glaciar", "el cañón", "la cueva", "el archipiélago", "la jungla"],
    "mystery": ["el tren nocturno", "la mansión", "el faro", "el museo", "la biblioteca", "el hotel", "el barco", "la estación", "el teatro", "el pueblo"],
    "romance": ["París", "Roma", "Kyoto", "Lisboa", "Buenos Aires", "Nueva York", "el campo", "la costa", "el viñedo", "la ciudad vieja"],
    "scifi": ["Marte", "la estación espacial", "el año 2200", "una galaxia lejana", "la ciudad flotante", "el laboratorio", "la colonia lunar", "un androide", "la simulación", "el portal"],
    "fantasy": ["el bosque encantado", "la torre de cristal", "el valle perdido", "las montañas de hielo", "el castillo", "el desierto mágico", "la isla flotante", "el lago sagrado", "la ciudad dorada", "el árbol milenario"],
    "history": ["el imperio romano", "la revolución", "el reino antiguo", "la gran travesía", "la guerra olvidada", "la corte real", "el gran incendio", "la ruta de la seda", "los años dorados", "el nuevo mundo"],
    "comedy": ["la oficina", "la boda", "el aeropuerto", "el crucero", "la escuela", "el gimnasio", "el restaurante", "la mudanza", "el concurso", "el vecindario"],
    "horror": ["el bosque", "el hospital abandonado", "el pueblo fantasma", "el sótano", "el internado", "el cementerio", "la niebla", "el ático", "la carretera solitaria", "el espejo"],
    "biography": ["un explorador", "una científica", "un músico", "una pintora", "un inventor", "una atleta", "un escritor", "una activista", "un chef", "una maestra"],
    "daily_life": ["el barrio", "la ciudad", "el pueblo", "la universidad", "la oficina", "el mercado", "la playa", "el campo", "el edificio", "la cafetería"],
}

_LEVELS = list(CEFRLevel)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _contract(title: str) -> str:
    """Spanish contracts "de el" -> "del" and "a el" -> "al" — needed because
    titles are built by joining a preposition template with an independently
    chosen (masculine or feminine) noun phrase."""
    title = re.sub(r"\bde el\b", "del", title)
    title = re.sub(r"\ba el\b", "al", title)
    return title


def _build_catalog() -> list[BookStub]:
    stubs: list[BookStub] = []
    i = 0
    for genre, label in _GENRES.items():
        for template in _TEMPLATES[genre]:
            for fillin in _FILL_INS[genre]:
                title = _contract(template.format(x=fillin))
                level = _LEVELS[i % len(_LEVELS)]
                stubs.append(
                    BookStub(
                        id=f"{genre}-{_slugify(title)}-{i}",
                        title=title,
                        genre=genre,
                        genre_label=label,
                        level=level,
                        blurb=f"Una historia de {label.lower()} para nivel {level.value}.",
                    )
                )
                i += 1
    return stubs


CATALOG: list[BookStub] = _build_catalog()
GENRES: list[dict[str, str]] = [{"id": k, "label": v} for k, v in _GENRES.items()]


def get_book_stub(book_id: str) -> BookStub | None:
    return next((b for b in CATALOG if b.id == book_id), None)


def catalog_for(level: CEFRLevel | None = None, genre: str | None = None) -> list[BookStub]:
    items = CATALOG
    if level:
        items = [b for b in items if b.level == level]
    if genre:
        items = [b for b in items if b.genre == genre]
    return items


def build_book_generation_prompt(stub: BookStub, target_lang: str, native_lang: str) -> str:
    return (
        f"Write a short story titled \"{stub.title}\" entirely in {target_lang}. "
        f"Genre: {stub.genre_label} (in {native_lang}). "
        f"Difficulty: CEFR level {stub.level.value} — use vocabulary and sentence "
        f"complexity appropriate for that level (very simple, high-frequency words and "
        f"short sentences for A1/A2; progressively richer grammar and vocabulary at "
        f"higher levels). Length: 6 to 10 short paragraphs. "
        f"Output ONLY the story text in {target_lang} — no title repetition, no "
        f"translation, no meta-commentary, no markdown headers."
    )
