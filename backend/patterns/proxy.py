"""
PATRÓN PROXY (Estructural - GoF)
Puntos de sustentación: 1 y 4.
Propósito: Actuar como un guardián de seguridad (Protection Proxy) antes de llegar
al controlador real (RealClinicController). Verifica:
1) Que el token JWT sea auténtico y no haya expirado.
2) Que la sesión y el usuario existan en la Base de Datos con estado == 'activo'.
3) Que la estrategia RBAC del rol autorice la acción solicitada antes de ejecutar el controlador real.
"""

from abc import ABC, abstractmethod
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional

from .adapter import IDatabaseAdapter
from .strategy import RBACContext


class ErrorSeguridadProxy(PermissionError):
    """Excepción lanzada por AuthSessionProxy cuando el acceso es denegado."""

    def __init__(self, mensaje: str, codigo_http: int = 401) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo_http = codigo_http


# =============================================================================
# UTILIDADES JWT NATIVAS (HS256 ESTÁNDAR RFC 7519 SIN DEPENDENCIAS FRÁGILES)
# =============================================================================

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(texto: str) -> bytes:
    padding = "=" * (-len(texto) % 4)
    return base64.urlsafe_b64decode((texto + padding).encode("ascii"))


def generar_token_jwt(payload: Dict[str, Any], duracion_segundos: int = 28800) -> str:
    """Genera un token JWT firmado con HMAC-SHA256."""
    secreto = os.getenv("JWT_SECRET", "patitas-felices-clave-secreta-2026").encode("utf-8")
    header = {"alg": "HS256", "typ": "JWT"}
    ahora = int(time.time())
    cuerpo = {
        **payload,
        "iat": ahora,
        "exp": ahora + duracion_segundos,
    }
    segmento_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    segmento_payload = _b64url_encode(json.dumps(cuerpo, separators=(",", ":")).encode("utf-8"))
    mensaje = f"{segmento_header}.{segmento_payload}".encode("ascii")
    firma = hmac.new(secreto, mensaje, hashlib.sha256).digest()
    return f"{segmento_header}.{segmento_payload}.{_b64url_encode(firma)}"


def verificar_token_jwt(token: str) -> Dict[str, Any]:
    """Verifica firma y vigencia de un token JWT HS256."""
    if not token or not isinstance(token, str):
        raise ErrorSeguridadProxy("Token JWT ausente. Inicie sesión para continuar.", 401)

    token_limpio = token.replace("Bearer ", "").strip()
    partes = token_limpio.split(".")
    if len(partes) != 3:
        raise ErrorSeguridadProxy("Formato de token JWT inválido.", 401)

    secreto = os.getenv("JWT_SECRET", "patitas-felices-clave-secreta-2026").encode("utf-8")
    mensaje = f"{partes[0]}.{partes[1]}".encode("ascii")
    firma_esperada = _b64url_encode(hmac.new(secreto, mensaje, hashlib.sha256).digest())

    if not hmac.compare_digest(firma_esperada, partes[2]):
        raise ErrorSeguridadProxy("Firma de token JWT inválida o adulterada.", 401)

    try:
        payload = json.loads(_b64url_decode(partes[1]).decode("utf-8"))
    except Exception as exc:
        raise ErrorSeguridadProxy("No se pudo decodificar el contenido del token JWT.", 401) from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise ErrorSeguridadProxy("La sesión JWT ha expirado. Vuelva a iniciar sesión.", 401)

    return payload


# =============================================================================
# SUJETO E IMPLEMENTACIÓN DEL PATRÓN PROXY
# =============================================================================

class ISecureController(ABC):
    """Subject Interface: Contrato común entre el Controlador Real y el Proxy."""

    @abstractmethod
    def ejecutar_accion(
        self, token: Optional[str], accion: str, parametros: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        pass


class RealClinicController(ISecureController):
    """
    RealSubject (Controlador Real):
    Contiene las operaciones sensibles de la clínica (CRM, gestión de usuarios,
    agenda médica e historial clínico). Asume que quien lo invoca ya pasó por el Proxy.
    """

    def __init__(self, db_adapter: IDatabaseAdapter) -> None:
        self.db = db_adapter

    def ejecutar_accion(
        self, token: Optional[str], accion: str, parametros: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        params = parametros or {}
        usuario_actual = params.get("_usuario_autenticado", {})

        if accion == "ver_crm_dashboard":
            usuarios = self.db.listar_usuarios()
            ventas = self.db.listar_ventas()
            citas = self.db.listar_citas()
            mascotas = self.db.listar_mascotas()
            productos = self.db.listar_productos(solo_activos=False)
            ingresos_totales = round(sum(float(v["total"]) for v in ventas), 2)
            ventas_referencia_demo = [
                {
                    "id": 901,
                    "numero_boleta": "B001-DEMO01",
                    "cliente_nombre": "Lucía Fernández",
                    "cliente_documento": "74859632",
                    "servicio_categoria": "Consulta general",
                    "concepto": "Consulta general + Control de peso (Luna)",
                    "subtotal": 50.85,
                    "igv": 9.15,
                    "total": 60.00,
                    "metodo_pago": "Yape / Plin",
                    "estado": "pagado",
                    "creado_en": "2026-10-20 10:15:00",
                    "es_demostracion": True,
                },
                {
                    "id": 902,
                    "numero_boleta": "B001-DEMO02",
                    "cliente_nombre": "Jorge Ramírez",
                    "cliente_documento": "45896321",
                    "servicio_categoria": "Vacunación",
                    "concepto": "Vacuna séxtuple canina + Refuerzo anual",
                    "subtotal": 63.56,
                    "igv": 11.44,
                    "total": 75.00,
                    "metodo_pago": "Tarjeta Visa / Mastercard",
                    "estado": "pagado",
                    "creado_en": "2026-10-22 16:40:00",
                    "es_demostracion": True,
                },
                {
                    "id": 903,
                    "numero_boleta": "B001-DEMO03",
                    "cliente_nombre": "María Vargas",
                    "cliente_documento": "10457896",
                    "servicio_categoria": "Farmacia",
                    "concepto": "Antipulgas Bravecto Chewable 10-20kg",
                    "subtotal": 122.88,
                    "igv": 22.12,
                    "total": 145.00,
                    "metodo_pago": "Transferencia Bancaria",
                    "estado": "pagado",
                    "creado_en": "2026-10-24 11:20:00",
                    "es_demostracion": True,
                },
                {
                    "id": 904,
                    "numero_boleta": "B001-DEMO04",
                    "cliente_nombre": "Carlos Quispe",
                    "cliente_documento": "71239845",
                    "servicio_categoria": "Desparasitación",
                    "concepto": "Desparasitación interna y externa felina",
                    "subtotal": 38.14,
                    "igv": 6.86,
                    "total": 45.00,
                    "metodo_pago": "Yape / Plin",
                    "estado": "pagado",
                    "creado_en": "2026-10-25 15:10:00",
                    "es_demostracion": True,
                },
                {
                    "id": 905,
                    "numero_boleta": "B001-DEMO05",
                    "cliente_nombre": "Ana Paredes",
                    "cliente_documento": "42987612",
                    "servicio_categoria": "Nutrición",
                    "concepto": "Alimento Clínico Renal Canine 2kg",
                    "subtotal": 75.85,
                    "igv": 13.65,
                    "total": 89.50,
                    "metodo_pago": "Tarjeta Visa / Mastercard",
                    "estado": "pagado",
                    "creado_en": "2026-10-26 18:05:00",
                    "es_demostracion": True,
                },
            ]
            ventas_mostradas = ventas if ventas else ventas_referencia_demo
            ingresos_mostrados = round(sum(float(v["total"]) for v in ventas_mostradas), 2)
            total_tx = len(ventas_mostradas)
            ticket_promedio = round(ingresos_mostrados / total_tx, 2) if total_tx > 0 else 0.0
            return {
                "resumen": {
                    "total_usuarios": len(usuarios),
                    "usuarios_activos": sum(1 for u in usuarios if u["estado"] == "activo"),
                    "total_pacientes": len(mascotas),
                    "total_citas": len(citas),
                    "citas_pendientes": sum(1 for c in citas if c["estado"] == "pendiente"),
                    "total_ventas": len(ventas),
                    "ingresos_totales": ingresos_totales,
                    "stock_total_unidades": sum(int(p["stock"]) for p in productos),
                },
                "balance_financiero": {
                    "ingresos_totales": ingresos_mostrados,
                    "ingresos_reales": ingresos_totales,
                    "total_transacciones": total_tx,
                    "ventas_reales": len(ventas),
                    "ticket_promedio": ticket_promedio,
                    "modo_demostracion": len(ventas) == 0,
                },
                "ultimas_ventas": ventas_mostradas,
                "usuarios": usuarios,
                "mascotas": mascotas,
                "ventas": ventas,
                "ventas_referencia_demo": ventas_referencia_demo,
                "citas": citas,
                "productos": productos,
                "trafico_periodo": [
                    {"fecha": "2026-10-21", "visitas": 34, "consultas_citas": 8, "es_demostracion": True},
                    {"fecha": "2026-10-22", "visitas": 48, "consultas_citas": 12, "es_demostracion": True},
                    {"fecha": "2026-10-23", "visitas": 41, "consultas_citas": 9, "es_demostracion": True},
                    {"fecha": "2026-10-24", "visitas": 62, "consultas_citas": 16, "es_demostracion": True},
                    {"fecha": "2026-10-25", "visitas": 55, "consultas_citas": 14, "es_demostracion": True},
                    {"fecha": "2026-10-26", "visitas": 71, "consultas_citas": 19, "es_demostracion": True},
                    {"fecha": "2026-10-27", "visitas": 28 + len(citas) + len(ventas), "consultas_citas": len(citas), "es_demostracion": False},
                ],
            }

        if accion == "cambiar_estado_usuario":
            usuario_id = int(params["usuario_id"])
            nuevo_estado = str(params["estado"]).lower()
            if nuevo_estado not in ("activo", "inactivo"):
                raise ValueError("El estado debe ser 'activo' o 'inactivo'.")
            actualizado = self.db.actualizar_estado_usuario(usuario_id, nuevo_estado)
            if not actualizado:
                raise LookupError(f"Usuario con ID {usuario_id} no encontrado.")
            return {"usuario": actualizado}

        if accion == "crear_personal_admin":
            rol = str(params.get("rol", "")).lower()
            if rol not in ("doctor", "admin"):
                raise ValueError("El rol asignado debe ser 'doctor' o 'admin'.")
            email = str(params.get("email", "")).strip().lower()
            if self.db.obtener_usuario_por_email(email):
                raise ValueError("Ya existe una cuenta registrada con este correo electrónico.")

            cmvp = str(params.get("cmvp") or "").strip()
            if rol == "doctor":
                if not cmvp:
                    raise ValueError("El número de colegiatura CMVP es obligatorio para registrar un médico veterinario.")
                if hasattr(self.db, "existe_colegiatura_veterinario") and self.db.existe_colegiatura_veterinario(cmvp):
                    raise ValueError(f"El número de colegiatura '{cmvp}' ya está registrado para otro profesional veterinario.")

            nuevo_usuario = self.db.crear_usuario({
                "nombre": params["nombre"].strip(),
                "email": email,
                "password_hash": params["password"],
                "rol": rol,
                "estado": "activo",
                "telefono": params.get("telefono", "").strip(),
            })
            if rol == "doctor":
                self.db.crear_doctor({
                    "usuario_id": nuevo_usuario.get("id"),
                    "cmvp": cmvp,
                    "nombre": params["nombre"].strip(),
                    "telefono": params.get("telefono", "").strip(),
                    "email": email,
                    "especialidad": params.get("especialidad") or "Medicina General",
                })
            return {"usuario": nuevo_usuario}

        if accion == "ver_agenda_doctor":
            citas = self.db.listar_citas()
            mascotas = self.db.listar_mascotas()
            perfil_profesional = {
                "id": usuario_actual.get("id", 2),
                "nombre": usuario_actual.get("nombre", "Dr. Carlos Mendoza"),
                "email": usuario_actual.get("email", "doctor@patitasfelices.pe"),
                "telefono": usuario_actual.get("telefono", "987654321"),
                "colegiatura": "CMVP-10452",
                "especialidad": "Medicina General, Preventiva y Dermatología",
                "horario_turno": "Lunes a Sábado · 09:00 a 18:00 (Lima)",
            }
            return {
                "perfil_profesional": perfil_profesional,
                "citas": citas,
                "mascotas": mascotas,
            }

        if accion == "actualizar_diagnostico":
            cita_id = int(params["cita_id"])
            estado = str(params.get("estado", "atendida"))
            diagnostico = str(params.get("diagnostico", "")).strip()
            tratamiento = str(params.get("tratamiento", "")).strip()
            cita = self.db.actualizar_cita_doctor(
                cita_id=cita_id,
                estado=estado,
                diagnostico=diagnostico,
                tratamiento=tratamiento,
                doctor_id=usuario_actual.get("id"),
            )
            if not cita:
                raise LookupError(f"La cita #{cita_id} no existe.")
            return {"cita": cita}

        if accion == "agendar_cita":
            nueva_cita = self.db.crear_cita(
                {
                    **params,
                    "usuario_id": usuario_actual.get("id"),
                }
            )
            return {"cita": nueva_cita}

        if accion == "ver_mis_citas":
            uid = usuario_actual.get("id")
            citas = self.db.listar_citas(usuario_id=uid)
            mascotas = self.db.listar_mascotas(usuario_id=uid)
            usuario_db = self.db.obtener_usuario_por_id(uid) if uid else {}
            perfil = {
                "id": uid,
                "nombre": (usuario_db or {}).get("nombre", usuario_actual.get("nombre", "")),
                "email": (usuario_db or {}).get("email", usuario_actual.get("email", "")),
                "telefono": (usuario_db or {}).get("telefono", usuario_actual.get("telefono", "")),
                "rol": usuario_actual.get("rol", "cliente"),
                "estado": usuario_actual.get("estado", "activo"),
                "tipo_documento": (usuario_db or {}).get("tipo_documento", "DNI"),
                "documento": (usuario_db or {}).get("documento"),
            }
            return {"perfil": perfil, "citas": citas, "mascotas": mascotas}

        if accion == "actualizar_documento_cliente":
            uid = usuario_actual.get("id") or int(params.get("usuario_id", 0))
            if not uid:
                raise ValueError("Usuario no autenticado para actualizar documento.")
            usuario_db = self.db.obtener_usuario_por_id(uid)
            if not usuario_db:
                raise LookupError("Usuario no encontrado.")
            if usuario_db.get("documento"):
                raise ValueError("Tu documento de identidad ya se encuentra registrado y es un identificador único no modificable.")

            tipo_limpio = str(params.get("tipo_documento", "DNI")).upper().strip()
            if tipo_limpio not in ("DNI", "RUC"):
                raise ValueError("El tipo de documento debe ser DNI o RUC.")

            doc_limpio = str(params.get("documento", "")).strip()
            if tipo_limpio == "DNI" and (not doc_limpio.isdigit() or len(doc_limpio) != 8):
                raise ValueError("El DNI debe contener exactamente 8 dígitos numéricos.")
            if tipo_limpio == "RUC" and (not doc_limpio.isdigit() or len(doc_limpio) != 11):
                raise ValueError("El RUC debe contener exactamente 11 dígitos numéricos.")

            actualizado = self.db.actualizar_documento_usuario(uid, tipo_limpio, doc_limpio)
            return {"usuario": actualizado or usuario_db}

        if accion == "ver_mis_mascotas":
            uid = usuario_actual.get("id")
            mascotas = self.db.listar_mascotas(usuario_id=uid)
            return {"total": len(mascotas), "mascotas": mascotas}

        if accion == "crear_mascota_cliente":
            uid = usuario_actual.get("id")
            if not uid:
                raise ValueError("Usuario no autenticado para registrar mascota.")
            nueva = self.db.crear_mascota({
                **params,
                "usuario_id": uid,
            })
            return {"mascota": nueva}

        if accion == "eliminar_mascota_cliente":
            uid = usuario_actual.get("id")
            mascota_id = int(params["mascota_id"])
            rol = usuario_actual.get("rol", "cliente")
            eliminado = self.db.eliminar_mascota(
                mascota_id=mascota_id,
                usuario_id=None if rol == "admin" else uid,
            )
            return {"eliminado": eliminado, "mascota_id": mascota_id}

        if accion == "cambiar_password":
            uid = usuario_actual.get("id") or int(params.get("usuario_id", 0))
            if not uid:
                raise ValueError("Usuario no autenticado.")
            pwd_actual = str(params.get("password_actual", "")).strip()
            pwd_nueva = str(params.get("password_nueva", "")).strip()
            if len(pwd_nueva) < 6:
                raise ValueError("La nueva contraseña debe tener al menos 6 caracteres.")
            self.db.cambiar_password_usuario(uid, pwd_actual, pwd_nueva)
            return {"mensaje": "Contraseña actualizada exitosamente."}

        if accion == "ver_mis_compras":
            uid = usuario_actual.get("id") or int(params.get("usuario_id", 0))
            compras = self.db.listar_compras_usuario(uid)
            return {"total": len(compras), "compras": compras}

        if accion == "solicitar_cambio_mascota":
            uid = usuario_actual.get("id")
            if not uid:
                raise ValueError("Usuario no autenticado.")
            mascota_id = int(params["mascota_id"])
            tipo = str(params.get("tipo", "editar")).lower()
            if tipo not in ("editar", "eliminar"):
                raise ValueError("El tipo de solicitud debe ser 'editar' o 'eliminar'.")
            motivo = str(params.get("motivo", "")).strip()
            if len(motivo) < 5:
                raise ValueError("Por favor proporciona una justificación o motivo claro (mínimo 5 caracteres).")
            datos_nuevos = params.get("datos_nuevos")
            solicitud = self.db.crear_solicitud_mascota(uid, mascota_id, tipo, motivo, datos_nuevos)
            return {
                "mensaje": "Tu solicitud ha sido enviada a la administración para su evaluación.",
                "solicitud": solicitud,
            }

        if accion == "ver_mis_solicitudes":
            uid = usuario_actual.get("id")
            solicitudes = self.db.listar_solicitudes_mascota(usuario_id=uid)
            return {"total": len(solicitudes), "solicitudes": solicitudes}

        if accion == "gestionar_solicitudes_mascota":
            solicitudes = self.db.listar_solicitudes_mascota(usuario_id=None)
            return {"total": len(solicitudes), "solicitudes": solicitudes}

        if accion == "resolver_solicitud_mascota":
            solicitud_id = int(params["solicitud_id"])
            accion_res = str(params.get("accion", "aprobar")).lower().strip()
            res = self.db.resolver_solicitud_mascota(solicitud_id, accion_res)
            return {
                "mensaje": f"Solicitud #{solicitud_id} procesada exitosamente como {res['estado']}.",
                "solicitud": res,
            }

        raise ValueError(f"Acción no implementada en el controlador real: {accion}")


class AuthSessionProxy(ISecureController):
    """
    Protection Proxy (Guardián de Seguridad y Sesión):
    Intercepta todas las llamadas hacia RealClinicController.
    1. Valida el token JWT.
    2. Consulta en tiempo real a la BD si el usuario sigue 'activo' (si un Admin lo
       desactiva en el CRM, el Proxy bloquea su acceso de inmediato).
    3. Evalúa el permiso mediante RBACContext (Patrón Strategy).
    """

    def __init__(self, real_controller: RealClinicController, db_adapter: IDatabaseAdapter) -> None:
        self._real_controller = real_controller
        self._db = db_adapter

    def validar_sesion(self, token: Optional[str]) -> Dict[str, Any]:
        payload = verificar_token_jwt(token or "")
        usuario_id = int(payload.get("sub", 0))
        usuario_bd = self._db.obtener_usuario_por_id(usuario_id)

        if not usuario_bd:
            raise ErrorSeguridadProxy("El usuario de la sesión no existe en el sistema.", 401)

        if usuario_bd.get("estado") != "activo":
            raise ErrorSeguridadProxy(
                "Cuenta inactiva o suspendida. El Proxy de seguridad bloqueó el acceso.", 403
            )

        return usuario_bd

    def ejecutar_accion(
        self, token: Optional[str], accion: str, parametros: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        # Paso 1 y 2: Verificar JWT y estado activo en base de datos
        usuario_bd = self.validar_sesion(token)

        # Paso 3: Delegar en Strategy + RBAC la verificación del permiso según rol
        contexto_rbac = RBACContext(usuario_bd["rol"])
        if not contexto_rbac.autorizar(accion):
            raise ErrorSeguridadProxy(
                f"Acceso denegado por RBAC: el rol '{usuario_bd['rol']}' no tiene permiso para '{accion}'.",
                403,
            )

        # Paso 4: Pasar la solicitud al Controlador Real enriquecida con el usuario verificado
        parametros_seguros = dict(parametros or {})
        parametros_seguros["_usuario_autenticado"] = usuario_bd
        return self._real_controller.ejecutar_accion(token, accion, parametros_seguros)
