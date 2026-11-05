"""
PATRÓN ADAPTER (Estructural - GoF)
Implementa el desacoplamiento de BD (SQLite y Supabase PostgreSQL REST) y WhatsApp.
Integra el modelo completo de 16 tablas basado en `prueba_1.erd.json`.
"""

from abc import ABC, abstractmethod
import hashlib
import hmac
from pathlib import Path
import secrets
import time
from urllib.parse import quote
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import httpx

# Cargar automáticamente variables de entorno desde .env si existe
_env_file = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_file.is_file():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())


# =============================================================================
# 0. UTILIDADES CRIPTOGRÁFICAS DE CONTRASEÑAS (PBKDF2-HMAC-SHA256)
# =============================================================================

_PBKDF2_PREFIX = "pbkdf2_sha256$"
_PBKDF2_ITERATIONS = 100_000


def hashear_password(password_plano: str) -> str:
    """Genera un hash criptográfico PBKDF2-HMAC-SHA256 con sal aleatoria de 128 bits."""
    if not password_plano or str(password_plano).startswith(_PBKDF2_PREFIX):
        return str(password_plano)
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        str(password_plano).encode("utf-8"),
        salt.encode("utf-8"),
        _PBKDF2_ITERATIONS,
    ).hex()
    return f"{_PBKDF2_PREFIX}{salt}${dk}"


def verificar_password(password_plano: str, hash_almacenado: str) -> bool:
    """
    Verifica de forma segura (tiempo constante) una contraseña contra su hash PBKDF2.
    Mantiene retrocompatibilidad con cuentas preexistentes en nube si aún no tienen prefijo.
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
            "sha256",
            plano_str.encode("utf-8"),
            salt.encode("utf-8"),
            _PBKDF2_ITERATIONS,
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
            f"Hola, Patitas Felices. Soy {cliente}. "
            f"Acabo de realizar la compra con Boleta N° {numero_boleta} "
            f"por un total de S/ {total:.2f}. Solicito coordinación de entrega."
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
    def actualizar_documento_usuario(self, usuario_id: int, tipo_documento: str, documento: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def cambiar_password_usuario(self, usuario_id: int, password_actual: str, password_nueva: str) -> bool:
        pass

    @abstractmethod
    def listar_compras_usuario(self, usuario_id: int) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def crear_solicitud_mascota(
        self, usuario_id: int, mascota_id: int, tipo: str, motivo: str, datos_nuevos: Optional[Dict[str, Any]] = None
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
    def actualizar_estado_usuario(self, usuario_id: int, nuevo_estado: str) -> Optional[Dict[str, Any]]:
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
        self, cita_id: int, estado: str, diagnostico: str, tratamiento: str, doctor_id: Optional[int] = None
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
# 3. ADAPTER SQLITE LOCAL
# =============================================================================

class SQLiteDatabaseAdapter(IDatabaseAdapter):
    """Adapter concreto autoinicializable (SQLite)."""

    NOMBRES_16_TABLAS = [
        "Dueno", "Especie", "Razas", "Paciente", "Especialidad", "Veterinario",
        "Servicios", "Cita", "Detalle_servicios", "Historial_clinico", "Receta",
        "Factura", "Pago", "usuarios", "productos", "detalle_ventas",
    ]

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            default_file = base_dir / "database" / "patitas_felices.db"
            default_file.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(default_file)
        else:
            self.db_path = db_path
        self._persistent_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self.inicializar_esquema()

    def _get_connection(self) -> sqlite3.Connection:
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _close_if_file(self, conn: sqlite3.Connection) -> None:
        if self._persistent_conn is None:
            conn.close()

    def _owner_id_for_user(self, conn: sqlite3.Connection, usuario_id: int, create: bool = True) -> Optional[int]:
        row = conn.execute("SELECT id_dueno FROM Dueno WHERE usuario_id = ?", (usuario_id,)).fetchone()
        if row: return int(row[0])
        user = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        if not user or not create: return None
        parts = str(user["nombre"] or "Cliente").strip().split(" ", 1)
        doc = user["documento"] or f"CLI{usuario_id:05d}"
        cur = conn.execute("INSERT INTO Dueno (usuario_id,dni,tipo_documento,correo,nombres,apellidos,telefono) VALUES (?,?,?,?,?,?,?)",(usuario_id,doc,user["tipo_documento"] or "DNI",user["email"].lower(),parts[0],parts[1] if len(parts)>1 else "",user["telefono"] or ""))
        return int(cur.lastrowid)

    def _mascota_row(self, conn: sqlite3.Connection, mascota_id: int) -> Optional[Dict[str, Any]]:
        row=conn.execute("SELECT p.id_paciente AS id,d.usuario_id,p.nombre,e.Nombre AS especie,r.nombre AS raza,p.edad,p.peso_kg,p.historial_resumen,p.sexo,p.fecha_nacimiento,p.estado,p.fecha_registro AS creado_en,COALESCE(u.nombre,d.nombres || ' ' || d.apellidos) AS propietario_nombre FROM Paciente p JOIN Dueno d ON d.id_dueno=p.id_dueno JOIN Razas r ON r.Id_raza=p.Id_raza JOIN Especie e ON e.Id_especie=r.Id_especie LEFT JOIN usuarios u ON u.id=d.usuario_id WHERE p.id_paciente=?",(mascota_id,)).fetchone()
        return dict(row) if row else None

    def inicializar_esquema(self) -> None:
        conn = self._get_connection()
        try:
            from .sqlite_schema import migrate_sqlite_schema

            migrate_sqlite_schema(conn, self.db_path, hashear_password)
            rows = conn.execute("SELECT id, password_hash FROM usuarios").fetchall()
            for row in rows:
                password_hash = row["password_hash"] or ""
                if password_hash and not str(password_hash).startswith(_PBKDF2_PREFIX):
                    conn.execute(
                        "UPDATE usuarios SET password_hash = ? WHERE id = ?",
                        (hashear_password(str(password_hash)), row["id"]),
                    )
            conn.commit()
        finally:
            self._close_if_file(conn)

    def obtener_usuario_por_email(self, email: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.execute("SELECT * FROM usuarios WHERE lower(email) = lower(?)", (email.strip(),))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._close_if_file(conn)

    def crear_usuario(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        conn=self._get_connection()
        try:
            nombre=str(datos["nombre"]).strip(); email=str(datos["email"]).strip().lower()
            cur=conn.execute("INSERT INTO usuarios (nombre,email,password_hash,rol,estado,telefono,tipo_documento,documento) VALUES (?,?,?,?,?,?,?,?)",(nombre,email,hashear_password(str(datos["password_hash"])),datos.get("rol","cliente"),datos.get("estado","activo"),str(datos.get("telefono","")).strip(),datos.get("tipo_documento","DNI"),datos.get("documento")))
            nuevo_id=int(cur.lastrowid)
            if datos.get("rol","cliente")=="cliente": self._owner_id_for_user(conn,nuevo_id)
            conn.commit()
            return dict(conn.execute("SELECT * FROM usuarios WHERE id=?",(nuevo_id,)).fetchone())
        finally: self._close_if_file(conn)
    def actualizar_documento_usuario(self, usuario_id: int, tipo_documento: str, documento: str) -> Optional[Dict[str, Any]]:
        conn=self._get_connection()
        try:
            conn.execute("UPDATE usuarios SET tipo_documento=?,documento=? WHERE id=?",(tipo_documento,documento,usuario_id))
            conn.execute("UPDATE Dueno SET dni=?,tipo_documento=? WHERE usuario_id=?",(documento,tipo_documento,usuario_id))
            conn.commit(); return self.obtener_usuario_por_id(usuario_id)
        finally: self._close_if_file(conn)
    def cambiar_password_usuario(self, usuario_id: int, password_actual: str, password_nueva: str) -> bool:
        conn = self._get_connection()
        try:
            cur = conn.execute("SELECT password_hash FROM usuarios WHERE id = ?", (usuario_id,))
            row = cur.fetchone()
            if not row or not verificar_password(password_actual, row["password_hash"]):
                raise ValueError("La contraseña actual no es correcta.")
            conn.execute(
                "UPDATE usuarios SET password_hash = ? WHERE id = ?",
                (hashear_password(password_nueva), usuario_id),
            )
            conn.commit()
            return True
        finally:
            self._close_if_file(conn)

    def listar_compras_usuario(self, usuario_id: int) -> List[Dict[str, Any]]:
        conn=self._get_connection()
        try:
            owner_id=self._owner_id_for_user(conn,usuario_id,create=False)
            if owner_id is None:return []
            rows=conn.execute("SELECT * FROM Factura WHERE id_dueno=? AND Id_cita IS NULL ORDER BY id_factura DESC",(owner_id,)).fetchall()
            result=[]
            for row in rows:
                sale=dict(row); sale["id"]=sale["id_factura"]; sale["usuario_id"]=usuario_id; sale["creado_en"]=sale.get("fecha_emision")
                sale["detalles"]=[dict(d) for d in conn.execute("SELECT id,id_factura,producto_id,producto_nombre,cantidad,precio_unitario,subtotal FROM detalle_ventas WHERE id_factura=? ORDER BY id",(sale["id_factura"],)).fetchall()]
                result.append(sale)
            return result
        finally:self._close_if_file(conn)
    def crear_solicitud_mascota(self, usuario_id: int, mascota_id: int, tipo: str, motivo: str, datos_nuevos: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import json
        conn=self._get_connection()
        try:
            owner=self._owner_id_for_user(conn,usuario_id,create=False)
            pet=conn.execute("SELECT id_dueno,solicitud_estado FROM Paciente WHERE id_paciente=?",(mascota_id,)).fetchone()
            if not pet or int(pet["id_dueno"])!=int(owner or -1):raise LookupError("Mascota no encontrada para este usuario.")
            if pet["solicitud_estado"]=="pendiente":raise ValueError("La mascota ya tiene una solicitud pendiente.")
            conn.execute("UPDATE Paciente SET solicitud_tipo=?,solicitud_datos_nuevos=?,solicitud_motivo=?,solicitud_estado='pendiente',solicitud_creado_en=datetime('now','localtime') WHERE id_paciente=?",(tipo,json.dumps(datos_nuevos,ensure_ascii=False) if datos_nuevos else None,motivo.strip(),mascota_id))
            conn.commit(); return next(item for item in self.listar_solicitudes_mascota(usuario_id) if item["id"]==mascota_id)
        finally:self._close_if_file(conn)

    def listar_solicitudes_mascota(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        import json
        conn=self._get_connection()
        try:
            query="SELECT p.id_paciente AS id,p.id_paciente AS mascota_id,d.usuario_id,p.solicitud_tipo AS tipo,p.solicitud_datos_nuevos AS datos_nuevos,p.solicitud_motivo AS motivo,p.solicitud_estado AS estado,p.solicitud_creado_en AS creado_en,u.nombre AS propietario_nombre,u.email AS propietario_email,p.nombre AS mascota_nombre,e.Nombre AS mascota_especie,r.nombre AS mascota_raza FROM Paciente p JOIN Dueno d ON d.id_dueno=p.id_dueno LEFT JOIN usuarios u ON u.id=d.usuario_id JOIN Razas r ON r.Id_raza=p.Id_raza JOIN Especie e ON e.Id_especie=r.Id_especie WHERE p.solicitud_tipo IS NOT NULL"
            params=()
            if usuario_id is not None:query+=" AND d.usuario_id=?";params=(usuario_id,)
            query+=" ORDER BY p.solicitud_creado_en DESC,p.id_paciente DESC"
            result=[dict(r) for r in conn.execute(query,params).fetchall()]
            for item in result:
                if item.get("datos_nuevos"):
                    try:item["datos_nuevos"]=json.loads(item["datos_nuevos"])
                    except (ValueError,TypeError):pass
            return result
        finally:self._close_if_file(conn)

    def resolver_solicitud_mascota(self, solicitud_id: int, accion: str) -> Dict[str, Any]:
        import json
        from datetime import date
        conn=self._get_connection()
        try:
            row=conn.execute("SELECT * FROM Paciente WHERE id_paciente=? AND solicitud_tipo IS NOT NULL",(solicitud_id,)).fetchone()
            if not row:raise LookupError("Solicitud no encontrada.")
            if row["solicitud_estado"]!="pendiente":raise ValueError("Esta solicitud ya fue resuelta previamente.")
            action=accion.lower().strip()
            if action not in ("aprobar","rechazar"):raise ValueError("La accion debe ser 'aprobar' o 'rechazar'.")
            status="aprobada" if action=="aprobar" else "rechazada"
            if action=="aprobar" and row["solicitud_tipo"]=="eliminar":
                conn.execute("UPDATE Paciente SET estado='Eliminado' WHERE id_paciente=?",(solicitud_id,))
            elif action=="aprobar" and row["solicitud_tipo"]=="editar" and row["solicitud_datos_nuevos"]:
                new=json.loads(row["solicitud_datos_nuevos"])
                species=str(new.get("especie") or "Perro").strip(); breed=str(new.get("raza") or "Mestizo").strip()
                found=conn.execute("SELECT Id_especie FROM Especie WHERE lower(Nombre)=lower(?) LIMIT 1",(species,)).fetchone()
                if found:species_id=int(found[0])
                else:species_id=int(conn.execute("INSERT INTO Especie (Nombre,Descripcion) VALUES (?,?)",(species,"Registrada desde solicitud")).lastrowid)
                found=conn.execute("SELECT Id_raza FROM Razas WHERE Id_especie=? AND lower(nombre)=lower(?)",(species_id,breed)).fetchone()
                if found:race_id=int(found[0])
                else:race_id=int(conn.execute("INSERT INTO Razas (Id_especie,nombre,Descripcion) VALUES (?,?,?)",(species_id,breed,"Registrada desde solicitud")).lastrowid)
                age=max(0,int(new.get("edad",row["edad"] or 1)))
                conn.execute("UPDATE Paciente SET Id_raza=?,nombre=?,edad=?,fecha_nacimiento=?,peso_kg=?,historial_resumen=? WHERE id_paciente=?",(race_id,str(new.get("nombre",row["nombre"])).strip(),age,f"{max(1900,date.today().year-age):04d}-01-01",float(new.get("peso_kg",row["peso_kg"] or 5)),new.get("historial_resumen",row["historial_resumen"]),solicitud_id))
            conn.execute("UPDATE Paciente SET solicitud_estado=? WHERE id_paciente=?",(status,solicitud_id));conn.commit()
            return next(item for item in self.listar_solicitudes_mascota() if item["id"]==solicitud_id)
        finally:self._close_if_file(conn)
    def crear_doctor(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        conn=self._get_connection()
        try:
            email=str(datos.get("correo",datos.get("email",""))).strip().lower(); user=conn.execute("SELECT id FROM usuarios WHERE lower(email)=lower(?)",(email,)).fetchone()
            specialty_id=datos.get("especialidad_id")
            if not specialty_id and datos.get("especialidad"):
                specialty=conn.execute("SELECT Id_especialidad FROM Especialidad WHERE lower(Nombre)=lower(?)",(datos["especialidad"],)).fetchone()
                if specialty:specialty_id=specialty[0]
            cur=conn.execute("INSERT INTO Veterinario (usuario_id,Id_especialidad,numero_colegiatura,nombres,Apellidos,Telefono,correo,Fecha_contratacion) VALUES (?,?,?,?,?,?,?,?)",(user[0] if user else None,specialty_id or 1,datos.get("cmvp","CMVP-00000"),datos.get("nombres",datos.get("nombre","")),datos.get("apellidos",""),datos.get("telefono",""),email,datos.get("fecha_contratacion","2026-10-29")))
            conn.commit();return {"id":int(cur.lastrowid),**datos}
        finally:self._close_if_file(conn)
    def obtener_usuario_por_id(self, usuario_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._close_if_file(conn)

    def listar_usuarios(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.execute("SELECT id, nombre, email, rol, estado, telefono, creado_en FROM usuarios ORDER BY id ASC")
            return [dict(r) for r in cur.fetchall()]
        finally:
            self._close_if_file(conn)

    def actualizar_estado_usuario(self, usuario_id: int, nuevo_estado: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            conn.execute("UPDATE usuarios SET estado = ? WHERE id = ?", (nuevo_estado, usuario_id))
            conn.commit()
            cur = conn.execute("SELECT id, nombre, email, rol, estado, telefono, creado_en FROM usuarios WHERE id = ?", (usuario_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._close_if_file(conn)

    def _cita_row(self, conn: sqlite3.Connection, cita_id: int) -> Optional[Dict[str, Any]]:
        row=conn.execute("""
            SELECT c.Id_cita AS id,d.usuario_id,c.id_paciente AS mascota_id,
                   COALESCE(v.usuario_id,v.Id_veterinario) AS doctor_id,
                   COALESCE(NULLIF(c.propietario,''),u.nombre,trim(d.nombres || ' ' || d.apellidos),'') AS propietario,
                   COALESCE(NULLIF(c.telefono,''),u.telefono,d.telefono,'') AS telefono,
                   COALESCE(NULLIF(c.mascota_nombre,''),p.nombre,'') AS mascota_nombre,
                   COALESCE(NULLIF(c.servicio,''),s.Nombre,'') AS servicio,c.fecha,c.hora,c.motivo,
                   lower(c.estado) AS estado,c.whatsapp_url,
                   COALESCE(h.Diagnostico,'') AS diagnostico,COALESCE(h.Tratamiento,'') AS tratamiento
            FROM Cita c JOIN Veterinario v ON v.Id_veterinario=c.Id_veterinario
            LEFT JOIN Paciente p ON p.id_paciente=c.id_paciente LEFT JOIN Dueno d ON d.id_dueno=p.id_dueno
            LEFT JOIN usuarios u ON u.id=d.usuario_id
            LEFT JOIN Detalle_servicios ds ON ds.Id_cita=c.Id_cita
            LEFT JOIN Servicios s ON s.Id_servicios=ds.Id_servicios
            LEFT JOIN Historial_clinico h ON h.Id_historial=(SELECT MAX(h2.Id_historial) FROM Historial_clinico h2 WHERE h2.Id_cita=c.Id_cita)
            WHERE c.Id_cita=?
        """,(cita_id,)).fetchone()
        if not row:return None
        result=dict(row)
        service_alias={"Consulta general":"consulta-general","Vacunación":"vacunacion","Desparasitación":"desparasitacion","Control y seguimiento":"control"}
        result["servicio"]=service_alias.get(result["servicio"],result["servicio"])
        return result

    def listar_mascotas(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        conn=self._get_connection()
        try:
            query="SELECT p.id_paciente AS id,d.usuario_id,p.nombre,e.Nombre AS especie,r.nombre AS raza,p.edad,p.peso_kg,p.historial_resumen,p.sexo,p.fecha_nacimiento,p.estado,p.fecha_registro AS creado_en,COALESCE(u.nombre,d.nombres || ' ' || d.apellidos) AS propietario_nombre FROM Paciente p JOIN Dueno d ON d.id_dueno=p.id_dueno JOIN Razas r ON r.Id_raza=p.Id_raza JOIN Especie e ON e.Id_especie=r.Id_especie LEFT JOIN usuarios u ON u.id=d.usuario_id WHERE p.estado<>'Eliminado'"
            params=()
            if usuario_id is not None:query+=" AND d.usuario_id=?";params=(usuario_id,)
            query+=" ORDER BY p.id_paciente ASC"
            return [dict(r) for r in conn.execute(query,params).fetchall()]
        finally:self._close_if_file(conn)
    def crear_mascota(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        conn=self._get_connection()
        try:
            uid=int(datos["usuario_id"]);owner_id=self._owner_id_for_user(conn,uid)
            species=str(datos.get("especie","Perro")).strip() or "Perro";breed=str(datos.get("raza","Mestizo")).strip() or "Mestizo"
            specie=conn.execute("SELECT Id_especie FROM Especie WHERE lower(Nombre)=lower(?) LIMIT 1",(species,)).fetchone()
            species_id=int(specie[0]) if specie else int(conn.execute("INSERT INTO Especie (Nombre,Descripcion) VALUES (?,?)",(species,"Registrada desde perfil de cliente")).lastrowid)
            race=conn.execute("SELECT Id_raza FROM Razas WHERE Id_especie=? AND lower(nombre)=lower(?)",(species_id,breed)).fetchone()
            race_id=int(race[0]) if race else int(conn.execute("INSERT INTO Razas (Id_especie,nombre,Descripcion) VALUES (?,?,?)",(species_id,breed,"Registrada desde perfil de cliente")).lastrowid)
            age=max(0,int(datos.get("edad",1)));birth=str(datos.get("fecha_nacimiento") or f"{max(1900,__import__('datetime').date.today().year-age):04d}-01-01")
            cur=conn.execute("INSERT INTO Paciente (id_dueno,Id_raza,nombre,sexo,fecha_nacimiento,edad,peso_kg,historial_resumen,estado) VALUES (?,?,?,?,?,?,?,?,?)",(owner_id,race_id,str(datos["nombre"]).strip(),str(datos.get("sexo","H")).strip()[:1].upper(),birth,age,float(datos.get("peso_kg",5.0)),str(datos.get("historial_resumen","")).strip(),"Activo"))
            pet_id=int(cur.lastrowid);conn.commit();return self._mascota_row(conn,pet_id) or {"id":pet_id}
        finally:self._close_if_file(conn)
    def eliminar_mascota(self, mascota_id: int, usuario_id: Optional[int] = None) -> bool:
        conn=self._get_connection()
        try:
            if usuario_id is None:cur=conn.execute("UPDATE Paciente SET estado='Eliminado' WHERE id_paciente=? AND estado<>'Eliminado'",(mascota_id,))
            else:cur=conn.execute("UPDATE Paciente SET estado='Eliminado' WHERE id_paciente=? AND id_dueno=(SELECT id_dueno FROM Dueno WHERE usuario_id=?) AND estado<>'Eliminado'",(mascota_id,usuario_id))
            conn.commit();return cur.rowcount==1
        finally:self._close_if_file(conn)
    def obtener_disponibilidad_horarios(self, fecha: str) -> Dict[str, Any]:
        horarios=["08:30","10:00","11:30","13:00","15:30","17:00","18:30"]
        conn=self._get_connection()
        try:
            counts={str(r["hora"])[:5]:int(r["ocupados"]) for r in conn.execute("SELECT hora,COUNT(*) AS ocupados FROM Cita WHERE fecha=? AND lower(estado)<>'cancelada' GROUP BY hora",(fecha,)).fetchall()}
            return {"fecha":fecha,"capacidad_por_turno":3,"horarios":{h:{"ocupados":counts.get(h,0),"capacidad_maxima":3,"disponible":counts.get(h,0)<3} for h in horarios}}
        finally:self._close_if_file(conn)
    def crear_cita(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        conn=self._get_connection()
        try:
            fecha=str(datos["fecha"]).strip()[:10];hora=str(datos["hora"]).strip()[:5]
            occupied=conn.execute("SELECT COUNT(*) FROM Cita WHERE fecha=? AND substr(hora,1,5)=? AND lower(estado)<>'cancelada'",(fecha,hora)).fetchone()[0]
            if occupied>=3:raise ValueError(f"El horario {hora} del {fecha} ya cuenta con sus 3 cupos médicos ocupados. Elige otro horario.")
            vet_id=None;doctor=datos.get("doctor_id")
            if doctor is not None:
                found=conn.execute("SELECT Id_veterinario FROM Veterinario WHERE usuario_id=?",(doctor,)).fetchone()
                if not found:found=conn.execute("SELECT Id_veterinario FROM Veterinario WHERE Id_veterinario=?",(doctor,)).fetchone()
                if found:vet_id=int(found[0])
            if vet_id is None:
                found=conn.execute("SELECT Id_veterinario FROM Veterinario ORDER BY Id_veterinario LIMIT 1").fetchone()
                if not found:raise ValueError("No hay veterinarios registrados para asignar la cita.")
                vet_id=int(found[0])
            pet_id=datos.get("mascota_id")
            if pet_id is not None:
                pet=conn.execute("SELECT p.id_paciente,d.usuario_id FROM Paciente p JOIN Dueno d ON d.id_dueno=p.id_dueno WHERE p.id_paciente=?",(int(pet_id),)).fetchone()
                if not pet:pet_id=None
                elif datos.get("usuario_id") is not None and int(pet["usuario_id"] or -1)!=int(datos["usuario_id"]):raise ValueError("La mascota no pertenece al usuario de la cita.")
            service_key=str(datos.get("servicio","")).strip();aliases={"consulta-general":"Consulta general","vacunacion":"Vacunación","desparasitacion":"Desparasitación","control":"Control y seguimiento"}
            service_name=aliases.get(service_key,service_key);service=conn.execute("SELECT Id_servicios,Precio FROM Servicios WHERE lower(Nombre)=lower(?) LIMIT 1",(service_name,)).fetchone()
            if not service:service=conn.execute("SELECT Id_servicios,Precio FROM Servicios ORDER BY Id_servicios LIMIT 1").fetchone()
            cur=conn.execute("INSERT INTO Cita (Id_veterinario,id_paciente,fecha,hora,motivo,estado,propietario,telefono,mascota_nombre,servicio,whatsapp_url) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(vet_id,pet_id,fecha,hora,str(datos.get("motivo","")).strip(),str(datos.get("estado","pendiente")).lower(),str(datos.get("propietario","")).strip(),str(datos.get("telefono","")).strip(),str(datos.get("mascota_nombre","")).strip(),service_key,str(datos.get("whatsapp_url","")).strip()))
            cita_id=int(cur.lastrowid)
            if service:conn.execute("INSERT INTO Detalle_servicios (Id_cita,Id_servicios,precio_aplicado) VALUES (?,?,?)",(cita_id,int(service[0]),float(service[1])))
            if datos.get("diagnostico") or datos.get("tratamiento"):conn.execute("INSERT INTO Historial_clinico (Id_cita,Diagnostico,Tratamiento) VALUES (?,?,?)",(cita_id,datos.get("diagnostico","") or "",datos.get("tratamiento","") or ""))
            conn.commit();return self._cita_row(conn,cita_id) or {"id":cita_id}
        finally:self._close_if_file(conn)
    def listar_citas(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        conn=self._get_connection()
        try:
            if usuario_id is None:ids=[r[0] for r in conn.execute("SELECT Id_cita FROM Cita ORDER BY fecha,hora,Id_cita").fetchall()]
            else:ids=[r[0] for r in conn.execute("SELECT c.Id_cita FROM Cita c LEFT JOIN Paciente p ON p.id_paciente=c.id_paciente LEFT JOIN Dueno d ON d.id_dueno=p.id_dueno WHERE d.usuario_id=? ORDER BY c.fecha,c.hora,c.Id_cita",(usuario_id,)).fetchall()]
            return [result for cid in ids if (result:=self._cita_row(conn,int(cid))) is not None]
        finally:self._close_if_file(conn)
    def actualizar_cita_doctor(self, cita_id: int, estado: str, diagnostico: str, tratamiento: str, doctor_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        conn=self._get_connection()
        try:
            if doctor_id is None:cur=conn.execute("UPDATE Cita SET estado=? WHERE Id_cita=?",(estado,cita_id))
            else:
                vet=conn.execute("SELECT Id_veterinario FROM Veterinario WHERE usuario_id=?",(doctor_id,)).fetchone()
                if not vet:vet=conn.execute("SELECT Id_veterinario FROM Veterinario WHERE Id_veterinario=?",(doctor_id,)).fetchone()
                cur=conn.execute("UPDATE Cita SET estado=?,Id_veterinario=COALESCE(?,Id_veterinario) WHERE Id_cita=?",(estado,int(vet[0]) if vet else None,cita_id))
            if cur.rowcount==0:return None
            hist=conn.execute("SELECT Id_historial FROM Historial_clinico WHERE Id_cita=? ORDER BY Id_historial DESC LIMIT 1",(cita_id,)).fetchone()
            if hist:conn.execute("UPDATE Historial_clinico SET Diagnostico=?,Tratamiento=? WHERE Id_historial=?",(diagnostico,tratamiento,hist[0]))
            elif diagnostico or tratamiento:conn.execute("INSERT INTO Historial_clinico (Id_cita,Diagnostico,Tratamiento) VALUES (?,?,?)",(cita_id,diagnostico,tratamiento))
            conn.commit();return self._cita_row(conn,cita_id)
        finally:self._close_if_file(conn)
    def listar_productos(self, solo_activos: bool = True) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.execute("SELECT * FROM productos WHERE activo = 1 ORDER BY id ASC" if solo_activos else "SELECT * FROM productos ORDER BY id ASC")
            return [dict(r) for r in cur.fetchall()]
        finally:
            self._close_if_file(conn)

    def obtener_producto(self, producto_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM productos WHERE id = ?", (producto_id,)).fetchone()
            return dict(row) if row else None
        finally:
            self._close_if_file(conn)

    def descontar_stock_producto(self, producto_id: int, cantidad: int) -> bool:
        conn = self._get_connection()
        try:
            cur = conn.execute("UPDATE productos SET stock = stock - ? WHERE id = ? AND stock >= ?", (cantidad, producto_id, cantidad))
            conn.commit()
            return cur.rowcount == 1
        finally:
            self._close_if_file(conn)

    def registrar_venta_y_detalles(self, cabecera: Dict[str, Any], detalles: List[Dict[str, Any]]) -> Dict[str, Any]:
        conn=self._get_connection()
        try:
            uid=int(cabecera["usuario_id"]);owner_id=self._owner_id_for_user(conn,uid)
            number_text=str(cabecera["numero_boleta"]);series,_,suffix=number_text.partition("-");series=series or "B001";number=int(suffix or "1")
            exists=conn.execute("SELECT 1 FROM Factura WHERE serie=? AND numero=?",(series,number)).fetchone()
            if exists:raise ValueError(f"El numero de boleta {number_text} ya existe.")
            cur=conn.execute("INSERT INTO Factura (id_dueno,tipo,serie,numero,numero_boleta,cliente_nombre,cliente_documento,subtotal,igv,total,metodo_pago,estado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(owner_id,"Boleta",series,number,number_text,cabecera["cliente_nombre"],cabecera["cliente_documento"],cabecera["subtotal"],cabecera["igv"],cabecera["total"],cabecera.get("metodo_pago","Tarjeta / Yape"),str(cabecera.get("estado","pagado")).capitalize()))
            invoice_id=int(cur.lastrowid)
            for detail in detalles:
                conn.execute("INSERT INTO detalle_ventas (id_factura,producto_id,producto_nombre,cantidad,precio_unitario,subtotal) VALUES (?,?,?,?,?,?)",(invoice_id,detail["producto_id"],detail["producto_nombre"],detail["cantidad"],detail["precio_unitario"],detail["subtotal"]))
            conn.execute("INSERT INTO Pago (id_factura,metodo_pago,monto,estado) VALUES (?,?,?,?)",(invoice_id,cabecera.get("metodo_pago","Tarjeta / Yape"),cabecera["total"],str(cabecera.get("estado","pagado")).capitalize()))
            conn.commit();return self._factura_row(conn,invoice_id) or {"id":invoice_id}
        finally:self._close_if_file(conn)

    def _factura_row(self, conn: sqlite3.Connection, invoice_id: int) -> Optional[Dict[str, Any]]:
        row=conn.execute("SELECT f.*,f.id_factura AS id,d.usuario_id,f.fecha_emision AS creado_en FROM Factura f LEFT JOIN Dueno d ON d.id_dueno=f.id_dueno WHERE f.id_factura=?",(invoice_id,)).fetchone()
        if not row:return None
        result=dict(row);result["detalles"]=[dict(d) for d in conn.execute("SELECT * FROM detalle_ventas WHERE id_factura=? ORDER BY id",(invoice_id,)).fetchall()]
        return result
    def listar_ventas(self) -> List[Dict[str, Any]]:
        conn=self._get_connection()
        try:
            ids=[r[0] for r in conn.execute("SELECT id_factura FROM Factura ORDER BY id_factura DESC").fetchall()]
            return [sale for invoice_id in ids if (sale:=self._factura_row(conn,int(invoice_id))) is not None]
        finally:self._close_if_file(conn)
    def obtener_todas_las_16_tablas(self) -> Dict[str, List[Dict[str, Any]]]:
        conn = self._get_connection()
        try:
            resultado: Dict[str, List[Dict[str, Any]]] = {}
            for tabla in self.NOMBRES_16_TABLAS:
                try:
                    filas = conn.execute(f"SELECT * FROM {tabla}").fetchall()
                    resultado[tabla] = [dict(f) for f in filas]
                except Exception:
                    resultado[tabla] = []
            return resultado
        finally:
            self._close_if_file(conn)


# =============================================================================
# 4. COMPATIBILIDAD CON ADAPTADOR EXTERNO - MODELO UNIFICADO 16 TABLAS
# =============================================================================

class SupabasePostgresAdapter(SQLiteDatabaseAdapter):
    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        db_path: Optional[str] = None,
    ) -> None:
        self.supabase_url = (supabase_url or str()).strip()
        self.supabase_key = (supabase_key or str()).strip()
        super().__init__(db_path=db_path)


# =============================================================================
# 5. FABRICA DE ADAPTADORES - FACTORY METHOD
# =============================================================================

def obtener_adaptador_bd() -> IDatabaseAdapter:
    db_path = os.getenv('SQLITE_PATH')
    if db_path:
        base_dir = Path(__file__).resolve().parent.parent.parent
        full_path = base_dir / db_path if not Path(db_path).is_absolute() else Path(db_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return SQLiteDatabaseAdapter(str(full_path))
    return SQLiteDatabaseAdapter()
