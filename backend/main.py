"""
API RESTful en Python (FastAPI) - Clínica Veterinaria Patitas Felices
Integra los 4 patrones de diseño GoF:
1. Proxy (AuthSessionProxy): Seguridad JWT y verificación de sesión activa.
2. Strategy + RBAC (RBACContext): Autorización dinámica por rol (Admin, Doctor, Cliente).
3. Adapter (IDatabaseAdapter / WhatsAppAdapter): Desacoplamiento de BD y WhatsApp.
4. Facade (TiendaFacade): Checkout unificado (Stock + CRM + Boleta PDF en memoria).
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import os
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Cargar automáticamente variables de entorno desde .env si existe
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.is_file():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from .patterns import (
    AuthSessionProxy,
    ErrorProcesoVenta,
    ErrorSeguridadProxy,
    IDatabaseAdapter,
    RBACContext,
    RealClinicController,
    TiendaFacade,
    WhatsAppAdapter,
    generar_token_jwt,
    obtener_adaptador_bd,
    verificar_password,
)


# =============================================================================
# MODELOS PYDANTIC (ESQUEMAS PARA SWAGGER / OPENAPI)
# =============================================================================

class LoginRequest(BaseModel):
    email: str = Field(..., examples=["admin@patitasfelices.pe"])
    password: str = Field(..., examples=["admin123"])


class ItemCarritoRequest(BaseModel):
    producto_id: int = Field(..., examples=[1])
    cantidad: int = Field(..., ge=1, examples=[2])


class CheckoutRequest(BaseModel):
    cliente_nombre: Optional[str] = Field(default="", max_length=120, examples=["Lucía Fernández"])
    tipo_documento: Optional[str] = Field(default="DNI", examples=["DNI"])
    cliente_documento: str = Field(..., min_length=8, max_length=15, examples=["74859632"])
    metodo_pago: str = Field(default="Tarjeta / Yape", examples=["Yape / Plin"])
    items: List[ItemCarritoRequest]


class ActualizarDocumentoRequest(BaseModel):
    tipo_documento: str = Field(default="DNI", examples=["DNI"])
    documento: str = Field(..., min_length=8, max_length=11, examples=["74859632"])


class CitaRequest(BaseModel):
    usuario_id: Optional[int] = Field(default=None, examples=[1])
    mascota_id: Optional[int] = Field(default=None, examples=[1])
    propietario: str = Field(..., min_length=2, max_length=80, examples=["Lucía Fernández"])
    telefono: str = Field(..., min_length=9, max_length=20, examples=["912345678"])
    mascota_nombre: str = Field(..., min_length=1, max_length=60, examples=["Luna"])
    servicio: str = Field(..., examples=["consulta-general"])
    fecha: str = Field(..., examples=["2026-10-30"])
    hora: str = Field(..., examples=["10:30"])
    motivo: str = Field(..., min_length=10, max_length=1000, examples=["Control general y revisión de vacunas anuales."])


class CrearMascotaRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=60, examples=["Toby"])
    especie: str = Field(default="Perro", max_length=40, examples=["Perro"])
    raza: str = Field(default="Mestizo", max_length=60, examples=["Labrador"])
    edad: int = Field(default=1, ge=0, le=40, examples=[3])
    peso_kg: float = Field(default=5.0, ge=0.1, le=200.0, examples=[18.5])
    sexo: Optional[str] = Field(default="H", max_length=10, examples=["H"])
    historial_resumen: Optional[str] = Field(default="", max_length=500, examples=["Vacunas al día."])


class ActualizarCitaDoctorRequest(BaseModel):
    estado: str = Field(..., examples=["atendida"])
    diagnostico: str = Field(default="", examples=["Paciente estable, sin fiebre."])
    tratamiento: str = Field(default="", examples=["Control en 15 días y dieta blanda."])


class CambiarEstadoUsuarioRequest(BaseModel):
    estado: str = Field(..., examples=["inactivo"])


class RegistroRequest(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100, examples=["Juan Pérez"])
    email: str = Field(..., min_length=5, max_length=120, examples=["juan@ejemplo.com"])
    password: str = Field(..., min_length=6, max_length=100, examples=["segura123"])
    telefono: Optional[str] = Field(default="", max_length=25, examples=["987654321"])


class CrearPersonalRequest(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100, examples=["Dra. Andrea Morales"])
    email: str = Field(..., min_length=5, max_length=120, examples=["andrea@patitasfelices.pe"])
    password: str = Field(..., min_length=6, max_length=100, examples=["doctor123"])
    rol: str = Field(..., examples=["doctor"])
    telefono: Optional[str] = Field(default="", max_length=25, examples=["990112233"])
    cmvp: Optional[str] = Field(default="CMVP-00000", max_length=30, examples=["CMVP-12345"])
    especialidad: Optional[str] = Field(default="Medicina General", max_length=100, examples=["Dermatología"])


class CambiarPasswordRequest(BaseModel):
    password_actual: str = Field(..., min_length=1)
    password_nueva: str = Field(..., min_length=6)


class SolicitarCambioMascotaRequest(BaseModel):
    tipo: str = Field(..., examples=["editar", "eliminar"])
    motivo: str = Field(..., min_length=5, examples=["Cambio de peso y datos de vacunación"])
    datos_nuevos: Optional[Dict[str, Any]] = None


class ResolverSolicitudMascotaRequest(BaseModel):
    accion: str = Field(..., examples=["aprobar", "rechazar"])


# =============================================================================
# FÁBRICA DE APLICACIÓN FASTAPI
# =============================================================================

def crear_app(db_adapter: Optional[IDatabaseAdapter] = None) -> FastAPI:
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origenes_permitidos,
        allow_origin_regex=r"https?://.*\.loca\.lt",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    adaptador_bd = db_adapter or obtener_adaptador_bd()
    adaptador_whatsapp = WhatsAppAdapter()
    controlador_real = RealClinicController(adaptador_bd)
    proxy_seguridad = AuthSessionProxy(controlador_real, adaptador_bd)
    tienda_facade = TiendaFacade(adaptador_bd, adaptador_whatsapp)

    app.state.db = adaptador_bd
    app.state.whatsapp = adaptador_whatsapp
    app.state.proxy = proxy_seguridad
    app.state.facade = tienda_facade

    def _manejar_proxy(token: Optional[str], accion: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            return proxy_seguridad.ejecutar_accion(token, accion, params)
        except ErrorSeguridadProxy as exc:
            raise HTTPException(status_code=exc.codigo_http, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/health", tags=["Sistema"])
    def verificar_estado() -> Dict[str, Any]:
        return {
            "status": "ok",
            "clinica": "Patitas Felices",
            "patrones_activos": ["Proxy", "Strategy+RBAC", "Adapter", "Facade"],
            "adaptador_bd": type(adaptador_bd).__name__,
        }

    # -------------------------------------------------------------------------
    # 1. AUTENTICACIÓN Y SESIÓN (PATRÓN PROXY + STRATEGY RBAC)
    # -------------------------------------------------------------------------
    @app.post("/api/auth/login", tags=["Autenticación y RBAC (Proxy + Strategy)"])
    def iniciar_sesion(credenciales: LoginRequest) -> Dict[str, Any]:
        usuario = adaptador_bd.obtener_usuario_por_email(credenciales.email)
        if not usuario or not verificar_password(credenciales.password, str(usuario.get("password_hash", ""))):
            raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")

        if usuario["estado"] != "activo":
            raise HTTPException(
                status_code=403,
                detail="Cuenta inactiva o suspendida. El Proxy de seguridad bloqueó el inicio de sesión.",
            )

        # Patrón Strategy: Determinar vistas y permisos según el rol del usuario
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
                "tipo_documento": usuario.get("tipo_documento") or ("RUC" if len(str(usuario.get("documento") or "")) == 11 else "DNI"),
                "documento": usuario.get("documento"),
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

    @app.post("/api/auth/register", tags=["Autenticación y RBAC (Proxy + Strategy)"])
    def registrar_cliente(datos: RegistroRequest) -> Dict[str, Any]:
        email_limpio = datos.email.strip().lower()
        existente = adaptador_bd.obtener_usuario_por_email(email_limpio)
        if existente:
            raise HTTPException(
                status_code=400,
                detail="Ya existe una cuenta registrada con este correo electrónico.",
            )

        nuevo = adaptador_bd.crear_usuario({
            "nombre": datos.nombre.strip(),
            "email": email_limpio,
            "password_hash": datos.password,
            "rol": "cliente",
            "estado": "activo",
            "telefono": datos.telefono.strip() if datos.telefono else "",
        })

        contexto_rbac = RBACContext("cliente")
        config_vista = contexto_rbac.obtener_vista_y_permisos()
        token = generar_token_jwt(
            {
                "sub": nuevo.get("id", 0),
                "email": nuevo["email"],
                "rol": "cliente",
                "nombre": nuevo["nombre"],
            }
        )

        return {
            "mensaje": f"Bienvenido(a), {nuevo['nombre']}. Tu cuenta ha sido creada exitosamente.",
            "token": token,
            "usuario": {
                "id": nuevo.get("id"),
                "nombre": nuevo["nombre"],
                "email": nuevo["email"],
                "rol": "cliente",
                "estado": "activo",
                "telefono": nuevo.get("telefono", ""),
                "tipo_documento": nuevo.get("tipo_documento", "DNI"),
                "documento": nuevo.get("documento"),
            },
            "rbac": {
                "rol": "cliente",
                "etiqueta": config_vista["etiqueta"],
                "ruta_principal": config_vista["ruta_principal"],
                "ruta_espacio": config_vista["ruta_espacio"],
                "vistas_disponibles": config_vista["vistas_disponibles"],
                "acciones": list(config_vista["acciones"]),
            },
        }

    @app.get("/api/auth/sesion", tags=["Autenticación y RBAC (Proxy + Strategy)"])
    def consultar_sesion(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        if not authorization:
            raise HTTPException(status_code=401, detail="Token no suministrado.")
        token = authorization.replace("Bearer ", "").strip()
        sesion = proxy_seguridad.validar_sesion(token)
        usuario_db = adaptador_bd.obtener_usuario_por_id(sesion["id"]) if sesion.get("id") else {}
        sesion_actualizada = {
            **sesion,
            "tipo_documento": (usuario_db or {}).get("tipo_documento") or ("RUC" if len(str((usuario_db or {}).get("documento") or "")) == 11 else "DNI"),
            "documento": (usuario_db or {}).get("documento"),
        }
        contexto_rbac = RBACContext(sesion["rol"])
        config_vista = contexto_rbac.obtener_vista_y_permisos()
        return {
            "usuario": sesion_actualizada,
            "rbac": {
                "rol": sesion["rol"],
                "etiqueta": config_vista["etiqueta"],
                "ruta_principal": config_vista["ruta_principal"],
                "ruta_espacio": config_vista["ruta_espacio"],
                "vistas_disponibles": config_vista["vistas_disponibles"],
                "acciones": list(config_vista["acciones"]),
            },
        }

    @app.post("/api/auth/cambiar-password", tags=["Autenticación y RBAC (Proxy + Strategy)"])
    def cambiar_password(
        cuerpo: CambiarPasswordRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        return _manejar_proxy(
            authorization,
            "cambiar_password",
            {
                "password_actual": cuerpo.password_actual,
                "password_nueva": cuerpo.password_nueva,
            },
        )

    # -------------------------------------------------------------------------
    # 2. TIENDA, FARMACIA Y COMPROBANTES (PATRÓN FACADE)
    # -------------------------------------------------------------------------
    @app.get("/api/productos", tags=["Tienda y Checkout (Facade)"])
    def catalogo_productos() -> Dict[str, Any]:
        productos = tienda_facade.obtener_catalogo_activo()
        return {"total": len(productos), "productos": productos}

    @app.post("/api/tienda/checkout", tags=["Tienda y Checkout (Facade)"])
    def procesar_compra(
        pedido: CheckoutRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        usuario_id = 3
        usuario_db = None
        if authorization:
            try:
                token = authorization.replace("Bearer ", "").strip()
                sesion = proxy_seguridad.validar_sesion(token)
                usuario_id = sesion["id"]
                usuario_db = adaptador_bd.obtener_usuario_por_id(usuario_id)
            except Exception:
                pass

        if not usuario_db:
            usuario_db = adaptador_bd.obtener_usuario_por_id(usuario_id)

        # 1. Nombre bloqueado: utiliza el nombre real de la cuenta
        cliente_nombre = usuario_db["nombre"] if usuario_db else (pedido.cliente_nombre or "Cliente Patitas Felices")

        # 2. DNI o RUC (identificador único bloqueado)
        tipo_doc = (pedido.tipo_documento or "DNI").upper().strip()
        doc_solicitado = pedido.cliente_documento.strip()

        if usuario_db and usuario_db.get("documento"):
            # Si el cliente ya tiene documento en su perfil, prevalece el registrado (no modificable)
            doc_final = str(usuario_db["documento"]).strip()
            tipo_doc = usuario_db.get("tipo_documento") or ("RUC" if len(doc_final) == 11 else "DNI")
        else:
            # Primera compra: validar documento según el tipo elegido
            doc_final = doc_solicitado
            if tipo_doc == "DNI":
                if not doc_final.isdigit() or len(doc_final) != 8:
                    raise HTTPException(status_code=400, detail="El DNI debe contener exactamente 8 dígitos numéricos.")
            elif tipo_doc == "RUC":
                if not doc_final.isdigit() or len(doc_final) != 11:
                    raise HTTPException(status_code=400, detail="El RUC debe contener exactamente 11 dígitos numéricos.")
            # Guardar en su perfil de base de datos
            if usuario_db:
                adaptador_bd.actualizar_documento_usuario(usuario_db["id"], tipo_doc, doc_final)

        try:
            resultado = tienda_facade.procesar_venta(
                usuario_id=usuario_id,
                cliente_nombre=cliente_nombre,
                cliente_documento=doc_final,
                items=[i.model_dump() for i in pedido.items],
                metodo_pago=pedido.metodo_pago,
            )
            return {
                "mensaje": "Venta procesada exitosamente mediante TiendaFacade.",
                "usuario_actualizado": {
                    "id": usuario_id,
                    "nombre": cliente_nombre,
                    "tipo_documento": tipo_doc,
                    "documento": doc_final,
                },
                **resultado,
            }
        except ErrorProcesoVenta as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/tienda/boleta/{venta_id}/pdf", tags=["Tienda y Checkout (Facade)"])
    def descargar_boleta_pdf(venta_id: int) -> Response:
        ventas = adaptador_bd.listar_ventas()
        venta = next((v for v in ventas if int(v["id"]) == venta_id), None)
        if not venta:
            raise HTTPException(status_code=404, detail="Boleta no encontrada.")
        pdf_bytes = tienda_facade.pdf_generator.construir_pdf_en_memoria(venta)
        nombre_archivo = f"Boleta_{venta['numero_boleta']}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{nombre_archivo}"'},
        )

    # -------------------------------------------------------------------------
    # 3. CITAS Y ADAPTADOR WHATSAPP (PATRÓN ADAPTER + PROXY)
    # -------------------------------------------------------------------------
    @app.get("/api/citas/disponibilidad", tags=["Citas y WhatsApp (Adapter)"])
    def consultar_disponibilidad_citas(fecha: str) -> Dict[str, Any]:
        """
        Consulta la disponibilidad de cupos por turno (máximo 3 citas por horario correspondientes a los 3 doctores).
        """
        try:
            return adaptador_bd.obtener_disponibilidad_horarios(fecha)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Error consultando disponibilidad: {exc}") from exc

    @app.post("/api/citas", tags=["Citas y WhatsApp (Adapter)"])
    def registrar_cita(
        solicitud: CitaRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        datos = solicitud.model_dump()
        whatsapp_url = adaptador_whatsapp.generar_enlace_cita(datos)
        datos["whatsapp_url"] = whatsapp_url

        try:
            if authorization:
                resultado = _manejar_proxy(authorization, "agendar_cita", datos)
                cita = resultado["cita"]
            else:
                cita = adaptador_bd.crear_cita(datos)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return {
            "mensaje": "Cita registrada y adaptada para WhatsApp exitosamente.",
            "cita": cita,
            "whatsapp_url": whatsapp_url,
        }

    @app.get("/api/cliente/mis-citas", tags=["Citas y WhatsApp (Adapter)"])
    def obtener_mis_citas(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        return _manejar_proxy(authorization, "ver_mis_citas")

    @app.get("/api/cliente/mis-mascotas", tags=["Espacio del Cliente"])
    def listar_mis_mascotas(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        return _manejar_proxy(authorization, "ver_mis_mascotas")

    @app.post("/api/cliente/mascotas", tags=["Espacio del Cliente"])
    def registrar_mascota_cliente(
        cuerpo: CrearMascotaRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        return _manejar_proxy(
            authorization,
            "crear_mascota_cliente",
            cuerpo.model_dump(),
        )

    @app.delete("/api/cliente/mascotas/{mascota_id}", tags=["Espacio del Cliente"])
    def eliminar_mascota_cliente(
        mascota_id: int,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        return _manejar_proxy(
            authorization,
            "eliminar_mascota_cliente",
            {"mascota_id": mascota_id},
        )

    @app.post("/api/cliente/documento", tags=["Espacio del Cliente"])
    def registrar_documento_cliente(
        cuerpo: ActualizarDocumentoRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        return _manejar_proxy(
            authorization,
            "actualizar_documento_cliente",
            {"tipo_documento": cuerpo.tipo_documento, "documento": cuerpo.documento},
        )

    @app.get("/api/cliente/mis-compras", tags=["Espacio del Cliente"])
    def ver_mis_compras(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        return _manejar_proxy(authorization, "ver_mis_compras")

    @app.post("/api/cliente/mascotas/{mascota_id}/solicitar-cambio", tags=["Espacio del Cliente"])
    def solicitar_cambio_mascota(
        mascota_id: int,
        cuerpo: SolicitarCambioMascotaRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        return _manejar_proxy(
            authorization,
            "solicitar_cambio_mascota",
            {
                "mascota_id": mascota_id,
                "tipo": cuerpo.tipo,
                "motivo": cuerpo.motivo,
                "datos_nuevos": cuerpo.datos_nuevos,
            },
        )

    @app.get("/api/cliente/solicitudes", tags=["Espacio del Cliente"])
    def ver_mis_solicitudes(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        return _manejar_proxy(authorization, "ver_mis_solicitudes")

    # -------------------------------------------------------------------------
    # 4. AGENDA E HISTORIAL DEL DOCTOR (PATRÓN PROXY + STRATEGY DOCTOR/ADMIN)
    # -------------------------------------------------------------------------
    @app.get("/api/doctor/agenda", tags=["Agenda e Historial (Doctor)"])
    def ver_agenda_doctor(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        return _manejar_proxy(authorization, "ver_agenda_doctor")

    @app.patch("/api/doctor/citas/{cita_id}", tags=["Agenda e Historial (Doctor)"])
    def actualizar_cita_clinica(
        cita_id: int,
        cuerpo: ActualizarCitaDoctorRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        return _manejar_proxy(
            authorization,
            "actualizar_diagnostico",
            {
                "cita_id": cita_id,
                "estado": cuerpo.estado,
                "diagnostico": cuerpo.diagnostico,
                "tratamiento": cuerpo.tratamiento,
            },
        )

    # -------------------------------------------------------------------------
    # 5. CRM Y ADMINISTRACIÓN (PATRÓN PROXY + STRATEGY ADMIN)
    # -------------------------------------------------------------------------
    @app.get("/api/admin/crm", tags=["CRM y Administración"])
    def resumen_crm(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        return _manejar_proxy(authorization, "ver_crm_dashboard")

    @app.patch("/api/admin/usuarios/{usuario_id}/estado", tags=["CRM y Administración"])
    def cambiar_estado_usuario_crm(
        usuario_id: int,
        cuerpo: CambiarEstadoUsuarioRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        return _manejar_proxy(
            authorization,
            "cambiar_estado_usuario",
            {"usuario_id": usuario_id, "estado": cuerpo.estado},
        )

    @app.post("/api/admin/usuarios", tags=["CRM y Administración"])
    def crear_personal_admin_crm(
        cuerpo: CrearPersonalRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        return _manejar_proxy(
            authorization,
            "crear_personal_admin",
            {
                "nombre": cuerpo.nombre,
                "email": cuerpo.email,
                "password": cuerpo.password,
                "rol": cuerpo.rol,
                "telefono": cuerpo.telefono,
                "cmvp": cuerpo.cmvp,
                "especialidad": cuerpo.especialidad,
            },
        )

    @app.get("/api/admin/solicitudes-mascotas", tags=["CRM y Administración"])
    def ver_todas_solicitudes_mascotas(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        return _manejar_proxy(authorization, "gestionar_solicitudes_mascota")

    @app.post("/api/admin/solicitudes-mascotas/{solicitud_id}/resolver", tags=["CRM y Administración"])
    def resolver_solicitud_mascota(
        solicitud_id: int,
        cuerpo: ResolverSolicitudMascotaRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        return _manejar_proxy(
            authorization,
            "resolver_solicitud_mascota",
            {"solicitud_id": solicitud_id, "accion": cuerpo.accion},
        )

    # -------------------------------------------------------------------------
    # 6. VISOR DE BASE DE DATOS (LAS 16 TABLAS DE PRUEBA_1.ERD.JSON)
    # -------------------------------------------------------------------------
    @app.get("/api/bd/tablas", tags=["Base de Datos (16 Tablas)"])
    def obtener_tablas_completas() -> Dict[str, Any]:
        tablas = adaptador_bd.obtener_todas_las_16_tablas()
        return {
            "total_tablas": len(tablas),
            "archivo_sqlite": getattr(adaptador_bd, "db_path", "Supabase PostgreSQL (Nube)"),
            "tablas": tablas,
        }

    @app.get("/visor-bd", tags=["Base de Datos (16 Tablas)"])
    def visor_html_bd() -> Response:
        html = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Visor en Vivo de las 16 Tablas | Patitas Felices</title>
  <link rel="icon" href="/img/logotipoveterinaria.jpg" type="image/jpeg">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 24px; background: #F8F9FA; color: #1C252C; }
    h1 { color: #0B2545; margin-bottom: 6px; }
    .subtitle { color: #5B6B78; margin-top: 0; margin-bottom: 20px; font-size: 0.95rem; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
    .chip { background: #FFFFFF; border: 1px solid #CED4DA; border-radius: 20px; padding: 6px 14px; font-size: 0.85rem; cursor: pointer; transition: 0.2s; }
    .chip:hover, .chip.active { background: #134074; color: #FFFFFF; border-color: #134074; }
    .table-card { background: #FFFFFF; border: 1px solid #E5E9EE; border-radius: 8px; margin-bottom: 28px; box-shadow: 0 2px 6px rgba(0,0,0,0.04); overflow: hidden; }
    .card-header { background: #EEF4F8; padding: 12px 18px; font-weight: bold; color: #0B2545; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #E5E9EE; }
    .table-container { overflow-x: auto; max-height: 480px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; text-align: left; }
    th { background: #FAFCFE; padding: 10px 14px; border-bottom: 2px solid #E2E8F0; color: #475569; position: sticky; top: 0; font-weight: 600; }
    td { padding: 8px 14px; border-bottom: 1px solid #EDF2F7; white-space: nowrap; }
    tr:hover td { background: #F8FAFC; }
    .empty { padding: 20px; text-align: center; color: #8C9BA5; }
    .btn-top { text-decoration: none; background: #0B2545; color: white; padding: 8px 16px; border-radius: 6px; font-size: 0.9rem; font-weight: 500; display: inline-block; margin-bottom: 15px; }
  </style>
</head>
<body>
  <div style="display:flex; justify-content:space-between; align-items:flex-start;">
    <div>
      <h1>Visor en Vivo de las 16 Tablas (DER)</h1>
      <p class="subtitle" id="meta-bd">Cargando base de datos...</p>
    </div>
    <a class="btn-top" href="/">← Volver al Portal Astro</a>
  </div>
  <div class="toolbar" id="barra-filtros"></div>
  <div id="contenedor-tablas"></div>

  <script>
    let cacheTablas = {};
    let tablaSeleccionada = 'TODAS';

    function renderizar() {
      const cont = document.getElementById('contenedor-tablas');
      cont.innerHTML = '';
      const nombres = tablaSeleccionada === 'TODAS' ? Object.keys(cacheTablas) : [tablaSeleccionada];

      for (const nombre of nombres) {
        const filas = cacheTablas[nombre] || [];
        const section = document.createElement('section');
        section.className = 'table-card';

        const header = document.createElement('div');
        header.className = 'card-header';
        header.innerHTML = '<span>Tabla: <code>' + nombre + '</code></span><span>' + filas.length + ' registros</span>';
        section.appendChild(header);

        if (filas.length === 0) {
          const emp = document.createElement('div');
          emp.className = 'empty';
          emp.textContent = 'La tabla no contiene registros actualmente.';
          section.appendChild(emp);
        } else {
          const wrap = document.createElement('div');
          wrap.className = 'table-container';
          const tbl = document.createElement('table');
          const thead = document.createElement('thead');
          const trHead = document.createElement('tr');
          const columnas = Object.keys(filas[0]);
          for (const c of columnas) {
            const th = document.createElement('th');
            th.textContent = c;
            trHead.appendChild(th);
          }
          thead.appendChild(trHead);
          tbl.appendChild(thead);

          const tbody = document.createElement('tbody');
          for (const f of filas) {
            const tr = document.createElement('tr');
            for (const c of columnas) {
              const td = document.createElement('td');
              td.textContent = f[c] !== null && f[c] !== undefined ? f[c] : '—';
              tr.appendChild(td);
            }
            tbody.appendChild(tr);
          }
          tbl.appendChild(tbody);
          wrap.appendChild(tbl);
          section.appendChild(wrap);
        }
        cont.appendChild(section);
      }
    }

    async function cargarTablas() {
      const res = await fetch('/api/bd/tablas');
      const data = await res.json();
      cacheTablas = data.tablas || {};
      document.getElementById('meta-bd').textContent =
        'Total tablas activas: ' + data.total_tablas + ' | Base de datos: ' + data.archivo_sqlite;

      const filtros = document.getElementById('barra-filtros');
      filtros.innerHTML = '';
      const btnTodas = document.createElement('button');
      btnTodas.className = 'chip' + (tablaSeleccionada === 'TODAS' ? ' active' : '');
      btnTodas.textContent = 'Mostrar todas las tablas';
      btnTodas.onclick = () => { tablaSeleccionada = 'TODAS'; cargarTablas(); };
      filtros.appendChild(btnTodas);

      Object.keys(cacheTablas).forEach((nom, idx) => {
        const b = document.createElement('button');
        b.className = 'chip' + (tablaSeleccionada === nom ? ' active' : '');
        b.textContent = (idx + 1) + '. ' + nom + ' (' + cacheTablas[nom].length + ')';
        b.onclick = () => { tablaSeleccionada = nom; cargarTablas(); };
        filtros.appendChild(b);
      });

      renderizar();
    }
    cargarTablas();
  </script>
</body>
</html>"""
        return Response(content=html, media_type="text/html")

    # Servir el Frontend compilado de Astro (dist/) en el mismo puerto para Hosting Unificado y Modo App
    dist_dir = Path(__file__).resolve().parent.parent / "dist"
    if dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="astro_frontend")

    return app


app = crear_app()
