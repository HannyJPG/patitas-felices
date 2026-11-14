"""Router de Citas, WhatsApp Adapter y Portal del Cliente."""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Header, HTTPException, Request

from ..patterns import (
    ErrorConexionSQLServer,
    ErrorConsultaSQLServer,
    ErrorRegistroDuplicadoSQLServer,
)
from ..schemas import (
    ActualizarDocumentoRequest,
    CitaRequest,
    CrearMascotaRequest,
    DisponibilidadHorariosResponse,
    SolicitarCambioMascotaRequest,
)
from .deps import manejar_proxy

router = APIRouter()


# --- Disponibilidad y registro de citas (clientes autenticados o invitados) ---
@router.get("/api/citas/disponibilidad", tags=["Citas y WhatsApp (Adapter)"], response_model=DisponibilidadHorariosResponse)
def consultar_disponibilidad_citas(fecha: str, request: Request) -> Dict[str, Any]:
    """
    Consulta la disponibilidad de cupos por turno (máximo 3 citas por horario correspondientes a los 3 doctores).
    """
    adaptador_bd = request.app.state.db
    try:
        return adaptador_bd.obtener_disponibilidad_horarios(fecha)
    except ErrorConexionSQLServer as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ErrorConsultaSQLServer as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error consultando disponibilidad: {exc}") from exc


@router.post("/api/citas", tags=["Citas y WhatsApp (Adapter)"])
def registrar_cita(
    solicitud: CitaRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    adaptador_bd = request.app.state.db
    adaptador_whatsapp = request.app.state.whatsapp
    datos = solicitud.model_dump()
    whatsapp_url = adaptador_whatsapp.generar_enlace_cita(datos)
    datos["whatsapp_url"] = whatsapp_url

    try:
        if authorization:
            resultado = manejar_proxy(request, authorization, "agendar_cita", datos)
            cita = resultado["cita"]
        else:
            datos["usuario_id"] = None
            cita = adaptador_bd.crear_cita(datos)
    except HTTPException:
        raise
    except ErrorConexionSQLServer as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, ErrorRegistroDuplicadoSQLServer) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ErrorConsultaSQLServer as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "mensaje": "Cita registrada y adaptada para WhatsApp exitosamente.",
        "cita": cita,
        "whatsapp_url": whatsapp_url,
    }


# --- Gestión del portal del cliente (citas, mascotas, documento, compras y solicitudes) ---
@router.get("/api/cliente/mis-citas", tags=["Citas y WhatsApp (Adapter)"])
def obtener_mis_citas(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(request, authorization, "ver_mis_citas")


@router.get("/api/cliente/mis-mascotas", tags=["Espacio del Cliente"])
def listar_mis_mascotas(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(request, authorization, "ver_mis_mascotas")


@router.post("/api/cliente/mascotas", tags=["Espacio del Cliente"])
def registrar_mascota_cliente(
    cuerpo: CrearMascotaRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(
        request,
        authorization,
        "crear_mascota_cliente",
        cuerpo.model_dump(),
    )


@router.delete("/api/cliente/mascotas/{mascota_id}", tags=["Espacio del Cliente"])
def eliminar_mascota_cliente(
    mascota_id: int,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(
        request,
        authorization,
        "eliminar_mascota_cliente",
        {"mascota_id": mascota_id},
    )


@router.post("/api/cliente/documento", tags=["Espacio del Cliente"])
def registrar_documento_cliente(
    cuerpo: ActualizarDocumentoRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(
        request,
        authorization,
        "actualizar_documento_cliente",
        {"tipo_documento": cuerpo.tipo_documento, "documento": cuerpo.documento},
    )


@router.get("/api/cliente/mis-compras", tags=["Espacio del Cliente"])
def ver_mis_compras(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(request, authorization, "ver_mis_compras")


@router.post("/api/cliente/mascotas/{mascota_id}/solicitar-cambio", tags=["Espacio del Cliente"])
def solicitar_cambio_mascota(
    mascota_id: int,
    cuerpo: SolicitarCambioMascotaRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(
        request,
        authorization,
        "solicitar_cambio_mascota",
        {
            "mascota_id": mascota_id,
            "tipo": cuerpo.tipo,
            "motivo": cuerpo.motivo,
            "datos_nuevos": cuerpo.datos_nuevos,
        },
    )


@router.get("/api/cliente/solicitudes", tags=["Espacio del Cliente"])
def ver_mis_solicitudes(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(request, authorization, "ver_mis_solicitudes")
