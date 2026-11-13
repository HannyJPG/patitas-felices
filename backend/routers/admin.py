"""Router de Administración Clínica, CRM, Personal y Solicitudes."""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Header, HTTPException, Request

from ..schemas import (
    CambiarEstadoUsuarioRequest,
    CrearPersonalRequest,
    ResolverSolicitudMascotaRequest,
)
from .deps import manejar_proxy

router = APIRouter()


@router.get("/api/admin/crm", tags=["CRM y Administración"])
def resumen_crm(
    request: Request,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    demo: Optional[bool] = None,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["page_size"] = page_size
    if demo is not None:
        params["incluir_demo"] = demo
    return manejar_proxy(request, authorization, "ver_crm_dashboard", params)


@router.patch("/api/admin/usuarios/{usuario_id}/estado", tags=["CRM y Administración"])
def cambiar_estado_usuario_crm(
    usuario_id: int,
    cuerpo: CambiarEstadoUsuarioRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(
        request,
        authorization,
        "cambiar_estado_usuario",
        {"usuario_id": usuario_id, "estado": cuerpo.estado},
    )


@router.get("/api/admin/personal", tags=["CRM y Administración"])
def listar_personal_admin_crm(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(request, authorization, "listar_personal_admin")


@router.post("/api/admin/usuarios", tags=["CRM y Administración"])
@router.post("/api/admin/personal", tags=["CRM y Administración"])
def crear_personal_admin_crm(
    cuerpo: CrearPersonalRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    nombres_limpio = str(cuerpo.nombres or "").strip()
    apellidos_limpio = str(cuerpo.apellidos or "").strip()
    nombre_limpio = str(cuerpo.nombre or "").strip()
    if not nombre_limpio and (nombres_limpio or apellidos_limpio):
        nombre_limpio = f"{nombres_limpio} {apellidos_limpio}".strip()
    if len(nombre_limpio) < 2:
        raise HTTPException(
            status_code=400,
            detail="El nombre del personal debe tener al menos 2 caracteres.",
        )
    return manejar_proxy(
        request,
        authorization,
        "crear_personal_admin",
        {
            "nombre": nombre_limpio,
            "nombres": nombres_limpio,
            "apellidos": apellidos_limpio,
            "email": cuerpo.email,
            "password": cuerpo.password,
            "rol": cuerpo.rol,
            "telefono": cuerpo.telefono,
            "cmvp": cuerpo.cmvp,
            "especialidad": cuerpo.especialidad,
        },
    )


@router.get("/api/admin/solicitudes-mascotas", tags=["CRM y Administración"])
def ver_todas_solicitudes_mascotas(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(request, authorization, "gestionar_solicitudes_mascota")


@router.post("/api/admin/solicitudes-mascotas/{solicitud_id}/resolver", tags=["CRM y Administración"])
def resolver_solicitud_mascota(
    solicitud_id: int,
    cuerpo: ResolverSolicitudMascotaRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(
        request,
        authorization,
        "resolver_solicitud_mascota",
        {"solicitud_id": solicitud_id, "accion": cuerpo.accion},
    )
