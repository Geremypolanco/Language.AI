"""Vision Router — image generation (vocabulary flashcards, persona
portraits) and short topic-explainer video generation:

    Images -> Vision Router -> ideal model

Also owns the free real-photo-first fallback chain (Google Image Search,
then Wikimedia Commons) that used to be duplicated across
routers/content.py's endpoints — one method, `illustrate`, now used
everywhere an illustration is needed. See registry.py's
AITask.IMAGE_GENERATION/VIDEO_GENERATION for the actual provider chain."""

from __future__ import annotations

from ... import image_search
from ...hf_client import hf_client
from ..registry import AITask, chain_for


class VisionRouter:
    @property
    def active_chain(self):
        return chain_for(AITask.IMAGE_GENERATION)

    async def generate_image(self, prompt: str) -> bytes | None:
        return await hf_client.generate_image(prompt)

    async def generate_video(self, prompt: str) -> bytes | None:
        return await hf_client.generate_video(prompt)

    async def illustrate(self, prompt: str, *, skip_photo_search: bool = False) -> bytes | None:
        """Real photos first (cheaper, and often clearer for a general
        vocabulary flashcard than an AI illustration), AI generation as the
        fallback — the same chain routers/content.py's /image endpoint
        already used, now shared with every other caller instead of
        duplicated per-endpoint. `skip_photo_search=True` keeps callers that
        need a specific, crafted illustration (exercise art, teacher
        portraits) on AI generation only: a blind keyword photo search has
        no way to match those prompts (see routers/content.py's
        ImageRequest docstring for a concrete case where it picked the
        wrong "wave")."""
        if not skip_photo_search:
            image = await image_search.search_image(prompt)
            if image is None:
                image = await image_search.search_wikimedia_commons(prompt)
            if image is not None:
                return image
        return await self.generate_image(prompt)
