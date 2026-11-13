"""Router de Salud del Sistema, Autenticación JWT y RBAC (Proxy + Strategy)."""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Header, HTTPException, Request

from ..patterns import (
    ErrorConexionSQLServer,
    ErrorConsultaSQLServer,
    ErrorRegistroDuplicadoSQLServer,
    ErrorSeguridadProxy,
    RBACContext,
    generar_token_jwt,
    verificar_password,
)
from ..patterns.adapter import es_email_valido
from ..schemas import (
    AuthResponse,
    CambiarPasswordRequest,
    HealthResponse,
    LoginRequest,
    RegistroRequest,
    SesionResponse,
)
from .deps import manejar_proxy

router = APIRouter()


@router.get("/api/health", tags=["Sistema"], response_model=HealthResponse)
def verificar_estado(request: Request) -> Dict[str, Any]:
    return {
        "status": "ok",
        "clinica": "Patitas Felices",
        "patrones_activos": ["Proxy", "Strategy+RBAC", "Adapter", "Facade"],
        "adaptador_bd": type(request.app.state.db).__name__,
    }


@router.post("/api/auth/login", tags=["Autenticación y RBAC (Proxy + Strategy)"], response_model=AuthResponse)
def iniciar_sesion(credenciales: LoginRequest, request: Request) -> Dict[str, Any]:
    adaptador_bd = request.app.state.db
    email_limpio = credenciales.email.strip().lower()
    try:
        usuario = adaptador_bd.obtener_usuario_por_email(email_limpio)
    except ErrorConexionSQLServer as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ErrorConsultaSQLServer as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not usuario or not verificar_password(credenciales.password, str(usuario.get("password_hash", ""))):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")

    if usuario["estado"] != "activo":
        raise HTTPException(
            status_code=403,
            detail="Cuenta inactiva o suspendida. El Proxy de seguridad bloqueó el inicio de sesión.",
        )

    contexto_rbac = RBACContext(usuario["rol"])
    config_vista = contexto_rbac.obtener_vista_y_permisos()

    token = generar_token_jwt(
        {
            "sub": usuario["id"],
            "email": usuario["email"],
            "rol": usuario["rol"],
            "nombre": usuario["nombre"],
        }
    )

    return {
        "mensaje": f"Bienvenido(a), {usuario['nombre']}",
        "token": token,
        "usuario": {
            "id": usuario["id"],
            "nombre": usuario["nombre"],
            "email": usuario["email"],
            "rol": usuario["rol"],
            "estado": usuario["estado"],
            "telefono": usuario.get("telefono"),
            "tipo_documento": usuario.get("tipo_documento")
            or ("RUC" if len(str(usuario.get("documento") or "")) == 11 else "DNI"),
            "documento": usuario.get("documento"),
            "id_veterinario": usuario.get("id_veterinario"),
            "cmvp": usuario.get("cmvp"),
            "especialidad": usuario.get("especialidad"),
        },
        "rbac": {
            "rol": usuario["rol"],
            "etiqueta": config_vista["etiqueta"],
            "ruta_principal": config_vista["ruta_principal"],
            "ruta_espacio": config_vista["ruta_espacio"],
            "vistas_disponibles": config_vista["vistas_disponibles"],
            "acciones": list(config_vista["acciones"]),
        },
    }


@router.post("/api/auth/register", tags=["Autenticación y RBAC (Proxy + Strategy)"], response_model=AuthResponse)
def registrar_cliente(datos: RegistroRequest, request: Request) -> Dict[str, Any]:
    adaptador_bd = request.app.state.db
    nombre_limpio = datos.nombre.strip()
    email_limpio = datos.email.strip().lower()
    telefono_limpio = datos.telefono.strip() if datos.telefono else ""

    if len(nombre_limpio) < 2:
        raise HTTPException(status_code=400, detail="El nombre y apellido deben tener al menos 2 caracteres.")
    if not es_email_valido(email_limpio):
        raise HTTPException(status_code=400, detail="Por favor, ingresa un correo electrónico válido.")
    if len(datos.password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres.")

    try:
        existente = adaptador_bd.obtener_usuario_por_email(email_limpio)
        if existente:
            raise HTTPException(
                status_code=400,
                detail="Ya existe una cuenta registrada con este correo electrónico.",
            )

        nuevo = adaptador_bd.crear_usuario(
            {
                "nombre": nombre_limpio,
                "email": email_limpio,
                "password_hash": datos.password,
                "rol": "cliente",
                "estado": "activo",
                "telefono": telefono_limpio,
            }
        )
    except HTTPException:
        raise
    except ErrorConexionSQLServer as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, ErrorRegistroDuplicadoSQLServer) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ErrorConsultaSQLServer as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not nuevo or not nuevo.get("id"):
        raise HTTPException(
            status_code=500,
            detail="No se pudo confirmar el almacenamiento del usuario en SQL Server.",
        )

    rol_real = str(nuevo.get("rol") or "cliente").lower()
    contexto_rbac = RBACContext(rol_real)
    config_vista = contexto_rbac.obtener_vista_y_permisos()
    token = generar_token_jwt(
        {
            "sub": nuevo["id"],
            "email": nuevo["email"],
            "rol": rol_real,
            "nombre": nuevo["nombre"],
        }
    )

    return {
        "mensaje": f"Bienvenido(a), {nuevo['nombre']}. Tu cuenta ha sido creada exitosamente.",
        "token": token,
        "usuario": {
            "id": nuevo["id"],
            "nombre": nuevo["nombre"],
            "email": nuevo["email"],
            "rol": rol_real,
            "estado": nuevo.get("estado", "activo"),
            "telefono": nuevo.get("telefono", ""),
            "tipo_documento": nuevo.get("tipo_documento", "DNI"),
            "documento": nuevo.get("documento"),
        },
        "rbac": {
            "rol": rol_real,
            "etiqueta": config_vista["etiqueta"],
            "ruta_principal": config_vista["ruta_principal"],
            "ruta_espacio": config_vista["ruta_espacio"],
            "vistas_disponibles": config_vista["vistas_disponibles"],
            "acciones": list(config_vista["acciones"]),
        },
    }


@router.get("/api/auth/sesion", tags=["Autenticación y RBAC (Proxy + Strategy)"], response_model=SesionResponse)
def consultar_sesion(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Token no suministrado.")
    token = authorization.replace("Bearer ", "").strip()
    proxy_seguridad = request.app.state.proxy
    adaptador_bd = request.app.state.db
    try:
        sesion = proxy_seguridad.validar_sesion(token)
        usuario_db = adaptador_bd.obtener_usuario_por_id(sesion["id"]) if sesion.get("id") else {}
    except ErrorSeguridadProxy as exc:
        raise HTTPException(status_code=exc.codigo_http, detail=str(exc)) from exc
    except ErrorConexionSQLServer as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ErrorConsultaSQLServer as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sesion_limpia = {k: v for k, v in sesion.items() if k != "password_hash"}
    sesion_actualizada = {
        **sesion_limpia,
        "tipo_documento": (usuario_db or {}).get("tipo_documento")
        or ("RUC" if len(str((usuario_db or {}).get("documento") or "")) == 11 else "DNI"),
        "documento": (usuario_db or {}).get("documento"),
        "id_veterinario": (usuario_db or {}).get("id_veterinario"),
        "cmvp": (usuario_db or {}).get("cmvp"),
        "especialidad": (usuario_db or {}).get("especialidad"),
    }
    contexto_rbac = RBACContext(sesion_actualizada["rol"])
    config_vista = contexto_rbac.obtener_vista_y_permisos()
    return {
        "usuario": sesion_actualizada,
        "rbac": {
            "rol": sesion_actualizada["rol"],
            "etiqueta": config_vista["etiqueta"],
            "ruta_principal": config_vista["ruta_principal"],
            "ruta_espacio": config_vista["ruta_espacio"],
            "vistas_disponibles": config_vista["vistas_disponibles"],
            "acciones": list(config_vista["acciones"]),
        },
    }


@router.post("/api/auth/cambiar-password", tags=["Autenticación y RBAC (Proxy + Strategy)"])
def cambiar_password(
    cuerpo: CambiarPasswordRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return manejar_proxy(
        request,
        authorization,
        "cambiar_password",
        {
            "password_actual": cuerpo.password_actual,
            "password_nueva": cuerpo.password_nueva,
        },
    )
