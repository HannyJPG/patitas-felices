"""
API RESTful en Python (FastAPI) - Clínica Veterinaria Patitas Felices
Integra los 4 patrones de diseño GoF:
1. Proxy (AuthSessionProxy): Seguridad JWT y verificación de sesión activa.
2. Strategy + RBAC (RBACContext): Autorización dinámica por rol (Admin, Doctor, Cliente).
3. Adapter (IDatabaseAdapter / WhatsAppAdapter): Desacoplamiento de BD y WhatsApp.
4. Facade (TiendaFacade): Checkout unificado (Stock + CRM + Boleta PDF en memoria).
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.is_file():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from .patterns import (
    AuthSessionProxy,
    IDatabaseAdapter,
    RealClinicController,
    TiendaFacade,
    WhatsAppAdapter,
    obtener_adaptador_bd,
)
from .routers import admin, auth, bd, citas, doctor, tienda
from .schemas import (  # noqa: F401 - Reexportado por compatibilidad
    ActualizarCitaDoctorRequest,
    ActualizarDocumentoRequest,
    CambiarEstadoUsuarioRequest,
    CambiarPasswordRequest,
    CheckoutRequest,
    CitaRequest,
    CrearMascotaRequest,
    CrearPersonalRequest,
    ItemCarritoRequest,
    LoginRequest,
    RegistroRequest,
    ResolverSolicitudMascotaRequest,
    SolicitarCambioMascotaRequest,
)


def crear_app(db_adapter: Optional[IDatabaseAdapter] = None) -> FastAPI:
    """Construye la aplicación FastAPI con routers modulares y los 4 patrones GoF."""
    app = FastAPI(
        title="Clínica Veterinaria Patitas Felices - API RESTful",
        description=(
            "Backend en Python (FastAPI) conectado a Astro mediante fetch(). "
            "Implementa los 4 patrones GoF: Proxy, Strategy + RBAC, Adapter y Facade."
        ),
        version="2.0.0",
    )

    origenes_env = os.getenv("CORS_ORIGINS", "")
    origenes_permitidos = (
        [o.strip() for o in origenes_env.split(",") if o.strip()]
        if origenes_env.strip()
        else [
            "http://127.0.0.1:4321",
            "http://localhost:4321",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        ]
    )

    cors_kwargs: Dict[str, Any] = {
        "allow_origins": origenes_permitidos,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
    if os.getenv("ENABLE_LOCALTUNNEL_CORS", "").strip() == "1":
        cors_kwargs["allow_origin_regex"] = r"https?://.*\.loca\.lt"

    app.add_middleware(CORSMiddleware, **cors_kwargs)

    adaptador_bd = db_adapter or obtener_adaptador_bd()
    adaptador_whatsapp = WhatsAppAdapter()
    controlador_real = RealClinicController(adaptador_bd)
    proxy_seguridad = AuthSessionProxy(controlador_real, adaptador_bd)
    tienda_facade = TiendaFacade(adaptador_bd, adaptador_whatsapp)

    app.state.db = adaptador_bd
    app.state.whatsapp = adaptador_whatsapp
    app.state.proxy = proxy_seguridad
    app.state.facade = tienda_facade

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errores = []
        for err in exc.errors():
            loc = err.get("loc", ())
            campo = str(loc[-1]) if loc else "campo"
            msg = err.get("msg", "dato inválido")
            if msg.startswith("Value error, "):
                msg = msg.replace("Value error, ", "")
            if campo == "telefono":
                errores.append(f"Teléfono: debe contener al menos 9 dígitos ({msg})")
            elif campo == "motivo":
                errores.append(f"Motivo: debe contener al menos 10 caracteres ({msg})")
            elif campo == "propietario":
                errores.append(f"Propietario: {msg}")
            elif campo == "mascota_nombre":
                errores.append(f"Nombre de mascota: {msg}")
            else:
                errores.append(f"{campo}: {msg}")
        mensaje_limpio = ". ".join(errores) if errores else "Datos del formulario incompletos o inválidos."
        return JSONResponse(
            status_code=422,
            content={"detail": mensaje_limpio, "errores": exc.errors()},
        )

    app.include_router(auth.router)
    app.include_router(tienda.router)
    app.include_router(citas.router)
    app.include_router(doctor.router)
    app.include_router(admin.router)
    app.include_router(bd.router)

    dist_dir = Path(__file__).resolve().parent.parent / "dist"
    if dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="astro_frontend")

    return app


app = crear_app()
