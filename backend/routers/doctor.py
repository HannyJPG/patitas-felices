"""Router de Agenda e Historial Clínico para Médicos Veterinarios."""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Header, Request

from ..schemas import ActualizarCitaDoctorRequest
from .deps import manejar_proxy

router = APIRouter()


# --- Endpoints clínicos protegidos para médicos veterinarios ---
@router.get("/api/doctor/agenda", tags=["Agenda e Historial (Doctor)"])
def ver_agenda_doctor(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Devuelve citas asignadas y perfil profesional del doctor autenticado."""
    return manejar_proxy(request, authorization, "ver_agenda_doctor")


@router.patch("/api/doctor/citas/{cita_id}", tags=["Agenda e Historial (Doctor)"])
def actualizar_cita_clinica(
    cita_id: int,
    cuerpo: ActualizarCitaDoctorRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Actualiza estado, diagnóstico y tratamiento clínico en dbo.Cita y dbo.Historial_clinico."""
    return manejar_proxy(
        request,
        authorization,
        "actualizar_diagnostico",
        {
            "cita_id": cita_id,
            "estado": cuerpo.estado,
            "diagnostico": cuerpo.diagnostico,
            "tratamiento": cuerpo.tratamiento,
        },
    )
