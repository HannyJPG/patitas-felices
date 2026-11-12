"""
PATRÓN ADAPTER (Estructural - GoF)
Implementa el desacoplamiento de Base de Datos (Microsoft SQL Server) y WhatsApp.
Integra el modelo canónico en 3FN de 16 tablas sin redundancias basado en `prueba_1.erd.json`.
"""
from abc import ABC, abstractmethod
from datetime import date
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from .sqlserver_schema import (
    ErrorConexionSQLServer,
    ErrorConsultaSQLServer,
    ErrorRegistroDuplicadoSQLServer,
    NOMBRES_16_TABLAS,
    SQLServerConnection,
    ensure_sqlserver_schema,
    sql_lit,
)

_env_file = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_file.is_file():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and (not _line.startswith("#")) and ("=" in _line):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# =============================================================================
# 0. UTILIDADES CRIPTOGRÁFICAS DE CONTRASEÑAS (PBKDF2-HMAC-SHA256)
# =============================================================================
_PBKDF2_PREFIX = "pbkdf2_sha256$"
_PBKDF2_ITERATIONS = 100000


def hashear_password(password_plano: str) -> str:
    """Genera un hash criptográfico PBKDF2-HMAC-SHA256 con sal aleatoria de 128 bits."""
    if not password_plano or str(password_plano).startswith(_PBKDF2_PREFIX):
        return str(password_plano)
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", str(password_plano).encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS
    ).hex()
    return f"{_PBKDF2_PREFIX}{salt}${dk}"


def verificar_password(password_plano: str, hash_almacenado: str) -> bool:
    """
    Verifica de forma segura (tiempo constante) una contraseña contra su hash PBKDF2.
    Mantiene retrocompatibilidad con cuentas preexistentes si aún no tienen prefijo.
    """
    if not password_plano or not hash_almacenado:
        return False
    hash_str = str(hash_almacenado)
    plano_str = str(password_plano)
    if hash_str.startswith(_PBKDF2_PREFIX):
        partes = hash_str.split("$", 2)
        if len(partes) != 3:
            return False
        _, salt, digest_esperado = partes
        dk = hashlib.pbkdf2_hmac(
            "sha256", plano_str.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS
        ).hex()
        return hmac.compare_digest(dk, digest_esperado)
    return hmac.compare_digest(hash_str, plano_str)


# =============================================================================
# 1. ADAPTER PARA INTEGRACIÓN EXTERNA DE MENSAJERÍA (WHATSAPP API / URL)
# =============================================================================
class IWhatsAppNotificationAdapter(ABC):
    """Target Interface: Define el contrato que la clínica necesita para notificar."""

    @abstractmethod
    def generar_enlace_cita(self, datos_cita: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    def generar_enlace_boleta(self, numero_boleta: str, cliente: str, total: float) -> str:
        pass


class WhatsAppAdapter(IWhatsAppNotificationAdapter):
    """
    Adapter concreto: Adapta los diccionarios de negocio de la clínica al formato
    requerido por la API web de WhatsApp (https://wa.me/<telefono>?text=<mensaje_codificado>).
    """

    SERVICIOS_NOMBRES = {
        "consulta-general": "Consulta general",
        "vacunacion": "Vacunación",
        "desparasitacion": "Desparasitación",
        "control": "Control y seguimiento",
    }
    SERVICIOS_CODIGOS = {nombre: codigo for codigo, nombre in SERVICIOS_NOMBRES.items()}

    def __init__(self, numero_clinica: Optional[str] = None) -> None:
        self.numero_clinica = numero_clinica or os.getenv("CLINICA_WHATSAPP", "51990853697")

    def _construir_url(self, mensaje: str) -> str:
        texto_codificado = quote(mensaje, safe="")
        return f"https://wa.me/{self.numero_clinica}?text={texto_codificado}"

    def generar_enlace_cita(self, datos_cita: Dict[str, Any]) -> str:
        fecha_raw = str(datos_cita.get("fecha", ""))
        partes = fecha_raw.split("-")
        fecha_formateada = f"{partes[2]}/{partes[1]}/{partes[0]}" if len(partes) == 3 else fecha_raw
        servicio_clave = datos_cita.get("servicio", "")
        servicio_legible = self.SERVICIOS_NOMBRES.get(servicio_clave, servicio_clave)
        lineas = [
            "Hola, Patitas Felices. Quisiera solicitar una cita veterinaria.",
            "",
            f"Propietario: {datos_cita.get('propietario', '')}",
            f"Teléfono de contacto: {datos_cita.get('telefono', '')}",
            f"Mascota: {datos_cita.get('mascota_nombre') or datos_cita.get('mascota', '')}",
            f"Servicio: {servicio_legible}",
            f"Fecha deseada: {fecha_formateada}",
            f"Hora deseada: {datos_cita.get('hora', '')} (Lima, Perú)",
            "Duración: 30 minutos",
            f"Motivo: {datos_cita.get('motivo', '')}",
            "",
            "¿Podrían confirmar si este horario está disponible?",
        ]
        return self._construir_url("\n".join(lineas))

    def generar_enlace_boleta(self, numero_boleta: str, cliente: str, total: float) -> str:
        mensaje = (
            f"Hola, Patitas Felices. Soy {cliente}. Acabo de realizar la compra con "
            f"Boleta N° {numero_boleta} por un total de S/ {total:.2f}. Solicito coordinación de entrega."
        )
        return self._construir_url(mensaje)


# =============================================================================
# 2. INTERFAZ ADAPTER PARA BASE DE DATOS
# =============================================================================
class IDatabaseAdapter(ABC):
    """Target Interface para el acceso desacoplado a la persistencia."""

    @abstractmethod
    def inicializar_esquema(self) -> None:
        pass

    @abstractmethod
    def obtener_usuario_por_email(self, email: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def crear_usuario(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def actualizar_documento_usuario(
        self, usuario_id: int, tipo_documento: str, documento: str
    ) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def cambiar_password_usuario(
        self, usuario_id: int, password_actual: str, password_nueva: str
    ) -> bool:
        pass

    @abstractmethod
    def listar_compras_usuario(self, usuario_id: int) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def crear_solicitud_mascota(
        self,
        usuario_id: int,
        mascota_id: int,
        tipo: str,
        motivo: str,
        datos_nuevos: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def listar_solicitudes_mascota(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def resolver_solicitud_mascota(self, solicitud_id: int, accion: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def obtener_disponibilidad_horarios(self, fecha: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def crear_doctor(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def obtener_usuario_por_id(self, usuario_id: int) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def listar_usuarios(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def actualizar_estado_usuario(
        self, usuario_id: int, nuevo_estado: str
    ) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def listar_mascotas(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def crear_mascota(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def eliminar_mascota(self, mascota_id: int, usuario_id: Optional[int] = None) -> bool:
        pass

    @abstractmethod
    def crear_cita(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def listar_citas(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def actualizar_cita_doctor(
        self,
        cita_id: int,
        estado: str,
        diagnostico: str,
        tratamiento: str,
        doctor_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def listar_productos(self, solo_activos: bool = True) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def obtener_producto(self, producto_id: int) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def descontar_stock_producto(self, producto_id: int, cantidad: int) -> bool:
        pass

    @abstractmethod
    def registrar_venta_y_detalles(
        self, cabecera: Dict[str, Any], detalles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def listar_ventas(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def obtener_todas_las_16_tablas(self) -> Dict[str, List[Dict[str, Any]]]:
        pass


# =============================================================================
# 3. ADAPTER DE MICROSOFT SQL SERVER (16 TABLAS EN 3FN SIN REDUNDANCIAS)
# =============================================================================
class SQLServerDatabaseAdapter(IDatabaseAdapter):
    """
    Adaptador concreto conectado directamente a Microsoft SQL Server (`PatitasFelices_DB` en `localhost`)
    mediante ODBC nativo de Windows (`odbc32.dll`), ejecutando consultas T-SQL sobre las 16 tablas en 3FN.
    """

    NOMBRES_16_TABLAS = NOMBRES_16_TABLAS

    def __init__(
        self,
        database: Optional[str] = None,
        server: Optional[str] = None,
        reset_tables: bool = False,
        include_demo_users: bool = False,
    ) -> None:
        self.server = (server or os.getenv("SQLSERVER_SERVER", "localhost")).strip()
        raw_db = (database or os.getenv("SQLSERVER_DATABASE", "PatitasFelices_DB")).strip()
        if raw_db == ":memory:":
            self.database = "PatitasFelices_Test_DB"
            self._reset_tables = True
            self._include_demo_users = True
        elif raw_db == "PatitasFelices_Test_DB":
            self.database = "PatitasFelices_Test_DB"
            self._reset_tables = reset_tables
            self._include_demo_users = include_demo_users
        else:
            self.database = raw_db
            self._reset_tables = reset_tables
            self._include_demo_users = include_demo_users

        self.conn = SQLServerConnection(server=self.server, database=self.database)
        self.inicializar_esquema()

    def inicializar_esquema(self) -> None:
        ensure_sqlserver_schema(
            self.conn,
            hashear_password,
            reset_tables=self._reset_tables,
            include_demo_users=self._include_demo_users,
        )
        rows = self.conn.query_json("SELECT id, password_hash FROM dbo.usuarios")
        for row in rows:
            pwd = row.get("password_hash") or ""
            if pwd and not str(pwd).startswith(_PBKDF2_PREFIX):
                hashed = hashear_password(str(pwd))
                self.conn.execute(
                    f"UPDATE dbo.usuarios SET password_hash = {sql_lit(hashed)} WHERE id = {int(row['id'])}"
                )

    def _owner_id_for_user(self, usuario_id: int, create: bool = True) -> Optional[int]:
        row = self.conn.query_one(
            f"SELECT TOP 1 id_dueno FROM dbo.Dueno WHERE usuario_id = {int(usuario_id)}"
        )
        if row:
            return int(row["id_dueno"])
        user = self.conn.query_one(
            f"SELECT TOP 1 id, nombre, telefono FROM dbo.usuarios WHERE id = {int(usuario_id)}"
        )
        if not user or not create:
            return None
        parts = str(user.get("nombre") or "Cliente").strip().split(" ", 1)
        doc = f"CLI{int(usuario_id):05d}"
        nombres = parts[0]
        apellidos = parts[1] if len(parts) > 1 else ""
        tel = user.get("telefono") or ""
        new_id = self.conn.scalar(
            f"""
            INSERT INTO dbo.Dueno (usuario_id, dni, tipo_documento, nombres, apellidos, telefono)
            OUTPUT INSERTED.id_dueno
            VALUES ({int(usuario_id)}, {sql_lit(doc)}, 'DNI', {sql_lit(nombres)}, {sql_lit(apellidos)}, {sql_lit(tel)})
            """
        )
        return int(new_id)

    def _resolve_raza_id(self, especie: str, raza: str, descripcion: str) -> int:
        species = (especie or "Perro").strip() or "Perro"
        breed = (raza or "Mestizo").strip() or "Mestizo"
        sp = self.conn.query_one(
            f"SELECT TOP 1 Id_especie FROM dbo.Especie WHERE LOWER(Nombre) = LOWER({sql_lit(species)})"
        )
        if sp:
            species_id = int(sp["Id_especie"])
        else:
            species_id = int(
                self.conn.scalar(
                    f"""
                    INSERT INTO dbo.Especie (Nombre, Descripcion)
                    OUTPUT INSERTED.Id_especie
                    VALUES ({sql_lit(species)}, {sql_lit(descripcion)})
                    """
                )
            )
        rz = self.conn.query_one(
            f"SELECT TOP 1 Id_raza FROM dbo.Razas WHERE Id_especie = {species_id} AND LOWER(nombre) = LOWER({sql_lit(breed)})"
        )
        if rz:
            return int(rz["Id_raza"])
        return int(
            self.conn.scalar(
                f"""
                INSERT INTO dbo.Razas (Id_especie, nombre, Descripcion)
                OUTPUT INSERTED.Id_raza
                VALUES ({species_id}, {sql_lit(breed)}, {sql_lit(descripcion)})
                """
            )
        )

    def _user_row(
        self,
        where_sql: str,
        params: Optional[Dict[str, Any]] = None,
        include_password_hash: bool = False,
    ) -> Optional[Dict[str, Any]]:
        row = self.conn.query_one(
            f"""
            SELECT TOP 1
                u.id, u.nombre, u.email, u.password_hash, u.rol, u.estado, u.telefono,
                CONVERT(VARCHAR(19), u.creado_en, 120) AS creado_en,
                COALESCE(d.tipo_documento, 'DNI') AS tipo_documento,
                CASE WHEN d.dni LIKE 'CLI%' OR d.dni LIKE 'EXT%' THEN NULL ELSE d.dni END AS documento,
                v.Id_veterinario AS id_veterinario,
                v.numero_colegiatura AS cmvp,
                esp.Nombre AS especialidad,
                CONVERT(VARCHAR(10), v.Fecha_contratacion, 23) AS fecha_contratacion
            FROM dbo.usuarios u
            LEFT JOIN dbo.Dueno d ON d.usuario_id = u.id
            LEFT JOIN dbo.Veterinario v ON v.usuario_id = u.id
            LEFT JOIN dbo.Especialidad esp ON esp.Id_especialidad = v.Id_especialidad
            WHERE {where_sql}
            """,
            params=params,
        )
        if row and not include_password_hash:
            row.pop("password_hash", None)
        return row

    def _mascota_row(self, mascota_id: int) -> Optional[Dict[str, Any]]:
        return self.conn.query_one(
            f"""
            SELECT TOP 1
                p.id_paciente AS id,
                d.usuario_id,
                p.nombre,
                e.Nombre AS especie,
                r.nombre AS raza,
                CASE WHEN YEAR(SYSDATETIME()) - YEAR(p.fecha_nacimiento) < 0 THEN 0
                     ELSE YEAR(SYSDATETIME()) - YEAR(p.fecha_nacimiento) END AS edad,
                CAST(p.peso_kg AS FLOAT) AS peso_kg,
                COALESCE(p.historial_resumen, '') AS historial_resumen,
                p.sexo,
                CONVERT(VARCHAR(10), p.fecha_nacimiento, 23) AS fecha_nacimiento,
                p.estado,
                CONVERT(VARCHAR(19), p.fecha_registro, 120) AS creado_en,
                COALESCE(u.nombre, LTRIM(RTRIM(d.nombres + ' ' + d.apellidos))) AS propietario_nombre
            FROM dbo.Paciente p
            JOIN dbo.Dueno d ON d.id_dueno = p.id_dueno
            JOIN dbo.Razas r ON r.Id_raza = p.Id_raza
            JOIN dbo.Especie e ON e.Id_especie = r.Id_especie
            LEFT JOIN dbo.usuarios u ON u.id = d.usuario_id
            WHERE p.id_paciente = {int(mascota_id)}
            """
        )

    def obtener_usuario_por_email(self, email: str) -> Optional[Dict[str, Any]]:
        email_limpio = str(email or "").strip().lower()
        if not email_limpio:
            return None
        return self._user_row(
            "LOWER(u.email) = LOWER(@email)",
            params={"email": email_limpio},
            include_password_hash=True,
        )

    def crear_usuario(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        nombre = str(datos.get("nombre", "")).strip()
        email = str(datos.get("email", "")).strip().lower()
        rol = str(datos.get("rol", "cliente")).strip().lower()
        estado = str(datos.get("estado", "activo")).strip().lower()
        telefono = str(datos.get("telefono", "")).strip()
        doc_nuevo = str(datos.get("documento") or "").strip()
        raw_pwd = str(datos.get("password_hash") or datos.get("password") or "")

        if len(nombre) < 2:
            raise ValueError("El nombre del usuario debe tener al menos 2 caracteres.")
        if "@" not in email or "." not in email.split("@")[-1] or " " in email:
            raise ValueError("El correo electrónico suministrado no tiene un formato válido.")
        if rol not in ("cliente", "doctor", "admin"):
            raise ValueError("El rol del usuario debe ser 'cliente', 'doctor' o 'admin'.")
        if estado not in ("activo", "inactivo"):
            raise ValueError("El estado del usuario debe ser 'activo' o 'inactivo'.")
        if not raw_pwd or (not raw_pwd.startswith(_PBKDF2_PREFIX) and len(raw_pwd) < 6):
            raise ValueError("La contraseña debe tener al menos 6 caracteres.")

        if self.obtener_usuario_por_email(email):
            raise ValueError("Ya existe una cuenta registrada con este correo electrónico.")

        if doc_nuevo:
            dup = self.conn.query_one(
                "SELECT TOP 1 1 AS ok FROM dbo.Dueno WHERE dni = @dni",
                params={"dni": doc_nuevo},
            )
            if dup:
                raise ValueError(
                    "El documento de identidad ingresado ya está registrado en otra cuenta."
                )

        pwd_hash = hashear_password(raw_pwd)
        parts = nombre.split(" ", 1)
        nombres_dueno = parts[0]
        apellidos_dueno = parts[1] if len(parts) > 1 else ""
        tipo_doc = str(datos.get("tipo_documento") or ("RUC" if len(doc_nuevo) == 11 else "DNI")).strip()
        crear_dueno = 1 if (rol == "cliente" or bool(doc_nuevo)) else 0

        try:
            nuevo_id_str = self.conn.scalar(
                """
                SET XACT_ABORT ON;
                BEGIN TRY
                    BEGIN TRANSACTION;
                    DECLARE @new_uid INT;
                    INSERT INTO dbo.usuarios (nombre, email, password_hash, rol, estado, telefono)
                    VALUES (@nombre, @email, @pwd_hash, @rol, @estado, @telefono);
                    SET @new_uid = CAST(SCOPE_IDENTITY() AS INT);

                    IF @crear_dueno = 1
                    BEGIN
                        DECLARE @dni_final VARCHAR(20) = CASE
                            WHEN LEN(@doc_nuevo) > 0 THEN @doc_nuevo
                            ELSE 'CLI' + RIGHT('00000' + CAST(@new_uid AS VARCHAR(10)), 5)
                        END;
                        INSERT INTO dbo.Dueno (usuario_id, dni, tipo_documento, nombres, apellidos, telefono)
                        VALUES (@new_uid, @dni_final, @tipo_doc, @nombres, @apellidos, @telefono);
                    END;

                    COMMIT TRANSACTION;
                    SELECT CAST(@new_uid AS VARCHAR(20)) AS id;
                END TRY
                BEGIN CATCH
                    IF @@TRANCOUNT > 0
                        ROLLBACK TRANSACTION;
                    THROW;
                END CATCH;
                """,
                params={
                    "nombre": nombre,
                    "email": email,
                    "pwd_hash": pwd_hash,
                    "rol": rol,
                    "estado": estado,
                    "telefono": telefono,
                    "crear_dueno": crear_dueno,
                    "doc_nuevo": doc_nuevo,
                    "tipo_doc": tipo_doc,
                    "nombres": nombres_dueno,
                    "apellidos": apellidos_dueno,
                },
            )
        except ErrorRegistroDuplicadoSQLServer as exc:
            raise ValueError(
                "Ya existe una cuenta registrada con este correo electrónico o documento de identidad."
            ) from exc

        if not nuevo_id_str or not str(nuevo_id_str).strip().isdigit():
            raise ErrorConsultaSQLServer(
                "No se pudo completar la inserción del usuario en SQL Server."
            )

        nuevo_id = int(str(nuevo_id_str).strip())
        usuario_persistido = self.obtener_usuario_por_id(nuevo_id)
        if not usuario_persistido or int(usuario_persistido.get("id", 0)) != nuevo_id:
            raise ErrorConsultaSQLServer(
                "No se pudo verificar la persistencia del usuario recién registrado en SQL Server."
            )
        return usuario_persistido

    def actualizar_documento_usuario(
        self, usuario_id: int, tipo_documento: str, documento: str
    ) -> Optional[Dict[str, Any]]:
        doc_limpio = documento.strip()
        dup = self.conn.query_one(
            "SELECT TOP 1 1 AS ok FROM dbo.Dueno WHERE dni = @dni AND (usuario_id IS NULL OR usuario_id <> @uid)",
            params={"dni": doc_limpio, "uid": int(usuario_id)},
        )
        if dup:
            raise ValueError(
                "El documento de identidad ingresado ya está registrado en otra cuenta."
            )
        self._owner_id_for_user(usuario_id, create=True)
        self.conn.execute(
            "UPDATE dbo.Dueno SET dni = @dni, tipo_documento = @tipo WHERE usuario_id = @uid",
            params={"dni": doc_limpio, "tipo": tipo_documento.strip(), "uid": int(usuario_id)},
        )
        return self.obtener_usuario_por_id(int(usuario_id))

    def cambiar_password_usuario(
        self, usuario_id: int, password_actual: str, password_nueva: str
    ) -> bool:
        row = self.conn.query_one(
            "SELECT TOP 1 password_hash FROM dbo.usuarios WHERE id = @uid",
            params={"uid": int(usuario_id)},
        )
        if not row or not verificar_password(password_actual, row["password_hash"]):
            raise ValueError("La contraseña actual no es correcta.")
        nuevo_hash = hashear_password(password_nueva)
        self.conn.execute(
            "UPDATE dbo.usuarios SET password_hash = @pwd_hash WHERE id = @uid",
            params={"pwd_hash": nuevo_hash, "uid": int(usuario_id)},
        )
        return True

    def listar_compras_usuario(self, usuario_id: int) -> List[Dict[str, Any]]:
        owner_id = self._owner_id_for_user(usuario_id, create=False)
        if owner_id is None:
            return []
        return self._query_facturas(
            f"WHERE f.id_dueno = {owner_id} AND f.Id_cita IS NULL ORDER BY f.id_factura DESC"
        )

    def crear_solicitud_mascota(
        self,
        usuario_id: int,
        mascota_id: int,
        tipo: str,
        motivo: str,
        datos_nuevos: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        owner = self._owner_id_for_user(usuario_id, create=False)
        pet = self.conn.query_one(
            f"SELECT TOP 1 id_dueno, solicitud_estado FROM dbo.Paciente WHERE id_paciente = {int(mascota_id)}"
        )
        if not pet or int(pet["id_dueno"]) != int(owner or -1):
            raise LookupError("Mascota no encontrada para este usuario.")
        if pet.get("solicitud_estado") == "pendiente":
            raise ValueError("La mascota ya tiene una solicitud pendiente.")
        datos_json = json.dumps(datos_nuevos, ensure_ascii=False) if datos_nuevos else None
        self.conn.execute(
            f"""
            UPDATE dbo.Paciente
            SET solicitud_tipo = {sql_lit(tipo)},
                solicitud_datos_nuevos = {sql_lit(datos_json)},
                solicitud_motivo = {sql_lit(motivo.strip())},
                solicitud_estado = 'pendiente',
                solicitud_creado_en = SYSDATETIME()
            WHERE id_paciente = {int(mascota_id)}
            """
        )
        return next(
            item
            for item in self.listar_solicitudes_mascota(usuario_id)
            if int(item["id"]) == int(mascota_id)
        )

    def listar_solicitudes_mascota(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        where_extra = f" AND d.usuario_id = {int(usuario_id)}" if usuario_id is not None else ""
        result = self.conn.query_json(
            f"""
            SELECT
                p.id_paciente AS id,
                p.id_paciente AS mascota_id,
                d.usuario_id,
                p.solicitud_tipo AS tipo,
                p.solicitud_datos_nuevos AS datos_nuevos,
                p.solicitud_motivo AS motivo,
                p.solicitud_estado AS estado,
                CONVERT(VARCHAR(19), p.solicitud_creado_en, 120) AS creado_en,
                COALESCE(u.nombre, LTRIM(RTRIM(d.nombres + ' ' + d.apellidos))) AS propietario_nombre,
                COALESCE(u.email, '') AS propietario_email,
                p.nombre AS mascota_nombre,
                e.Nombre AS mascota_especie,
                r.nombre AS mascota_raza
            FROM dbo.Paciente p
            JOIN dbo.Dueno d ON d.id_dueno = p.id_dueno
            LEFT JOIN dbo.usuarios u ON u.id = d.usuario_id
            JOIN dbo.Razas r ON r.Id_raza = p.Id_raza
            JOIN dbo.Especie e ON e.Id_especie = r.Id_especie
            WHERE p.solicitud_tipo IS NOT NULL{where_extra}
            ORDER BY p.solicitud_creado_en DESC, p.id_paciente DESC
            """
        )
        for item in result:
            if item.get("datos_nuevos") and isinstance(item["datos_nuevos"], str):
                try:
                    item["datos_nuevos"] = json.loads(item["datos_nuevos"])
                except (ValueError, TypeError):
                    pass
        return result

    def resolver_solicitud_mascota(self, solicitud_id: int, accion: str) -> Dict[str, Any]:
        row = self.conn.query_one(
            f"SELECT TOP 1 * FROM dbo.Paciente WHERE id_paciente = {int(solicitud_id)} AND solicitud_tipo IS NOT NULL"
        )
        if not row:
            raise LookupError("Solicitud no encontrada.")
        if row.get("solicitud_estado") != "pendiente":
            raise ValueError("Esta solicitud ya fue resuelta previamente.")
        action = accion.lower().strip()
        if action not in ("aprobar", "rechazar"):
            raise ValueError("La accion debe ser 'aprobar' o 'rechazar'.")
        status = "aprobada" if action == "aprobar" else "rechazada"
        if action == "aprobar" and row.get("solicitud_tipo") == "eliminar":
            self.conn.execute(
                f"UPDATE dbo.Paciente SET estado = 'Eliminado' WHERE id_paciente = {int(solicitud_id)}"
            )
        elif action == "aprobar" and row.get("solicitud_tipo") == "editar" and row.get("solicitud_datos_nuevos"):
            new = (
                json.loads(row["solicitud_datos_nuevos"])
                if isinstance(row["solicitud_datos_nuevos"], str)
                else row["solicitud_datos_nuevos"]
            )
            if new.get("especie") or new.get("raza"):
                cur_rz = self.conn.query_one(
                    f"""
                    SELECT TOP 1 e.Nombre AS especie, r.nombre AS raza
                    FROM dbo.Razas r
                    JOIN dbo.Especie e ON e.Id_especie = r.Id_especie
                    WHERE r.Id_raza = {int(row['Id_raza'])}
                    """
                )
                sp_default = cur_rz["especie"] if cur_rz else "Perro"
                rz_default = cur_rz["raza"] if cur_rz else "Mestizo"
                race_id = self._resolve_raza_id(
                    str(new.get("especie") or sp_default),
                    str(new.get("raza") or rz_default),
                    "Registrada desde solicitud",
                )
            else:
                race_id = int(row["Id_raza"])
            birth_str = str(row.get("fecha_nacimiento") or "2023-05-10")[:10]
            current_age = max(0, date.today().year - int(birth_str[:4])) if birth_str[:4].isdigit() else 1
            raw_age = new.get("edad")
            age = max(0, int(raw_age if raw_age is not None else current_age))
            new_birth = f"{max(1900, date.today().year - age):04d}-01-01" if raw_age is not None else birth_str
            raw_peso = new.get("peso_kg")
            peso_final = float(raw_peso if raw_peso is not None else row.get("peso_kg") or 5.0)
            nuevo_nombre = str(new.get("nombre") or row["nombre"]).strip()
            nuevo_hist = (
                new.get("historial_resumen")
                if new.get("historial_resumen") is not None
                else (row.get("historial_resumen") or "")
            )
            self.conn.execute(
                f"""
                UPDATE dbo.Paciente
                SET Id_raza = {race_id},
                    nombre = {sql_lit(nuevo_nombre)},
                    fecha_nacimiento = {sql_lit(new_birth)},
                    peso_kg = {peso_final},
                    historial_resumen = {sql_lit(nuevo_hist)}
                WHERE id_paciente = {int(solicitud_id)}
                """
            )
        self.conn.execute(
            f"UPDATE dbo.Paciente SET solicitud_estado = {sql_lit(status)} WHERE id_paciente = {int(solicitud_id)}"
        )
        return next(
            item for item in self.listar_solicitudes_mascota() if int(item["id"]) == int(solicitud_id)
        )

    def existe_colegiatura_veterinario(self, cmvp: str) -> bool:
        codigo = str(cmvp or "").strip()
        if not codigo:
            return False
        row = self.conn.query_one(
            "SELECT TOP 1 1 AS ok FROM dbo.Veterinario WHERE LOWER(numero_colegiatura) = LOWER(@cmvp)",
            params={"cmvp": codigo},
        )
        return row is not None

    def crear_doctor(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        cmvp = str(datos.get("cmvp") or "").strip()
        if not cmvp:
            raise ValueError(
                "El número de colegiatura CMVP es obligatorio para registrar un médico veterinario."
            )
        if self.existe_colegiatura_veterinario(cmvp):
            raise ValueError(
                f"El número de colegiatura '{cmvp}' ya está registrado para otro profesional veterinario."
            )
        email = str(datos.get("correo", datos.get("email", ""))).strip().lower()
        user = (
            self.conn.query_one(
                "SELECT TOP 1 id FROM dbo.usuarios WHERE LOWER(email) = LOWER(@email)",
                params={"email": email},
            )
            if email
            else None
        )
        spec_name = str(datos.get("especialidad") or "Medicina General").strip() or "Medicina General"
        spec_id_override = int(datos["especialidad_id"]) if datos.get("especialidad_id") else 0
        nombre_completo = str(datos.get("nombres") or datos.get("nombre") or "Doctor").strip()
        apellidos = str(datos.get("apellidos") or "").strip()
        if not apellidos and " " in nombre_completo:
            nombre_completo, apellidos = nombre_completo.split(" ", 1)
        uid_val = datos.get("usuario_id") or (user["id"] if user else None)
        tel_val = str(datos.get("telefono", "")).strip()
        fecha_cont = str(datos.get("fecha_contratacion", date.today().isoformat()))[:10]

        try:
            new_id_str = self.conn.scalar(
                """
                SET XACT_ABORT ON;
                BEGIN TRY
                    BEGIN TRANSACTION;
                    DECLARE @spec_id INT = @spec_id_override;
                    IF @spec_id IS NULL OR @spec_id <= 0
                    BEGIN
                        SELECT TOP 1 @spec_id = Id_especialidad
                        FROM dbo.Especialidad
                        WHERE LOWER(Nombre) = LOWER(@spec_name);

                        IF @spec_id IS NULL
                        BEGIN
                            INSERT INTO dbo.Especialidad (Nombre, Descripcion)
                            VALUES (@spec_name, N'Especialidad registrada desde panel administrativo');
                            SET @spec_id = CAST(SCOPE_IDENTITY() AS INT);
                        END;
                    END;

                    INSERT INTO dbo.Veterinario (
                        usuario_id, Id_especialidad, numero_colegiatura,
                        nombres, Apellidos, Telefono, Fecha_contratacion
                    )
                    VALUES (
                        @uid_val, @spec_id, @cmvp,
                        @nombres, @apellidos, @tel_val, @fecha_cont
                    );
                    DECLARE @new_vet_id INT = CAST(SCOPE_IDENTITY() AS INT);

                    COMMIT TRANSACTION;
                    SELECT CAST(@new_vet_id AS VARCHAR(20)) AS id;
                END TRY
                BEGIN CATCH
                    IF @@TRANCOUNT > 0
                        ROLLBACK TRANSACTION;
                    THROW;
                END CATCH;
                """,
                params={
                    "spec_id_override": spec_id_override,
                    "spec_name": spec_name,
                    "uid_val": int(uid_val) if uid_val is not None else None,
                    "cmvp": cmvp,
                    "nombres": nombre_completo,
                    "apellidos": apellidos,
                    "tel_val": tel_val,
                    "fecha_cont": fecha_cont,
                },
            )
        except ErrorRegistroDuplicadoSQLServer as exc:
            raise ValueError(
                f"El número de colegiatura '{cmvp}' o el usuario asignado ya está registrado en dbo.Veterinario."
            ) from exc

        if not new_id_str or not str(new_id_str).strip().isdigit():
            raise ErrorConsultaSQLServer(
                "No se pudo confirmar la inserción del médico veterinario en SQL Server."
            )
        new_id = int(str(new_id_str).strip())
        verificado = self.conn.query_one(
            """
            SELECT TOP 1
                v.Id_veterinario AS id,
                v.usuario_id,
                v.Id_especialidad AS especialidad_id,
                esp.Nombre AS especialidad,
                v.numero_colegiatura AS cmvp,
                v.nombres,
                v.Apellidos AS apellidos,
                v.Telefono AS telefono,
                CONVERT(VARCHAR(10), v.Fecha_contratacion, 23) AS fecha_contratacion
            FROM dbo.Veterinario v
            JOIN dbo.Especialidad esp ON esp.Id_especialidad = v.Id_especialidad
            WHERE v.Id_veterinario = @vid
            """,
            params={"vid": new_id},
        )
        if not verificado:
            raise ErrorConsultaSQLServer(
                "No se pudo verificar la persistencia del médico veterinario en dbo.Veterinario."
            )
        return {**datos, **verificado, "id": new_id}

    def crear_personal(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        """
        Registra de forma atómica y transaccional en SQL Server a un miembro del personal
        ('doctor' o 'admin'), insertando en dbo.usuarios y (si es doctor) en dbo.Especialidad
        y dbo.Veterinario dentro de una única transacción con verificación posterior SELECT.
        """
        nombre = str(datos.get("nombre", "")).strip()
        email = str(datos.get("email", "")).strip().lower()
        rol = str(datos.get("rol", "")).strip().lower()
        estado = str(datos.get("estado", "activo")).strip().lower()
        telefono = str(datos.get("telefono", "")).strip()
        raw_pwd = str(datos.get("password_hash") or datos.get("password") or "")
        cmvp = str(datos.get("cmvp") or "").strip()
        spec_name = str(datos.get("especialidad") or "Medicina General").strip() or "Medicina General"
        fecha_cont = str(datos.get("fecha_contratacion", date.today().isoformat()))[:10]

        if len(nombre) < 2:
            raise ValueError("El nombre y apellido del personal deben tener al menos 2 caracteres.")
        if "@" not in email or "." not in email.split("@")[-1] or " " in email:
            raise ValueError("El correo electrónico suministrado no tiene un formato válido.")
        if rol not in ("doctor", "admin"):
            raise ValueError("El rol asignado debe ser 'doctor' o 'admin'.")
        if not raw_pwd or (not raw_pwd.startswith(_PBKDF2_PREFIX) and len(raw_pwd) < 6):
            raise ValueError("La contraseña debe tener al menos 6 caracteres.")

        if self.obtener_usuario_por_email(email):
            raise ValueError("Ya existe una cuenta registrada con este correo electrónico.")

        if rol == "doctor":
            if not cmvp:
                raise ValueError(
                    "El número de colegiatura CMVP es obligatorio para registrar un médico veterinario."
                )
            if self.existe_colegiatura_veterinario(cmvp):
                raise ValueError(
                    f"El número de colegiatura '{cmvp}' ya está registrado para otro profesional veterinario."
                )

        pwd_hash = hashear_password(raw_pwd)
        parts = nombre.split(" ", 1)
        nombres_vet = parts[0]
        apellidos_vet = parts[1] if len(parts) > 1 else ""
        es_doctor = 1 if rol == "doctor" else 0

        try:
            nuevo_uid_str = self.conn.scalar(
                """
                SET XACT_ABORT ON;
                BEGIN TRY
                    BEGIN TRANSACTION;

                    INSERT INTO dbo.usuarios (nombre, email, password_hash, rol, estado, telefono)
                    VALUES (@nombre, @email, @pwd_hash, @rol, @estado, @telefono);
                    DECLARE @new_uid INT = CAST(SCOPE_IDENTITY() AS INT);

                    IF @es_doctor = 1
                    BEGIN
                        DECLARE @spec_id INT = (
                            SELECT TOP 1 Id_especialidad
                            FROM dbo.Especialidad
                            WHERE LOWER(Nombre) = LOWER(@spec_name)
                        );
                        IF @spec_id IS NULL
                        BEGIN
                            INSERT INTO dbo.Especialidad (Nombre, Descripcion)
                            VALUES (@spec_name, N'Especialidad registrada desde panel administrativo');
                            SET @spec_id = CAST(SCOPE_IDENTITY() AS INT);
                        END;

                        INSERT INTO dbo.Veterinario (
                            usuario_id, Id_especialidad, numero_colegiatura,
                            nombres, Apellidos, Telefono, Fecha_contratacion
                        )
                        VALUES (
                            @new_uid, @spec_id, @cmvp,
                            @nombres_vet, @apellidos_vet, @telefono, @fecha_cont
                        );
                    END;

                    COMMIT TRANSACTION;
                    SELECT CAST(@new_uid AS VARCHAR(20)) AS id;
                END TRY
                BEGIN CATCH
                    IF @@TRANCOUNT > 0
                        ROLLBACK TRANSACTION;
                    THROW;
                END CATCH;
                """,
                params={
                    "nombre": nombre,
                    "email": email,
                    "pwd_hash": pwd_hash,
                    "rol": rol,
                    "estado": estado,
                    "telefono": telefono,
                    "es_doctor": es_doctor,
                    "spec_name": spec_name,
                    "cmvp": cmvp,
                    "nombres_vet": nombres_vet,
                    "apellidos_vet": apellidos_vet,
                    "fecha_cont": fecha_cont,
                },
            )
        except ErrorRegistroDuplicadoSQLServer as exc:
            raise ValueError(
                "Ya existe un registro en SQL Server con ese correo electrónico o número de colegiatura CMVP."
            ) from exc

        if not nuevo_uid_str or not str(nuevo_uid_str).strip().isdigit():
            raise ErrorConsultaSQLServer(
                "No se pudo completar el registro transaccional del personal en SQL Server."
            )

        nuevo_uid = int(str(nuevo_uid_str).strip())
        usuario_persistido = self.obtener_usuario_por_id(nuevo_uid)
        if not usuario_persistido or int(usuario_persistido.get("id", 0)) != nuevo_uid:
            raise ErrorConsultaSQLServer(
                "No se pudo verificar la persistencia del nuevo personal en dbo.usuarios de SQL Server."
            )
        if rol == "doctor" and not usuario_persistido.get("cmvp"):
            raise ErrorConsultaSQLServer(
                "No se pudo verificar la persistencia del médico veterinario en dbo.Veterinario de SQL Server."
            )
        return usuario_persistido

    def obtener_usuario_por_id(self, usuario_id: int) -> Optional[Dict[str, Any]]:
        return self._user_row(
            "u.id = @uid",
            params={"uid": int(usuario_id)},
            include_password_hash=False,
        )

    def listar_usuarios(self) -> List[Dict[str, Any]]:
        return self.conn.query_json(
            """
            SELECT
                u.id, u.nombre, u.email, u.rol, u.estado, u.telefono,
                CONVERT(VARCHAR(19), u.creado_en, 120) AS creado_en,
                COALESCE(d.tipo_documento, 'DNI') AS tipo_documento,
                CASE WHEN d.dni LIKE 'CLI%' OR d.dni LIKE 'EXT%' THEN NULL ELSE d.dni END AS documento,
                v.Id_veterinario AS id_veterinario,
                v.numero_colegiatura AS cmvp,
                esp.Nombre AS especialidad,
                CONVERT(VARCHAR(10), v.Fecha_contratacion, 23) AS fecha_contratacion
            FROM dbo.usuarios u
            LEFT JOIN dbo.Dueno d ON d.usuario_id = u.id
            LEFT JOIN dbo.Veterinario v ON v.usuario_id = u.id
            LEFT JOIN dbo.Especialidad esp ON esp.Id_especialidad = v.Id_especialidad
            ORDER BY u.id ASC
            """
        )

    def listar_personal(self) -> List[Dict[str, Any]]:
        """
        Devuelve todo el personal médico y administrativo persistido en SQL Server,
        combinando dbo.usuarios (rol IN ('doctor', 'admin')) con dbo.Veterinario y dbo.Especialidad,
        incluyendo tanto los registros iniciales (SEED) como todo el personal registrado posteriormente.
        """
        return self.conn.query_json(
            """
            SELECT
                COALESCE(u.id, 10000 + v.Id_veterinario) AS id,
                u.id AS usuario_id,
                v.Id_veterinario AS id_veterinario,
                COALESCE(u.nombre, LTRIM(RTRIM(v.nombres + ' ' + v.Apellidos))) AS nombre,
                COALESCE(u.email, 'doctor@patitasfelices.pe') AS email,
                COALESCE(u.rol, 'doctor') AS rol,
                COALESCE(u.estado, 'activo') AS estado,
                COALESCE(NULLIF(u.telefono, ''), v.Telefono, '') AS telefono,
                v.numero_colegiatura AS cmvp,
                COALESCE(
                    esp.Nombre,
                    CASE WHEN u.rol = 'admin' THEN N'Dirección y Administración Clínica' ELSE N'Medicina General' END
                ) AS especialidad,
                COALESCE(
                    CONVERT(VARCHAR(10), v.Fecha_contratacion, 23),
                    CONVERT(VARCHAR(10), u.creado_en, 23)
                ) AS fecha_contratacion,
                COALESCE(
                    CONVERT(VARCHAR(19), u.creado_en, 120),
                    CONVERT(VARCHAR(10), v.Fecha_contratacion, 23) + ' 09:00:00'
                ) AS creado_en
            FROM dbo.usuarios u
            FULL OUTER JOIN dbo.Veterinario v ON v.usuario_id = u.id
            LEFT JOIN dbo.Especialidad esp ON esp.Id_especialidad = v.Id_especialidad
            WHERE (u.rol IN ('doctor', 'admin')) OR (v.Id_veterinario IS NOT NULL)
            ORDER BY
                CASE WHEN u.id IS NOT NULL THEN 0 ELSE 1 END ASC,
                COALESCE(u.id, v.Id_veterinario) ASC
            """
        )

    def obtener_perfil_doctor(self, usuario_actual: Dict[str, Any]) -> Dict[str, Any]:
        """Obtiene desde SQL Server (dbo.Veterinario + dbo.Especialidad) el perfil real del médico autenticado."""
        uid = usuario_actual.get("id")
        row = None
        if uid is not None:
            row = self.conn.query_one(
                """
                SELECT TOP 1
                    v.Id_veterinario AS id_veterinario,
                    v.usuario_id,
                    v.numero_colegiatura AS colegiatura,
                    esp.Nombre AS especialidad,
                    LTRIM(RTRIM(v.nombres + ' ' + v.Apellidos)) AS nombre_veterinario,
                    v.Telefono AS telefono_veterinario,
                    CONVERT(VARCHAR(10), v.Fecha_contratacion, 23) AS fecha_contratacion
                FROM dbo.Veterinario v
                LEFT JOIN dbo.Especialidad esp ON esp.Id_especialidad = v.Id_especialidad
                WHERE v.usuario_id = @uid
                ORDER BY v.Id_veterinario ASC
                """,
                params={"uid": int(uid)},
            )
        if not row:
            row = self.conn.query_one(
                """
                SELECT TOP 1
                    v.Id_veterinario AS id_veterinario,
                    v.usuario_id,
                    v.numero_colegiatura AS colegiatura,
                    esp.Nombre AS especialidad,
                    LTRIM(RTRIM(v.nombres + ' ' + v.Apellidos)) AS nombre_veterinario,
                    v.Telefono AS telefono_veterinario,
                    CONVERT(VARCHAR(10), v.Fecha_contratacion, 23) AS fecha_contratacion
                FROM dbo.Veterinario v
                LEFT JOIN dbo.Especialidad esp ON esp.Id_especialidad = v.Id_especialidad
                ORDER BY v.Id_veterinario ASC
                """
            )
        return {
            "id": uid or (row.get("id_veterinario") if row else 1),
            "id_veterinario": row.get("id_veterinario") if row else None,
            "nombre": usuario_actual.get("nombre") or (row.get("nombre_veterinario") if row else "Dr. Carlos Mendoza"),
            "email": usuario_actual.get("email") or "doctor@patitasfelices.pe",
            "telefono": usuario_actual.get("telefono") or (row.get("telefono_veterinario") if row else "987654321"),
            "colegiatura": (row.get("colegiatura") if row else None) or usuario_actual.get("cmvp") or "CMVP-10452",
            "especialidad": (row.get("especialidad") if row else None) or usuario_actual.get("especialidad") or "Medicina General e Interna",
            "horario_turno": "Lunes a Sábado · 09:00 a 18:00 (Lima)",
        }

    def actualizar_estado_usuario(
        self, usuario_id: int, nuevo_estado: str
    ) -> Optional[Dict[str, Any]]:
        self.conn.execute(
            "UPDATE dbo.usuarios SET estado = @estado WHERE id = @uid",
            params={"estado": nuevo_estado, "uid": int(usuario_id)},
        )
        return self.obtener_usuario_por_id(int(usuario_id))

    def _query_citas(self, where_order_sql: str) -> List[Dict[str, Any]]:
        rows = self.conn.query_json(
            f"""
            SELECT
                c.Id_cita AS id,
                d.usuario_id,
                c.id_paciente AS mascota_id,
                COALESCE(v.usuario_id, v.Id_veterinario) AS doctor_id,
                COALESCE(u.nombre, LTRIM(RTRIM(d.nombres + ' ' + d.apellidos)), '') AS propietario,
                COALESCE(NULLIF(d.telefono, ''), u.telefono, '') AS telefono,
                COALESCE(p.nombre, '') AS mascota_nombre,
                COALESCE(s.Nombre, '') AS servicio,
                CONVERT(VARCHAR(10), c.fecha, 23) AS fecha,
                c.hora,
                c.motivo,
                LOWER(c.estado) AS estado,
                c.whatsapp_url,
                COALESCE(h.Diagnostico, '') AS diagnostico,
                COALESCE(h.Tratamiento, '') AS tratamiento
            FROM dbo.Cita c
            JOIN dbo.Veterinario v ON v.Id_veterinario = c.Id_veterinario
            LEFT JOIN dbo.Paciente p ON p.id_paciente = c.id_paciente
            LEFT JOIN dbo.Dueno d ON d.id_dueno = p.id_dueno
            LEFT JOIN dbo.usuarios u ON u.id = d.usuario_id
            LEFT JOIN dbo.Detalle_servicios ds ON ds.Id_cita = c.Id_cita
            LEFT JOIN dbo.Servicios s ON s.Id_servicios = ds.Id_servicios
            LEFT JOIN dbo.Historial_clinico h ON h.Id_historial = (
                SELECT MAX(h2.Id_historial) FROM dbo.Historial_clinico h2 WHERE h2.Id_cita = c.Id_cita
            )
            {where_order_sql}
            """
        )
        results: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["servicio"] = WhatsAppAdapter.SERVICIOS_CODIGOS.get(
                item["servicio"], item["servicio"]
            )
            results.append(item)
        return results

    def _cita_row(self, cita_id: int) -> Optional[Dict[str, Any]]:
        items = self._query_citas(f"WHERE c.Id_cita = {int(cita_id)}")
        return items[0] if items else None

    def listar_mascotas(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        where_extra = f" AND d.usuario_id = {int(usuario_id)}" if usuario_id is not None else ""
        return self.conn.query_json(
            f"""
            SELECT
                p.id_paciente AS id,
                d.usuario_id,
                p.nombre,
                e.Nombre AS especie,
                r.nombre AS raza,
                CASE WHEN YEAR(SYSDATETIME()) - YEAR(p.fecha_nacimiento) < 0 THEN 0
                     ELSE YEAR(SYSDATETIME()) - YEAR(p.fecha_nacimiento) END AS edad,
                CAST(p.peso_kg AS FLOAT) AS peso_kg,
                COALESCE(p.historial_resumen, '') AS historial_resumen,
                p.sexo,
                CONVERT(VARCHAR(10), p.fecha_nacimiento, 23) AS fecha_nacimiento,
                p.estado,
                CONVERT(VARCHAR(19), p.fecha_registro, 120) AS creado_en,
                COALESCE(u.nombre, LTRIM(RTRIM(d.nombres + ' ' + d.apellidos))) AS propietario_nombre
            FROM dbo.Paciente p
            JOIN dbo.Dueno d ON d.id_dueno = p.id_dueno
            JOIN dbo.Razas r ON r.Id_raza = p.Id_raza
            JOIN dbo.Especie e ON e.Id_especie = r.Id_especie
            LEFT JOIN dbo.usuarios u ON u.id = d.usuario_id
            WHERE p.estado <> 'Eliminado'{where_extra}
            ORDER BY p.id_paciente ASC
            """
        )

    def crear_mascota(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        uid = int(datos["usuario_id"])
        owner_id = self._owner_id_for_user(uid)
        race_id = self._resolve_raza_id(
            str(datos.get("especie", "Perro")),
            str(datos.get("raza", "Mestizo")),
            "Registrada desde perfil de cliente",
        )
        age = max(0, int(datos.get("edad", 1)))
        birth = str(datos.get("fecha_nacimiento") or f"{max(1900, date.today().year - age):04d}-01-01")[:10]
        nombre = str(datos["nombre"]).strip()
        sexo = str(datos.get("sexo", "H")).strip()[:1].upper() or "H"
        peso = float(datos.get("peso_kg", 5.0))
        hist = str(datos.get("historial_resumen", "")).strip()
        pet_id = int(
            self.conn.scalar(
                f"""
                INSERT INTO dbo.Paciente (id_dueno, Id_raza, nombre, sexo, fecha_nacimiento, peso_kg, historial_resumen, estado)
                OUTPUT INSERTED.id_paciente
                VALUES ({owner_id}, {race_id}, {sql_lit(nombre)}, {sql_lit(sexo)}, {sql_lit(birth)}, {peso}, {sql_lit(hist)}, 'Activo')
                """
            )
        )
        return self._mascota_row(pet_id) or {"id": pet_id}

    def eliminar_mascota(self, mascota_id: int, usuario_id: Optional[int] = None) -> bool:
        if usuario_id is None:
            updated = self.conn.scalar(
                f"""
                UPDATE dbo.Paciente
                SET estado = 'Eliminado'
                OUTPUT INSERTED.id_paciente
                WHERE id_paciente = {int(mascota_id)} AND estado <> 'Eliminado'
                """
            )
        else:
            updated = self.conn.scalar(
                f"""
                UPDATE dbo.Paciente
                SET estado = 'Eliminado'
                OUTPUT INSERTED.id_paciente
                WHERE id_paciente = {int(mascota_id)}
                  AND id_dueno = (SELECT TOP 1 id_dueno FROM dbo.Dueno WHERE usuario_id = {int(usuario_id)})
                  AND estado <> 'Eliminado'
                """
            )
        return bool(updated.strip())

    def obtener_disponibilidad_horarios(self, fecha: str) -> Dict[str, Any]:
        horarios = ["08:30", "10:00", "11:30", "13:00", "15:30", "17:00", "18:30"]
        rows = self.conn.query_json(
            f"""
            SELECT LEFT(hora, 5) AS hora, COUNT(*) AS ocupados
            FROM dbo.Cita
            WHERE fecha = {sql_lit(fecha[:10])} AND LOWER(estado) <> 'cancelada'
            GROUP BY LEFT(hora, 5)
            """
        )
        counts = {str(r["hora"])[:5]: int(r["ocupados"]) for r in rows}
        return {
            "fecha": fecha,
            "capacidad_por_turno": 3,
            "horarios": {
                h: {
                    "ocupados": counts.get(h, 0),
                    "capacidad_maxima": 3,
                    "disponible": counts.get(h, 0) < 3,
                }
                for h in horarios
            },
        }

    def _resolve_cita_paciente(self, datos: Dict[str, Any]) -> int:
        pet_id = datos.get("mascota_id")
        if pet_id is not None:
            pet = self.conn.query_one(
                f"""
                SELECT TOP 1 p.id_paciente, d.usuario_id, d.id_dueno
                FROM dbo.Paciente p
                JOIN dbo.Dueno d ON d.id_dueno = p.id_dueno
                WHERE p.id_paciente = {int(pet_id)}
                """
            )
            if pet:
                if datos.get("usuario_id") is not None and int(pet.get("usuario_id") or -1) != int(
                    datos["usuario_id"]
                ):
                    raise ValueError("La mascota no pertenece al usuario de la cita.")
                telefono = str(datos.get("telefono", "")).strip()
                if telefono:
                    self.conn.execute(
                        f"UPDATE dbo.Dueno SET telefono = {sql_lit(telefono)} WHERE id_dueno = {int(pet['id_dueno'])} AND telefono = ''"
                    )
                return int(pet["id_paciente"])

        propietario = str(datos.get("propietario", "")).strip() or "Cliente"
        telefono = str(datos.get("telefono", "")).strip()
        mascota_nombre = str(datos.get("mascota_nombre") or datos.get("mascota") or "Mascota").strip()
        if datos.get("usuario_id") is not None:
            owner_id = self._owner_id_for_user(int(datos["usuario_id"]), create=True)
            if telefono and owner_id:
                self.conn.execute(
                    f"UPDATE dbo.Dueno SET telefono = {sql_lit(telefono)} WHERE id_dueno = {owner_id} AND telefono = ''"
                )
        else:
            parts = propietario.split(" ", 1)
            nombres, apellidos = parts[0], (parts[1] if len(parts) > 1 else "")
            existing_owner = self.conn.query_one(
                f"""
                SELECT TOP 1 id_dueno
                FROM dbo.Dueno
                WHERE LOWER(nombres) = LOWER({sql_lit(nombres)})
                  AND LOWER(apellidos) = LOWER({sql_lit(apellidos)})
                  AND telefono = {sql_lit(telefono)}
                """
            )
            if existing_owner:
                owner_id = int(existing_owner["id_dueno"])
            else:
                ext_dni = f"EXT{secrets.token_hex(4).upper()}"
                owner_id = int(
                    self.conn.scalar(
                        f"""
                        INSERT INTO dbo.Dueno (usuario_id, dni, tipo_documento, nombres, apellidos, telefono)
                        OUTPUT INSERTED.id_dueno
                        VALUES (NULL, {sql_lit(ext_dni)}, 'DNI', {sql_lit(nombres)}, {sql_lit(apellidos)}, {sql_lit(telefono)})
                        """
                    )
                )
        existing_pet = self.conn.query_one(
            f"SELECT TOP 1 id_paciente FROM dbo.Paciente WHERE id_dueno = {owner_id} AND LOWER(nombre) = LOWER({sql_lit(mascota_nombre)})"
        )
        if existing_pet:
            return int(existing_pet["id_paciente"])
        raza = self.conn.query_one("SELECT TOP 1 Id_raza FROM dbo.Razas ORDER BY Id_raza")
        raza_id = int(raza["Id_raza"]) if raza else 1
        today_str = date.today().isoformat()
        return int(
            self.conn.scalar(
                f"""
                INSERT INTO dbo.Paciente (id_dueno, Id_raza, nombre, sexo, fecha_nacimiento, peso_kg, historial_resumen, estado)
                OUTPUT INSERTED.id_paciente
                VALUES ({owner_id}, {raza_id}, {sql_lit(mascota_nombre)}, 'H', {sql_lit(today_str)}, 5.0, '', 'Activo')
                """
            )
        )

    def crear_cita(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        fecha = str(datos["fecha"]).strip()[:10]
        hora = str(datos["hora"]).strip()[:5]
        occ_str = self.conn.scalar(
            f"SELECT CAST(COUNT(*) AS VARCHAR(10)) FROM dbo.Cita WHERE fecha = {sql_lit(fecha)} AND LEFT(hora, 5) = {sql_lit(hora)} AND LOWER(estado) <> 'cancelada'"
        )
        occupied = int(occ_str) if occ_str.isdigit() else 0
        if occupied >= 3:
            raise ValueError(
                f"El horario {hora} del {fecha} ya cuenta con sus 3 cupos médicos ocupados. Elige otro horario."
            )
        vet_id = None
        doctor = datos.get("doctor_id")
        if doctor is not None:
            found = self.conn.query_one(
                f"SELECT TOP 1 Id_veterinario FROM dbo.Veterinario WHERE usuario_id = {int(doctor)}"
            )
            if not found:
                found = self.conn.query_one(
                    f"SELECT TOP 1 Id_veterinario FROM dbo.Veterinario WHERE Id_veterinario = {int(doctor)}"
                )
            if found:
                vet_id = int(found["Id_veterinario"])
        if vet_id is None:
            found = self.conn.query_one(
                "SELECT TOP 1 Id_veterinario FROM dbo.Veterinario ORDER BY Id_veterinario"
            )
            if not found:
                raise ValueError("No hay veterinarios registrados para asignar la cita.")
            vet_id = int(found["Id_veterinario"])

        pet_id = self._resolve_cita_paciente(datos)
        service_key = str(datos.get("servicio", "")).strip()
        service_name = WhatsAppAdapter.SERVICIOS_NOMBRES.get(
            service_key, service_key or "Consulta general"
        )
        service = self.conn.query_one(
            f"SELECT TOP 1 Id_servicios, CAST(Precio AS FLOAT) AS Precio FROM dbo.Servicios WHERE LOWER(Nombre) = LOWER({sql_lit(service_name)})"
        )
        if not service:
            service = self.conn.query_one(
                "SELECT TOP 1 Id_servicios, CAST(Precio AS FLOAT) AS Precio FROM dbo.Servicios ORDER BY Id_servicios"
            )

        motivo = str(datos.get("motivo", "")).strip()
        estado = str(datos.get("estado", "pendiente")).lower()
        w_url = str(datos.get("whatsapp_url", "")).strip()
        cita_id = int(
            self.conn.scalar(
                f"""
                INSERT INTO dbo.Cita (Id_veterinario, id_paciente, fecha, hora, motivo, estado, whatsapp_url)
                OUTPUT INSERTED.Id_cita
                VALUES ({vet_id}, {pet_id}, {sql_lit(fecha)}, {sql_lit(hora)}, {sql_lit(motivo)}, {sql_lit(estado)}, {sql_lit(w_url)})
                """
            )
        )
        if service:
            self.conn.execute(
                f"INSERT INTO dbo.Detalle_servicios (Id_cita, Id_servicios, precio_aplicado) VALUES ({cita_id}, {int(service['Id_servicios'])}, {float(service['Precio'])})"
            )
        if datos.get("diagnostico") or datos.get("tratamiento"):
            diag = datos.get("diagnostico", "") or ""
            trat = datos.get("tratamiento", "") or ""
            self.conn.execute(
                f"INSERT INTO dbo.Historial_clinico (Id_cita, Diagnostico, Tratamiento) VALUES ({cita_id}, {sql_lit(diag)}, {sql_lit(trat)})"
            )
        return self._cita_row(cita_id) or {"id": cita_id}

    def listar_citas(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if usuario_id is None:
            return self._query_citas("ORDER BY c.fecha, c.hora, c.Id_cita")
        return self._query_citas(
            f"WHERE d.usuario_id = {int(usuario_id)} ORDER BY c.fecha, c.hora, c.Id_cita"
        )

    def actualizar_cita_doctor(
        self,
        cita_id: int,
        estado: str,
        diagnostico: str,
        tratamiento: str,
        doctor_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        if doctor_id is None:
            updated = self.conn.scalar(
                f"UPDATE dbo.Cita SET estado = {sql_lit(estado)} OUTPUT INSERTED.Id_cita WHERE Id_cita = {int(cita_id)}"
            )
        else:
            vet = self.conn.query_one(
                f"SELECT TOP 1 Id_veterinario FROM dbo.Veterinario WHERE usuario_id = {int(doctor_id)}"
            )
            if not vet:
                vet = self.conn.query_one(
                    f"SELECT TOP 1 Id_veterinario FROM dbo.Veterinario WHERE Id_veterinario = {int(doctor_id)}"
                )
            vet_val = int(vet["Id_veterinario"]) if vet else None
            updated = self.conn.scalar(
                f"UPDATE dbo.Cita SET estado = {sql_lit(estado)}, Id_veterinario = COALESCE({sql_lit(vet_val)}, Id_veterinario) OUTPUT INSERTED.Id_cita WHERE Id_cita = {int(cita_id)}"
            )
        if not updated.strip():
            return None
        hist = self.conn.query_one(
            f"SELECT TOP 1 Id_historial FROM dbo.Historial_clinico WHERE Id_cita = {int(cita_id)} ORDER BY Id_historial DESC"
        )
        if hist:
            self.conn.execute(
                f"UPDATE dbo.Historial_clinico SET Diagnostico = {sql_lit(diagnostico)}, Tratamiento = {sql_lit(tratamiento)} WHERE Id_historial = {int(hist['Id_historial'])}"
            )
        elif diagnostico or tratamiento:
            self.conn.execute(
                f"INSERT INTO dbo.Historial_clinico (Id_cita, Diagnostico, Tratamiento) VALUES ({int(cita_id)}, {sql_lit(diagnostico)}, {sql_lit(tratamiento)})"
            )
        return self._cita_row(cita_id)

    def listar_productos(self, solo_activos: bool = True) -> List[Dict[str, Any]]:
        where_clause = "WHERE activo = 1 " if solo_activos else ""
        return self.conn.query_json(
            f"""
            SELECT id, codigo, nombre, categoria, descripcion,
                   CAST(precio AS FLOAT) AS precio, stock, CAST(activo AS INT) AS activo
            FROM dbo.productos
            {where_clause}ORDER BY id ASC
            """
        )

    def obtener_producto(self, producto_id: int) -> Optional[Dict[str, Any]]:
        return self.conn.query_one(
            f"""
            SELECT TOP 1 id, codigo, nombre, categoria, descripcion,
                         CAST(precio AS FLOAT) AS precio, stock, CAST(activo AS INT) AS activo
            FROM dbo.productos
            WHERE id = {int(producto_id)}
            """
        )

    def descontar_stock_producto(self, producto_id: int, cantidad: int) -> bool:
        updated = self.conn.scalar(
            f"""
            UPDATE dbo.productos
            SET stock = stock - {int(cantidad)}
            OUTPUT INSERTED.id
            WHERE id = {int(producto_id)} AND stock >= {int(cantidad)}
            """
        )
        return bool(updated.strip())

    def registrar_venta_y_detalles(
        self, cabecera: Dict[str, Any], detalles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        uid = int(cabecera["usuario_id"])
        owner_id = self._owner_id_for_user(uid)
        doc_cliente = str(cabecera.get("cliente_documento") or "").strip()
        nombre_cliente = str(cabecera.get("cliente_nombre") or "Cliente Patitas Felices").strip()
        if owner_id is None:
            existing_dueno = (
                self.conn.query_one(
                    f"SELECT TOP 1 id_dueno FROM dbo.Dueno WHERE dni = {sql_lit(doc_cliente)}"
                )
                if doc_cliente and doc_cliente != "00000000"
                else None
            )
            if existing_dueno:
                owner_id = int(existing_dueno["id_dueno"])
            else:
                parts = nombre_cliente.split(" ", 1)
                dni_guest = (
                    doc_cliente
                    if doc_cliente and doc_cliente != "00000000"
                    else f"EXT{secrets.token_hex(4).upper()}"
                )
                tipo_guest = "RUC" if len(doc_cliente) == 11 else "DNI"
                owner_id = int(
                    self.conn.scalar(
                        f"""
                        INSERT INTO dbo.Dueno (usuario_id, dni, tipo_documento, nombres, apellidos, telefono)
                        OUTPUT INSERTED.id_dueno
                        VALUES (NULL, {sql_lit(dni_guest)}, {sql_lit(tipo_guest)}, {sql_lit(parts[0])}, {sql_lit(parts[1] if len(parts) > 1 else '')}, '')
                        """
                    )
                )
        elif doc_cliente and doc_cliente != "00000000":
            current_dueno = self.conn.query_one(
                f"SELECT TOP 1 dni FROM dbo.Dueno WHERE id_dueno = {owner_id}"
            )
            if current_dueno and (
                str(current_dueno["dni"]).startswith("CLI")
                or str(current_dueno["dni"]).startswith("EXT")
            ):
                dup_dni = self.conn.query_one(
                    f"SELECT TOP 1 1 AS ok FROM dbo.Dueno WHERE dni = {sql_lit(doc_cliente)} AND id_dueno <> {owner_id}"
                )
                if not dup_dni:
                    tipo_doc = "RUC" if len(doc_cliente) == 11 else "DNI"
                    self.conn.execute(
                        f"UPDATE dbo.Dueno SET dni = {sql_lit(doc_cliente)}, tipo_documento = {sql_lit(tipo_doc)} WHERE id_dueno = {owner_id}"
                    )

        number_text = str(cabecera["numero_boleta"])
        series, _, suffix = number_text.partition("-")
        series = series or "B001"
        number = int(suffix or "1")
        if self.conn.query_one(
            f"SELECT TOP 1 1 AS ok FROM dbo.Factura WHERE serie = {sql_lit(series)} AND numero = {number}"
        ):
            raise ValueError(f"El numero de boleta {number_text} ya existe.")

        estado_cap = str(cabecera.get("estado", "pagado")).capitalize()
        invoice_id = int(
            self.conn.scalar(
                f"""
                INSERT INTO dbo.Factura (id_dueno, tipo, serie, numero, subtotal, igv, total, estado)
                OUTPUT INSERTED.id_factura
                VALUES ({owner_id}, 'Boleta', {sql_lit(series)}, {number}, {float(cabecera['subtotal'])}, {float(cabecera['igv'])}, {float(cabecera['total'])}, {sql_lit(estado_cap)})
                """
            )
        )
        for detail in detalles:
            self.conn.execute(
                f"""
                INSERT INTO dbo.detalle_ventas (id_factura, producto_id, cantidad, precio_unitario, subtotal)
                VALUES ({invoice_id}, {int(detail['producto_id'])}, {int(detail['cantidad'])}, {float(detail['precio_unitario'])}, {float(detail['subtotal'])})
                """
            )
        metodo_pago = cabecera.get("metodo_pago", "Tarjeta / Yape")
        self.conn.execute(
            f"""
            INSERT INTO dbo.Pago (id_factura, metodo_pago, monto, estado)
            VALUES ({invoice_id}, {sql_lit(metodo_pago)}, {float(cabecera['total'])}, {sql_lit(estado_cap)})
            """
        )
        return self._factura_row(invoice_id) or {"id": invoice_id}

    def _query_facturas(self, where_order_sql: str) -> List[Dict[str, Any]]:
        facturas = self.conn.query_json(
            f"""
            SELECT
                f.id_factura,
                f.id_factura AS id,
                f.Id_cita,
                f.id_dueno,
                d.usuario_id,
                f.tipo,
                f.serie,
                f.numero,
                (f.serie + '-' + RIGHT('000000' + CAST(f.numero AS VARCHAR(10)), 6)) AS numero_boleta,
                COALESCE(u.nombre, LTRIM(RTRIM(d.nombres + ' ' + d.apellidos)), 'Cliente Patitas Felices') AS cliente_nombre,
                COALESCE(CASE WHEN d.dni LIKE 'CLI%' OR d.dni LIKE 'EXT%' THEN NULL ELSE d.dni END, '00000000') AS cliente_documento,
                CONVERT(VARCHAR(19), f.fecha_emision, 120) AS fecha_emision,
                CONVERT(VARCHAR(19), f.fecha_emision, 120) AS creado_en,
                CAST(f.subtotal AS FLOAT) AS subtotal,
                CAST(f.igv AS FLOAT) AS igv,
                CAST(f.total AS FLOAT) AS total,
                COALESCE(pg.metodo_pago, 'Tarjeta / Yape') AS metodo_pago,
                f.estado,
                f.pdf_url
            FROM dbo.Factura f
            LEFT JOIN dbo.Dueno d ON d.id_dueno = f.id_dueno
            LEFT JOIN dbo.usuarios u ON u.id = d.usuario_id
            LEFT JOIN dbo.Pago pg ON pg.id_pago = (
                SELECT MAX(p2.id_pago) FROM dbo.Pago p2 WHERE p2.id_factura = f.id_factura
            )
            {where_order_sql}
            """
        )
        if not facturas:
            return []
        inv_ids = [int(f["id_factura"]) for f in facturas]
        ids_csv = ",".join(str(i) for i in inv_ids)
        detalles_rows = self.conn.query_json(
            f"""
            SELECT
                dv.id,
                dv.id_factura,
                dv.producto_id,
                pr.nombre AS producto_nombre,
                dv.cantidad,
                CAST(dv.precio_unitario AS FLOAT) AS precio_unitario,
                CAST(dv.subtotal AS FLOAT) AS subtotal
            FROM dbo.detalle_ventas dv
            JOIN dbo.productos pr ON pr.id = dv.producto_id
            WHERE dv.id_factura IN ({ids_csv})
            ORDER BY dv.id
            """
        )
        detalles_map: Dict[int, List[Dict[str, Any]]] = {iid: [] for iid in inv_ids}
        for d in detalles_rows:
            det_dict = dict(d)
            detalles_map[int(det_dict["id_factura"])].append(det_dict)
        for f in facturas:
            f["detalles"] = detalles_map.get(int(f["id_factura"]), [])
        return facturas

    def _factura_row(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        items = self._query_facturas(f"WHERE f.id_factura = {int(invoice_id)}")
        return items[0] if items else None

    def listar_ventas(self) -> List[Dict[str, Any]]:
        return self._query_facturas("ORDER BY f.id_factura DESC")

    def obtener_todas_las_16_tablas(self) -> Dict[str, List[Dict[str, Any]]]:
        resultado: Dict[str, List[Dict[str, Any]]] = {}
        for tabla in self.NOMBRES_16_TABLAS:
            try:
                if tabla == "usuarios":
                    resultado[tabla] = self.conn.query_json(
                        """
                        SELECT
                            id,
                            nombre,
                            email,
                            '[PROTEGIDO PBKDF2-SHA256]' AS password_hash,
                            rol,
                            estado,
                            telefono,
                            CONVERT(VARCHAR(19), creado_en, 120) AS creado_en
                        FROM dbo.usuarios
                        ORDER BY id ASC
                        """
                    )
                else:
                    resultado[tabla] = self.conn.query_json(f"SELECT * FROM dbo.{tabla}")
            except Exception:
                resultado[tabla] = []
        return resultado


# =============================================================================
# 4. FÁBRICA DE ADAPTADORES - FACTORY METHOD (SQL SERVER)
# =============================================================================
def obtener_adaptador_bd() -> IDatabaseAdapter:
    return SQLServerDatabaseAdapter(
        database=os.getenv("SQLSERVER_DATABASE", "PatitasFelices_DB"),
        server=os.getenv("SQLSERVER_SERVER", "localhost"),
    )
