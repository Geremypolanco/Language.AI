"""Faculty endpoints: the 5 selectable core teacher personas (language
practice) and portrait images for any persona, core or departmental (see
backend/personas.py). Portrait generation hits paid HF inference, so —
like backend/routers/content.py — this whole router sits behind "signed in"
rather than being reachable by anonymous traffic."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from .. import auth, personas
from ..hf_client import hf_client
from ..models import PersonaInfo

router = APIRouter(prefix="/api/personas", tags=["personas"], dependencies=[Depends(auth.require_session)])


@router.get("", response_model=list[PersonaInfo])
def list_core_teachers() -> list[PersonaInfo]:
    return [personas.to_persona_info(p) for p in personas.all_core_teachers()]


@router.get("/{persona_id}/portrait")
async def get_portrait(persona_id: str) -> Response:
    persona = personas.get_persona(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="Maestro no encontrado")
    image = await hf_client.generate_image(persona.portrait_prompt)
    if image is None:
        raise HTTPException(
            status_code=503, detail="Retrato no disponible — configura HF_TOKEN para generar los retratos del profesorado"
        )
    return Response(content=image, media_type="image/jpeg")
