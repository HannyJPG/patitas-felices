"""
PATRÓN ADAPTER (Estructural - GoF)
Implementa el desacoplamiento de BD (SQL Server, SQLite y Supabase PostgreSQL) y WhatsApp.
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
import sqlite3
from typing import Any, Dict, List, Optional
from urllib.parse import quote
_env_file = Path(__file__).resolve().parent.parent.parent / '.env'
if _env_file.is_file():
    for _line in _env_file.read_text(encoding='utf-8').splitlines():
        _line = _line.strip()
        if _line and (not _line.startswith('#')) and ('=' in _line):
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())
# =============================================================================
# 0. UTILIDADES CRIPTOGRÁFICAS DE CONTRASEÑAS (PBKDF2-HMAC-SHA256)
# =============================================================================
_PBKDF2_PREFIX = 'pbkdf2_sha256$'
_PBKDF2_ITERATIONS = 100000

def hashear_password(password_plano: str) -> str:
    """Genera un hash criptográfico PBKDF2-HMAC-SHA256 con sal aleatoria de 128 bits."""
    if not password_plano or str(password_plano).startswith(_PBKDF2_PREFIX):
        return str(password_plano)
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', str(password_plano).encode('utf-8'), salt.encode('utf-8'), _PBKDF2_ITERATIONS).hex()
    return f'{_PBKDF2_PREFIX}{salt}${dk}'

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
        partes = hash_str.split('$', 2)
        if len(partes) != 3:
            return False
        _, salt, digest_esperado = partes
        dk = hashlib.pbkdf2_hmac('sha256', plano_str.encode('utf-8'), salt.encode('utf-8'), _PBKDF2_ITERATIONS).hex()
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
    SERVICIOS_NOMBRES = {'consulta-general': 'Consulta general', 'vacunacion': 'Vacunación', 'desparasitacion': 'Desparasitación', 'control': 'Control y seguimiento'}
    SERVICIOS_CODIGOS = {nombre: codigo for codigo, nombre in SERVICIOS_NOMBRES.items()}

    def __init__(self, numero_clinica: Optional[str]=None) -> None:
        self.numero_clinica = numero_clinica or os.getenv('CLINICA_WHATSAPP', '51990853697')

    def _construir_url(self, mensaje: str) -> str:
        texto_codificado = quote(mensaje, safe='')
        return f'https://wa.me/{self.numero_clinica}?text={texto_codificado}'

    def generar_enlace_cita(self, datos_cita: Dict[str, Any]) -> str:
        fecha_raw = str(datos_cita.get('fecha', ''))
        partes = fecha_raw.split('-')
        fecha_formateada = f'{partes[2]}/{partes[1]}/{partes[0]}' if len(partes) == 3 else fecha_raw
        servicio_clave = datos_cita.get('servicio', '')
        servicio_legible = self.SERVICIOS_NOMBRES.get(servicio_clave, servicio_clave)
        lineas = ['Hola, Patitas Felices. Quisiera solicitar una cita veterinaria.', '', f"Propietario: {datos_cita.get('propietario', '')}", f"Teléfono de contacto: {datos_cita.get('telefono', '')}", f"Mascota: {datos_cita.get('mascota_nombre') or datos_cita.get('mascota', '')}", f'Servicio: {servicio_legible}', f'Fecha deseada: {fecha_formateada}', f"Hora deseada: {datos_cita.get('hora', '')} (Lima, Perú)", 'Duración: 30 minutos', f"Motivo: {datos_cita.get('motivo', '')}", '', '¿Podrían confirmar si este horario está disponible?']
        return self._construir_url('\n'.join(lineas))

    def generar_enlace_boleta(self, numero_boleta: str, cliente: str, total: float) -> str:
        mensaje = f'Hola, Patitas Felices. Soy {cliente}. Acabo de realizar la compra con Boleta N° {numero_boleta} por un total de S/ {total:.2f}. Solicito coordinación de entrega.'
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
    def crear_solicitud_mascota(self, usuario_id: int, mascota_id: int, tipo: str, motivo: str, datos_nuevos: Optional[Dict[str, Any]]=None) -> Dict[str, Any]:
        pass

    @abstractmethod
    def listar_solicitudes_mascota(self, usuario_id: Optional[int]=None) -> List[Dict[str, Any]]:
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
    def listar_mascotas(self, usuario_id: Optional[int]=None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def crear_mascota(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def eliminar_mascota(self, mascota_id: int, usuario_id: Optional[int]=None) -> bool:
        pass

    @abstractmethod
    def crear_cita(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def listar_citas(self, usuario_id: Optional[int]=None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def actualizar_cita_doctor(self, cita_id: int, estado: str, diagnostico: str, tratamiento: str, doctor_id: Optional[int]=None) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def listar_productos(self, solo_activos: bool=True) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def obtener_producto(self, producto_id: int) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def descontar_stock_producto(self, producto_id: int, cantidad: int) -> bool:
        pass

    @abstractmethod
    def registrar_venta_y_detalles(self, cabecera: Dict[str, Any], detalles: List[Dict[str, Any]]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def listar_ventas(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def obtener_todas_las_16_tablas(self) -> Dict[str, List[Dict[str, Any]]]:
        pass

# =============================================================================
# 3. ADAPTER DE BASE DE DATOS NORMALIZADA EN 3FN (16 TABLAS SIN REDUNDANCIAS)
# =============================================================================
class SQLiteDatabaseAdapter(IDatabaseAdapter):
    """Adapter concreto autoinicializable con sincronización automática a SQL Server."""
    NOMBRES_16_TABLAS = ['Dueno', 'Especie', 'Razas', 'Paciente', 'Especialidad', 'Veterinario', 'Servicios', 'Cita', 'Detalle_servicios', 'Historial_clinico', 'Receta', 'Factura', 'Pago', 'usuarios', 'productos', 'detalle_ventas']

    def __init__(self, db_path: Optional[str]=None) -> None:
        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            default_file = base_dir / 'database' / 'patitas_felices.db'
            default_file.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(default_file)
        else:
            self.db_path = db_path
        self._persistent_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ':memory:':
            self._persistent_conn = sqlite3.connect(':memory:', check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self.inicializar_esquema()

    def _get_connection(self) -> sqlite3.Connection:
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        return conn

    def _close_if_file(self, conn: sqlite3.Connection) -> None:
        if self._persistent_conn is None:
            conn.close()

    def _commit_and_sync(self, conn: sqlite3.Connection) -> None:
        conn.commit()
        if self.db_path != ':memory:':
            from .sqlite_schema import push_to_sqlserver
            push_to_sqlserver(conn, self.db_path, server=getattr(self, 'server', None), database=getattr(self, 'database', None))

    def _owner_id_for_user(self, conn: sqlite3.Connection, usuario_id: int, create: bool=True) -> Optional[int]:
        row = conn.execute('SELECT id_dueno FROM Dueno WHERE usuario_id = ?', (usuario_id,)).fetchone()
        if row:
            return int(row[0])
        user = conn.execute('SELECT id, nombre, telefono FROM usuarios WHERE id = ?', (usuario_id,)).fetchone()
        if not user or not create:
            return None
        parts = str(user['nombre'] or 'Cliente').strip().split(' ', 1)
        doc = f'CLI{usuario_id:05d}'
        cur = conn.execute("INSERT INTO Dueno (usuario_id, dni, tipo_documento, nombres, apellidos, telefono) VALUES (?, ?, 'DNI', ?, ?, ?)", (usuario_id, doc, parts[0], parts[1] if len(parts) > 1 else '', user['telefono'] or ''))
        return int(cur.lastrowid)

    def _resolve_raza_id(self, conn: sqlite3.Connection, especie: str, raza: str, descripcion: str) -> int:
        species = (especie or 'Perro').strip() or 'Perro'
        breed = (raza or 'Mestizo').strip() or 'Mestizo'
        sp = conn.execute('SELECT Id_especie FROM Especie WHERE lower(Nombre) = lower(?) LIMIT 1', (species,)).fetchone()
        species_id = int(sp[0]) if sp else int(conn.execute('INSERT INTO Especie (Nombre, Descripcion) VALUES (?, ?)', (species, descripcion)).lastrowid)
        rz = conn.execute('SELECT Id_raza FROM Razas WHERE Id_especie = ? AND lower(nombre) = lower(?)', (species_id, breed)).fetchone()
        return int(rz[0]) if rz else int(conn.execute('INSERT INTO Razas (Id_especie, nombre, Descripcion) VALUES (?, ?, ?)', (species_id, breed, descripcion)).lastrowid)

    def _user_row(self, conn: sqlite3.Connection, where_sql: str, params: tuple[Any, ...]) -> Optional[Dict[str, Any]]:
        row = conn.execute(f"\n            SELECT u.id, u.nombre, u.email, u.password_hash, u.rol, u.estado, u.telefono, u.creado_en,\n                   COALESCE(d.tipo_documento, 'DNI') AS tipo_documento,\n                   CASE WHEN d.dni LIKE 'CLI%' OR d.dni LIKE 'EXT%' THEN NULL ELSE d.dni END AS documento\n            FROM usuarios u\n            LEFT JOIN Dueno d ON d.usuario_id = u.id\n            WHERE {where_sql}\n            ", params).fetchone()
        return dict(row) if row else None

    def _mascota_row(self, conn: sqlite3.Connection, mascota_id: int) -> Optional[Dict[str, Any]]:
        row = conn.execute("\n            SELECT p.id_paciente AS id, d.usuario_id, p.nombre, e.Nombre AS especie, r.nombre AS raza,\n                   MAX(0, CAST(strftime('%Y', 'now', 'localtime') AS INTEGER) - CAST(substr(p.fecha_nacimiento, 1, 4) AS INTEGER)) AS edad,\n                   p.peso_kg, p.historial_resumen, p.sexo, p.fecha_nacimiento, p.estado, p.fecha_registro AS creado_en,\n                   COALESCE(u.nombre, trim(d.nombres || ' ' || d.apellidos)) AS propietario_nombre\n            FROM Paciente p\n            JOIN Dueno d ON d.id_dueno = p.id_dueno\n            JOIN Razas r ON r.Id_raza = p.Id_raza\n            JOIN Especie e ON e.Id_especie = r.Id_especie\n            LEFT JOIN usuarios u ON u.id = d.usuario_id\n            WHERE p.id_paciente = ?\n            ", (mascota_id,)).fetchone()
        return dict(row) if row else None

    def inicializar_esquema(self) -> None:
        conn = self._get_connection()
        try:
            from .sqlite_schema import migrate_sqlite_schema
            migrate_sqlite_schema(conn, self.db_path, hashear_password, server=getattr(self, 'server', None), database=getattr(self, 'database', None))
            rows = conn.execute('SELECT id, password_hash FROM usuarios').fetchall()
            updated = False
            for row in rows:
                password_hash = row['password_hash'] or ''
                if password_hash and (not str(password_hash).startswith(_PBKDF2_PREFIX)):
                    conn.execute('UPDATE usuarios SET password_hash = ? WHERE id = ?', (hashear_password(str(password_hash)), row['id']))
                    updated = True
            if updated:
                self._commit_and_sync(conn)
            else:
                conn.commit()
        finally:
            self._close_if_file(conn)

    def obtener_usuario_por_email(self, email: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            return self._user_row(conn, 'lower(u.email) = lower(?)', (email.strip(),))
        finally:
            self._close_if_file(conn)

    def crear_usuario(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            nombre = str(datos['nombre']).strip()
            email = str(datos['email']).strip().lower()
            rol = str(datos.get('rol', 'cliente')).strip()
            estado = str(datos.get('estado', 'activo')).strip()
            telefono = str(datos.get('telefono', '')).strip()
            doc_nuevo = str(datos.get('documento') or '').strip()
            if doc_nuevo:
                dup = conn.execute('SELECT 1 FROM Dueno WHERE dni = ? LIMIT 1', (doc_nuevo,)).fetchone()
                if dup:
                    raise ValueError('El documento de identidad ingresado ya está registrado en otra cuenta.')
            cur = conn.execute('INSERT INTO usuarios (nombre, email, password_hash, rol, estado, telefono) VALUES (?, ?, ?, ?, ?, ?)', (nombre, email, hashear_password(str(datos['password_hash'])), rol, estado, telefono))
            nuevo_id = int(cur.lastrowid)
            if rol == 'cliente' or doc_nuevo:
                self._owner_id_for_user(conn, nuevo_id)
                if doc_nuevo:
                    conn.execute('UPDATE Dueno SET dni = ?, tipo_documento = ? WHERE usuario_id = ?', (doc_nuevo, str(datos.get('tipo_documento') or 'DNI').strip(), nuevo_id))
            self._commit_and_sync(conn)
            return self._user_row(conn, 'u.id = ?', (nuevo_id,)) or {'id': nuevo_id, 'nombre': nombre, 'email': email, 'rol': rol, 'estado': estado}
        finally:
            self._close_if_file(conn)

    def actualizar_documento_usuario(self, usuario_id: int, tipo_documento: str, documento: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            doc_limpio = documento.strip()
            dup = conn.execute('SELECT 1 FROM Dueno WHERE dni = ? AND (usuario_id IS NULL OR usuario_id <> ?) LIMIT 1', (doc_limpio, usuario_id)).fetchone()
            if dup:
                raise ValueError('El documento de identidad ingresado ya está registrado en otra cuenta.')
            self._owner_id_for_user(conn, usuario_id, create=True)
            conn.execute('UPDATE Dueno SET dni = ?, tipo_documento = ? WHERE usuario_id = ?', (doc_limpio, tipo_documento.strip(), usuario_id))
            self._commit_and_sync(conn)
            return self._user_row(conn, 'u.id = ?', (usuario_id,))
        finally:
            self._close_if_file(conn)

    def cambiar_password_usuario(self, usuario_id: int, password_actual: str, password_nueva: str) -> bool:
        conn = self._get_connection()
        try:
            row = conn.execute('SELECT password_hash FROM usuarios WHERE id = ?', (usuario_id,)).fetchone()
            if not row or not verificar_password(password_actual, row['password_hash']):
                raise ValueError('La contraseña actual no es correcta.')
            conn.execute('UPDATE usuarios SET password_hash = ? WHERE id = ?', (hashear_password(password_nueva), usuario_id))
            self._commit_and_sync(conn)
            return True
        finally:
            self._close_if_file(conn)

    def listar_compras_usuario(self, usuario_id: int) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            owner_id = self._owner_id_for_user(conn, usuario_id, create=False)
            if owner_id is None:
                return []
            return self._query_facturas(conn, 'WHERE f.id_dueno = ? AND f.Id_cita IS NULL ORDER BY f.id_factura DESC', (owner_id,))
        finally:
            self._close_if_file(conn)

    def crear_solicitud_mascota(self, usuario_id: int, mascota_id: int, tipo: str, motivo: str, datos_nuevos: Optional[Dict[str, Any]]=None) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            owner = self._owner_id_for_user(conn, usuario_id, create=False)
            pet = conn.execute('SELECT id_dueno, solicitud_estado FROM Paciente WHERE id_paciente = ?', (mascota_id,)).fetchone()
            if not pet or int(pet['id_dueno']) != int(owner or -1):
                raise LookupError('Mascota no encontrada para este usuario.')
            if pet['solicitud_estado'] == 'pendiente':
                raise ValueError('La mascota ya tiene una solicitud pendiente.')
            conn.execute("UPDATE Paciente SET solicitud_tipo = ?, solicitud_datos_nuevos = ?, solicitud_motivo = ?, solicitud_estado = 'pendiente', solicitud_creado_en = datetime('now', 'localtime') WHERE id_paciente = ?", (tipo, json.dumps(datos_nuevos, ensure_ascii=False) if datos_nuevos else None, motivo.strip(), mascota_id))
            self._commit_and_sync(conn)
            return next((item for item in self.listar_solicitudes_mascota(usuario_id) if item['id'] == mascota_id))
        finally:
            self._close_if_file(conn)

    def listar_solicitudes_mascota(self, usuario_id: Optional[int]=None) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            query = "\n                SELECT p.id_paciente AS id, p.id_paciente AS mascota_id, d.usuario_id,\n                       p.solicitud_tipo AS tipo, p.solicitud_datos_nuevos AS datos_nuevos,\n                       p.solicitud_motivo AS motivo, p.solicitud_estado AS estado, p.solicitud_creado_en AS creado_en,\n                       COALESCE(u.nombre, trim(d.nombres || ' ' || d.apellidos)) AS propietario_nombre,\n                       COALESCE(u.email, '') AS propietario_email,\n                       p.nombre AS mascota_nombre, e.Nombre AS mascota_especie, r.nombre AS mascota_raza\n                FROM Paciente p\n                JOIN Dueno d ON d.id_dueno = p.id_dueno\n                LEFT JOIN usuarios u ON u.id = d.usuario_id\n                JOIN Razas r ON r.Id_raza = p.Id_raza\n                JOIN Especie e ON e.Id_especie = r.Id_especie\n                WHERE p.solicitud_tipo IS NOT NULL\n            "
            params: tuple[Any, ...] = ()
            if usuario_id is not None:
                query += ' AND d.usuario_id = ?'
                params = (usuario_id,)
            query += ' ORDER BY p.solicitud_creado_en DESC, p.id_paciente DESC'
            result = [dict(r) for r in conn.execute(query, params).fetchall()]
            for item in result:
                if item.get('datos_nuevos'):
                    try:
                        item['datos_nuevos'] = json.loads(item['datos_nuevos'])
                    except (ValueError, TypeError):
                        pass
            return result
        finally:
            self._close_if_file(conn)

    def resolver_solicitud_mascota(self, solicitud_id: int, accion: str) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            row = conn.execute('SELECT * FROM Paciente WHERE id_paciente = ? AND solicitud_tipo IS NOT NULL', (solicitud_id,)).fetchone()
            if not row:
                raise LookupError('Solicitud no encontrada.')
            if row['solicitud_estado'] != 'pendiente':
                raise ValueError('Esta solicitud ya fue resuelta previamente.')
            action = accion.lower().strip()
            if action not in ('aprobar', 'rechazar'):
                raise ValueError("La accion debe ser 'aprobar' o 'rechazar'.")
            status = 'aprobada' if action == 'aprobar' else 'rechazada'
            if action == 'aprobar' and row['solicitud_tipo'] == 'eliminar':
                conn.execute("UPDATE Paciente SET estado = 'Eliminado' WHERE id_paciente = ?", (solicitud_id,))
            elif action == 'aprobar' and row['solicitud_tipo'] == 'editar' and row['solicitud_datos_nuevos']:
                new = json.loads(row['solicitud_datos_nuevos'])
                if new.get('especie') or new.get('raza'):
                    cur_rz = conn.execute('SELECT e.Nombre AS especie, r.nombre AS raza FROM Razas r JOIN Especie e ON e.Id_especie = r.Id_especie WHERE r.Id_raza = ?', (row['Id_raza'],)).fetchone()
                    sp_default = cur_rz['especie'] if cur_rz else 'Perro'
                    rz_default = cur_rz['raza'] if cur_rz else 'Mestizo'
                    race_id = self._resolve_raza_id(conn, str(new.get('especie') or sp_default), str(new.get('raza') or rz_default), 'Registrada desde solicitud')
                else:
                    race_id = int(row['Id_raza'])
                birth_str = str(row['fecha_nacimiento'] or '2023-05-10')
                current_age = max(0, date.today().year - int(birth_str[:4])) if birth_str[:4].isdigit() else 1
                raw_age = new.get('edad')
                age = max(0, int(raw_age if raw_age is not None else current_age))
                new_birth = f'{max(1900, date.today().year - age):04d}-01-01' if raw_age is not None else birth_str
                raw_peso = new.get('peso_kg')
                peso_final = float(raw_peso if raw_peso is not None else row['peso_kg'] or 5.0)
                conn.execute('UPDATE Paciente SET Id_raza = ?, nombre = ?, fecha_nacimiento = ?, peso_kg = ?, historial_resumen = ? WHERE id_paciente = ?', (race_id, str(new.get('nombre') or row['nombre']).strip(), new_birth, peso_final, new.get('historial_resumen') if new.get('historial_resumen') is not None else row['historial_resumen'], solicitud_id))
            conn.execute('UPDATE Paciente SET solicitud_estado = ? WHERE id_paciente = ?', (status, solicitud_id))
            self._commit_and_sync(conn)
            return next((item for item in self.listar_solicitudes_mascota() if item['id'] == solicitud_id))
        finally:
            self._close_if_file(conn)

    def existe_colegiatura_veterinario(self, cmvp: str) -> bool:
        codigo = str(cmvp or '').strip()
        if not codigo:
            return False
        conn = self._get_connection()
        try:
            row = conn.execute('SELECT 1 FROM Veterinario WHERE lower(numero_colegiatura) = lower(?) LIMIT 1', (codigo,)).fetchone()
            return row is not None
        finally:
            self._close_if_file(conn)

    def crear_doctor(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            cmvp = str(datos.get('cmvp') or '').strip()
            if not cmvp:
                raise ValueError('El número de colegiatura CMVP es obligatorio para registrar un médico veterinario.')
            dup = conn.execute('SELECT 1 FROM Veterinario WHERE lower(numero_colegiatura) = lower(?) LIMIT 1', (cmvp,)).fetchone()
            if dup:
                raise ValueError(f"El número de colegiatura '{cmvp}' ya está registrado para otro profesional veterinario.")
            email = str(datos.get('correo', datos.get('email', ''))).strip().lower()
            user = conn.execute('SELECT id FROM usuarios WHERE lower(email) = lower(?)', (email,)).fetchone()
            specialty_id = datos.get('especialidad_id')
            if not specialty_id and datos.get('especialidad'):
                specialty = conn.execute('SELECT Id_especialidad FROM Especialidad WHERE lower(Nombre) = lower(?)', (datos['especialidad'],)).fetchone()
                specialty_id = int(specialty[0]) if specialty else int(conn.execute('INSERT INTO Especialidad (Nombre, Descripcion) VALUES (?, ?)', (str(datos['especialidad']).strip(), 'Especialidad registrada desde panel administrativo')).lastrowid)
            nombre_completo = str(datos.get('nombres') or datos.get('nombre') or 'Doctor').strip()
            apellidos = str(datos.get('apellidos') or '').strip()
            if not apellidos and ' ' in nombre_completo:
                nombre_completo, apellidos = nombre_completo.split(' ', 1)
            cur = conn.execute('INSERT INTO Veterinario (usuario_id, Id_especialidad, numero_colegiatura, nombres, Apellidos, Telefono, Fecha_contratacion) VALUES (?, ?, ?, ?, ?, ?, ?)', (datos.get('usuario_id') or (user[0] if user else None), specialty_id or 1, cmvp, nombre_completo, apellidos, str(datos.get('telefono', '')).strip(), datos.get('fecha_contratacion', date.today().isoformat())))
            self._commit_and_sync(conn)
            return {'id': int(cur.lastrowid), **datos}
        finally:
            self._close_if_file(conn)

    def obtener_usuario_por_id(self, usuario_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            return self._user_row(conn, 'u.id = ?', (usuario_id,))
        finally:
            self._close_if_file(conn)

    def listar_usuarios(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.execute("\n                SELECT u.id, u.nombre, u.email, u.rol, u.estado, u.telefono, u.creado_en,\n                       COALESCE(d.tipo_documento, 'DNI') AS tipo_documento,\n                       CASE WHEN d.dni LIKE 'CLI%' OR d.dni LIKE 'EXT%' THEN NULL ELSE d.dni END AS documento\n                FROM usuarios u\n                LEFT JOIN Dueno d ON d.usuario_id = u.id\n                ORDER BY u.id ASC\n                ")
            return [dict(r) for r in cur.fetchall()]
        finally:
            self._close_if_file(conn)

    def actualizar_estado_usuario(self, usuario_id: int, nuevo_estado: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            conn.execute('UPDATE usuarios SET estado = ? WHERE id = ?', (nuevo_estado, usuario_id))
            self._commit_and_sync(conn)
            return self._user_row(conn, 'u.id = ?', (usuario_id,))
        finally:
            self._close_if_file(conn)

    def _query_citas(self, conn: sqlite3.Connection, where_order_sql: str, params: tuple[Any, ...]=()) -> List[Dict[str, Any]]:
        rows = conn.execute(f"\n            SELECT c.Id_cita AS id, d.usuario_id, c.id_paciente AS mascota_id,\n                   COALESCE(v.usuario_id, v.Id_veterinario) AS doctor_id,\n                   COALESCE(u.nombre, trim(d.nombres || ' ' || d.apellidos), '') AS propietario,\n                   COALESCE(NULLIF(d.telefono, ''), u.telefono, '') AS telefono,\n                   COALESCE(p.nombre, '') AS mascota_nombre,\n                   COALESCE(s.Nombre, '') AS servicio,\n                   c.fecha, c.hora, c.motivo, lower(c.estado) AS estado, c.whatsapp_url,\n                   COALESCE(h.Diagnostico, '') AS diagnostico, COALESCE(h.Tratamiento, '') AS tratamiento\n            FROM Cita c\n            JOIN Veterinario v ON v.Id_veterinario = c.Id_veterinario\n            LEFT JOIN Paciente p ON p.id_paciente = c.id_paciente\n            LEFT JOIN Dueno d ON d.id_dueno = p.id_dueno\n            LEFT JOIN usuarios u ON u.id = d.usuario_id\n            LEFT JOIN Detalle_servicios ds ON ds.Id_cita = c.Id_cita\n            LEFT JOIN Servicios s ON s.Id_servicios = ds.Id_servicios\n            LEFT JOIN Historial_clinico h ON h.Id_historial = (\n                SELECT MAX(h2.Id_historial) FROM Historial_clinico h2 WHERE h2.Id_cita = c.Id_cita\n            )\n            {where_order_sql}\n            ", params).fetchall()
        results: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item['servicio'] = WhatsAppAdapter.SERVICIOS_CODIGOS.get(item['servicio'], item['servicio'])
            results.append(item)
        return results

    def _cita_row(self, conn: sqlite3.Connection, cita_id: int) -> Optional[Dict[str, Any]]:
        items = self._query_citas(conn, 'WHERE c.Id_cita = ?', (cita_id,))
        return items[0] if items else None

    def listar_mascotas(self, usuario_id: Optional[int]=None) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            query = "\n                SELECT p.id_paciente AS id, d.usuario_id, p.nombre, e.Nombre AS especie, r.nombre AS raza,\n                       MAX(0, CAST(strftime('%Y', 'now', 'localtime') AS INTEGER) - CAST(substr(p.fecha_nacimiento, 1, 4) AS INTEGER)) AS edad,\n                       p.peso_kg, p.historial_resumen, p.sexo, p.fecha_nacimiento, p.estado, p.fecha_registro AS creado_en,\n                       COALESCE(u.nombre, trim(d.nombres || ' ' || d.apellidos)) AS propietario_nombre\n                FROM Paciente p\n                JOIN Dueno d ON d.id_dueno = p.id_dueno\n                JOIN Razas r ON r.Id_raza = p.Id_raza\n                JOIN Especie e ON e.Id_especie = r.Id_especie\n                LEFT JOIN usuarios u ON u.id = d.usuario_id\n                WHERE p.estado <> 'Eliminado'\n            "
            params: tuple[Any, ...] = ()
            if usuario_id is not None:
                query += ' AND d.usuario_id = ?'
                params = (usuario_id,)
            query += ' ORDER BY p.id_paciente ASC'
            return [dict(r) for r in conn.execute(query, params).fetchall()]
        finally:
            self._close_if_file(conn)

    def crear_mascota(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            uid = int(datos['usuario_id'])
            owner_id = self._owner_id_for_user(conn, uid)
            race_id = self._resolve_raza_id(conn, str(datos.get('especie', 'Perro')), str(datos.get('raza', 'Mestizo')), 'Registrada desde perfil de cliente')
            age = max(0, int(datos.get('edad', 1)))
            birth = str(datos.get('fecha_nacimiento') or f'{max(1900, date.today().year - age):04d}-01-01')
            cur = conn.execute("INSERT INTO Paciente (id_dueno, Id_raza, nombre, sexo, fecha_nacimiento, peso_kg, historial_resumen, estado) VALUES (?, ?, ?, ?, ?, ?, ?, 'Activo')", (owner_id, race_id, str(datos['nombre']).strip(), str(datos.get('sexo', 'H')).strip()[:1].upper(), birth, float(datos.get('peso_kg', 5.0)), str(datos.get('historial_resumen', '')).strip()))
            pet_id = int(cur.lastrowid)
            self._commit_and_sync(conn)
            return self._mascota_row(conn, pet_id) or {'id': pet_id}
        finally:
            self._close_if_file(conn)

    def eliminar_mascota(self, mascota_id: int, usuario_id: Optional[int]=None) -> bool:
        conn = self._get_connection()
        try:
            if usuario_id is None:
                cur = conn.execute("UPDATE Paciente SET estado = 'Eliminado' WHERE id_paciente = ? AND estado <> 'Eliminado'", (mascota_id,))
            else:
                cur = conn.execute("UPDATE Paciente SET estado = 'Eliminado' WHERE id_paciente = ? AND id_dueno = (SELECT id_dueno FROM Dueno WHERE usuario_id = ?) AND estado <> 'Eliminado'", (mascota_id, usuario_id))
            self._commit_and_sync(conn)
            return cur.rowcount == 1
        finally:
            self._close_if_file(conn)

    def obtener_disponibilidad_horarios(self, fecha: str) -> Dict[str, Any]:
        horarios = ['08:30', '10:00', '11:30', '13:00', '15:30', '17:00', '18:30']
        conn = self._get_connection()
        try:
            counts = {str(r['hora'])[:5]: int(r['ocupados']) for r in conn.execute("SELECT hora, COUNT(*) AS ocupados FROM Cita WHERE fecha = ? AND lower(estado) <> 'cancelada' GROUP BY hora", (fecha,)).fetchall()}
            return {'fecha': fecha, 'capacidad_por_turno': 3, 'horarios': {h: {'ocupados': counts.get(h, 0), 'capacidad_maxima': 3, 'disponible': counts.get(h, 0) < 3} for h in horarios}}
        finally:
            self._close_if_file(conn)

    def _resolve_cita_paciente(self, conn: sqlite3.Connection, datos: Dict[str, Any]) -> int:
        pet_id = datos.get('mascota_id')
        if pet_id is not None:
            pet = conn.execute('SELECT p.id_paciente, d.usuario_id, d.id_dueno FROM Paciente p JOIN Dueno d ON d.id_dueno = p.id_dueno WHERE p.id_paciente = ?', (int(pet_id),)).fetchone()
            if pet:
                if datos.get('usuario_id') is not None and int(pet['usuario_id'] or -1) != int(datos['usuario_id']):
                    raise ValueError('La mascota no pertenece al usuario de la cita.')
                telefono = str(datos.get('telefono', '')).strip()
                if telefono:
                    conn.execute("UPDATE Dueno SET telefono = ? WHERE id_dueno = ? AND telefono = ''", (telefono, pet['id_dueno']))
                return int(pet['id_paciente'])
        propietario = str(datos.get('propietario', '')).strip() or 'Cliente'
        telefono = str(datos.get('telefono', '')).strip()
        mascota_nombre = str(datos.get('mascota_nombre') or datos.get('mascota') or 'Mascota').strip()
        if datos.get('usuario_id') is not None:
            owner_id = self._owner_id_for_user(conn, int(datos['usuario_id']), create=True)
            if telefono and owner_id:
                conn.execute("UPDATE Dueno SET telefono = ? WHERE id_dueno = ? AND telefono = ''", (telefono, owner_id))
        else:
            parts = propietario.split(' ', 1)
            nombres, apellidos = (parts[0], parts[1] if len(parts) > 1 else '')
            existing_owner = conn.execute('SELECT id_dueno FROM Dueno WHERE lower(nombres) = lower(?) AND lower(apellidos) = lower(?) AND telefono = ? LIMIT 1', (nombres, apellidos, telefono)).fetchone()
            owner_id = int(existing_owner[0]) if existing_owner else int(conn.execute("INSERT INTO Dueno (usuario_id, dni, tipo_documento, nombres, apellidos, telefono) VALUES (NULL, ?, 'DNI', ?, ?, ?)", (f'EXT{secrets.token_hex(4).upper()}', nombres, apellidos, telefono)).lastrowid)
        existing_pet = conn.execute('SELECT id_paciente FROM Paciente WHERE id_dueno = ? AND lower(nombre) = lower(?) LIMIT 1', (owner_id, mascota_nombre)).fetchone()
        if existing_pet:
            return int(existing_pet[0])
        raza = conn.execute('SELECT Id_raza FROM Razas ORDER BY Id_raza LIMIT 1').fetchone()
        raza_id = int(raza[0]) if raza else 1
        return int(conn.execute("INSERT INTO Paciente (id_dueno, Id_raza, nombre, sexo, fecha_nacimiento, peso_kg, historial_resumen, estado) VALUES (?, ?, ?, 'H', ?, 5.0, '', 'Activo')", (owner_id, raza_id, mascota_nombre, date.today().isoformat())).lastrowid)

    def crear_cita(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            fecha = str(datos['fecha']).strip()[:10]
            hora = str(datos['hora']).strip()[:5]
            occupied = conn.execute("SELECT COUNT(*) FROM Cita WHERE fecha = ? AND substr(hora, 1, 5) = ? AND lower(estado) <> 'cancelada'", (fecha, hora)).fetchone()[0]
            if occupied >= 3:
                raise ValueError(f'El horario {hora} del {fecha} ya cuenta con sus 3 cupos médicos ocupados. Elige otro horario.')
            vet_id = None
            doctor = datos.get('doctor_id')
            if doctor is not None:
                found = conn.execute('SELECT Id_veterinario FROM Veterinario WHERE usuario_id = ?', (doctor,)).fetchone()
                if not found:
                    found = conn.execute('SELECT Id_veterinario FROM Veterinario WHERE Id_veterinario = ?', (doctor,)).fetchone()
                if found:
                    vet_id = int(found[0])
            if vet_id is None:
                found = conn.execute('SELECT Id_veterinario FROM Veterinario ORDER BY Id_veterinario LIMIT 1').fetchone()
                if not found:
                    raise ValueError('No hay veterinarios registrados para asignar la cita.')
                vet_id = int(found[0])
            pet_id = self._resolve_cita_paciente(conn, datos)
            service_key = str(datos.get('servicio', '')).strip()
            service_name = WhatsAppAdapter.SERVICIOS_NOMBRES.get(service_key, service_key or 'Consulta general')
            service = conn.execute('SELECT Id_servicios, Precio FROM Servicios WHERE lower(Nombre) = lower(?) LIMIT 1', (service_name,)).fetchone()
            if not service:
                service = conn.execute('SELECT Id_servicios, Precio FROM Servicios ORDER BY Id_servicios LIMIT 1').fetchone()
            cur = conn.execute('INSERT INTO Cita (Id_veterinario, id_paciente, fecha, hora, motivo, estado, whatsapp_url) VALUES (?, ?, ?, ?, ?, ?, ?)', (vet_id, pet_id, fecha, hora, str(datos.get('motivo', '')).strip(), str(datos.get('estado', 'pendiente')).lower(), str(datos.get('whatsapp_url', '')).strip()))
            cita_id = int(cur.lastrowid)
            if service:
                conn.execute('INSERT INTO Detalle_servicios (Id_cita, Id_servicios, precio_aplicado) VALUES (?, ?, ?)', (cita_id, int(service[0]), float(service[1])))
            if datos.get('diagnostico') or datos.get('tratamiento'):
                conn.execute('INSERT INTO Historial_clinico (Id_cita, Diagnostico, Tratamiento) VALUES (?, ?, ?)', (cita_id, datos.get('diagnostico', '') or '', datos.get('tratamiento', '') or ''))
            self._commit_and_sync(conn)
            return self._cita_row(conn, cita_id) or {'id': cita_id}
        finally:
            self._close_if_file(conn)

    def listar_citas(self, usuario_id: Optional[int]=None) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            if usuario_id is None:
                return self._query_citas(conn, 'ORDER BY c.fecha, c.hora, c.Id_cita')
            return self._query_citas(conn, 'WHERE d.usuario_id = ? ORDER BY c.fecha, c.hora, c.Id_cita', (usuario_id,))
        finally:
            self._close_if_file(conn)

    def actualizar_cita_doctor(self, cita_id: int, estado: str, diagnostico: str, tratamiento: str, doctor_id: Optional[int]=None) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            if doctor_id is None:
                cur = conn.execute('UPDATE Cita SET estado = ? WHERE Id_cita = ?', (estado, cita_id))
            else:
                vet = conn.execute('SELECT Id_veterinario FROM Veterinario WHERE usuario_id = ?', (doctor_id,)).fetchone()
                if not vet:
                    vet = conn.execute('SELECT Id_veterinario FROM Veterinario WHERE Id_veterinario = ?', (doctor_id,)).fetchone()
                cur = conn.execute('UPDATE Cita SET estado = ?, Id_veterinario = COALESCE(?, Id_veterinario) WHERE Id_cita = ?', (estado, int(vet[0]) if vet else None, cita_id))
            if cur.rowcount == 0:
                return None
            hist = conn.execute('SELECT Id_historial FROM Historial_clinico WHERE Id_cita = ? ORDER BY Id_historial DESC LIMIT 1', (cita_id,)).fetchone()
            if hist:
                conn.execute('UPDATE Historial_clinico SET Diagnostico = ?, Tratamiento = ? WHERE Id_historial = ?', (diagnostico, tratamiento, hist[0]))
            elif diagnostico or tratamiento:
                conn.execute('INSERT INTO Historial_clinico (Id_cita, Diagnostico, Tratamiento) VALUES (?, ?, ?)', (cita_id, diagnostico, tratamiento))
            self._commit_and_sync(conn)
            return self._cita_row(conn, cita_id)
        finally:
            self._close_if_file(conn)

    def listar_productos(self, solo_activos: bool=True) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.execute('SELECT * FROM productos WHERE activo = 1 ORDER BY id ASC' if solo_activos else 'SELECT * FROM productos ORDER BY id ASC')
            return [dict(r) for r in cur.fetchall()]
        finally:
            self._close_if_file(conn)

    def obtener_producto(self, producto_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            row = conn.execute('SELECT * FROM productos WHERE id = ?', (producto_id,)).fetchone()
            return dict(row) if row else None
        finally:
            self._close_if_file(conn)

    def descontar_stock_producto(self, producto_id: int, cantidad: int) -> bool:
        conn = self._get_connection()
        try:
            cur = conn.execute('UPDATE productos SET stock = stock - ? WHERE id = ? AND stock >= ?', (cantidad, producto_id, cantidad))
            self._commit_and_sync(conn)
            return cur.rowcount == 1
        finally:
            self._close_if_file(conn)

    def registrar_venta_y_detalles(self, cabecera: Dict[str, Any], detalles: List[Dict[str, Any]]) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            uid = int(cabecera['usuario_id'])
            owner_id = self._owner_id_for_user(conn, uid)
            doc_cliente = str(cabecera.get('cliente_documento') or '').strip()
            nombre_cliente = str(cabecera.get('cliente_nombre') or 'Cliente Patitas Felices').strip()
            if owner_id is None:
                existing_dueno = conn.execute('SELECT id_dueno FROM Dueno WHERE dni = ? LIMIT 1', (doc_cliente,)).fetchone() if doc_cliente and doc_cliente != '00000000' else None
                if existing_dueno:
                    owner_id = int(existing_dueno[0])
                else:
                    parts = nombre_cliente.split(' ', 1)
                    dni_guest = doc_cliente if doc_cliente and doc_cliente != '00000000' else f'EXT{secrets.token_hex(4).upper()}'
                    tipo_guest = 'RUC' if len(doc_cliente) == 11 else 'DNI'
                    owner_id = int(conn.execute("INSERT INTO Dueno (usuario_id, dni, tipo_documento, nombres, apellidos, telefono) VALUES (NULL, ?, ?, ?, ?, '')", (dni_guest, tipo_guest, parts[0], parts[1] if len(parts) > 1 else '')).lastrowid)
            elif doc_cliente and doc_cliente != '00000000':
                current_dueno = conn.execute('SELECT dni FROM Dueno WHERE id_dueno = ?', (owner_id,)).fetchone()
                if current_dueno and (str(current_dueno['dni']).startswith('CLI') or str(current_dueno['dni']).startswith('EXT')):
                    dup_dni = conn.execute('SELECT 1 FROM Dueno WHERE dni = ? AND id_dueno <> ?', (doc_cliente, owner_id)).fetchone()
                    if not dup_dni:
                        tipo_doc = 'RUC' if len(doc_cliente) == 11 else 'DNI'
                        conn.execute('UPDATE Dueno SET dni = ?, tipo_documento = ? WHERE id_dueno = ?', (doc_cliente, tipo_doc, owner_id))
            number_text = str(cabecera['numero_boleta'])
            series, _, suffix = number_text.partition('-')
            series = series or 'B001'
            number = int(suffix or '1')
            if conn.execute('SELECT 1 FROM Factura WHERE serie = ? AND numero = ?', (series, number)).fetchone():
                raise ValueError(f'El numero de boleta {number_text} ya existe.')
            cur = conn.execute("INSERT INTO Factura (id_dueno, tipo, serie, numero, subtotal, igv, total, estado) VALUES (?, 'Boleta', ?, ?, ?, ?, ?, ?)", (owner_id, series, number, cabecera['subtotal'], cabecera['igv'], cabecera['total'], str(cabecera.get('estado', 'pagado')).capitalize()))
            invoice_id = int(cur.lastrowid)
            for detail in detalles:
                conn.execute('INSERT INTO detalle_ventas (id_factura, producto_id, cantidad, precio_unitario, subtotal) VALUES (?, ?, ?, ?, ?)', (invoice_id, detail['producto_id'], detail['cantidad'], detail['precio_unitario'], detail['subtotal']))
            conn.execute('INSERT INTO Pago (id_factura, metodo_pago, monto, estado) VALUES (?, ?, ?, ?)', (invoice_id, cabecera.get('metodo_pago', 'Tarjeta / Yape'), cabecera['total'], str(cabecera.get('estado', 'pagado')).capitalize()))
            self._commit_and_sync(conn)
            return self._factura_row(conn, invoice_id) or {'id': invoice_id}
        finally:
            self._close_if_file(conn)

    def _query_facturas(self, conn: sqlite3.Connection, where_order_sql: str, params: tuple[Any, ...]=()) -> List[Dict[str, Any]]:
        rows = conn.execute(f"\n            SELECT f.id_factura, f.id_factura AS id, f.Id_cita, f.id_dueno, d.usuario_id,\n                   f.tipo, f.serie, f.numero,\n                   (f.serie || '-' || printf('%06d', f.numero)) AS numero_boleta,\n                   COALESCE(u.nombre, trim(d.nombres || ' ' || d.apellidos), 'Cliente Patitas Felices') AS cliente_nombre,\n                   COALESCE(CASE WHEN d.dni LIKE 'CLI%' OR d.dni LIKE 'EXT%' THEN NULL ELSE d.dni END, '00000000') AS cliente_documento,\n                   f.fecha_emision, f.fecha_emision AS creado_en, f.subtotal, f.igv, f.total,\n                   COALESCE(pg.metodo_pago, 'Tarjeta / Yape') AS metodo_pago, f.estado, f.pdf_url\n            FROM Factura f\n            LEFT JOIN Dueno d ON d.id_dueno = f.id_dueno\n            LEFT JOIN usuarios u ON u.id = d.usuario_id\n            LEFT JOIN Pago pg ON pg.id_pago = (\n                SELECT MAX(p2.id_pago) FROM Pago p2 WHERE p2.id_factura = f.id_factura\n            )\n            {where_order_sql}\n            ", params).fetchall()
        if not rows:
            return []
        facturas = [dict(r) for r in rows]
        inv_ids = [int(f['id_factura']) for f in facturas]
        placeholders = ','.join(('?' for _ in inv_ids))
        detalles_rows = conn.execute(f'\n            SELECT dv.id, dv.id_factura, dv.producto_id, pr.nombre AS producto_nombre,\n                   dv.cantidad, dv.precio_unitario, dv.subtotal\n            FROM detalle_ventas dv\n            JOIN productos pr ON pr.id = dv.producto_id\n            WHERE dv.id_factura IN ({placeholders})\n            ORDER BY dv.id\n            ', tuple(inv_ids)).fetchall()
        detalles_map: Dict[int, List[Dict[str, Any]]] = {iid: [] for iid in inv_ids}
        for d in detalles_rows:
            det_dict = dict(d)
            detalles_map[int(det_dict['id_factura'])].append(det_dict)
        for f in facturas:
            f['detalles'] = detalles_map.get(int(f['id_factura']), [])
        return facturas

    def _factura_row(self, conn: sqlite3.Connection, invoice_id: int) -> Optional[Dict[str, Any]]:
        items = self._query_facturas(conn, 'WHERE f.id_factura = ?', (invoice_id,))
        return items[0] if items else None

    def listar_ventas(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            return self._query_facturas(conn, 'ORDER BY f.id_factura DESC')
        finally:
            self._close_if_file(conn)

    def obtener_todas_las_16_tablas(self) -> Dict[str, List[Dict[str, Any]]]:
        conn = self._get_connection()
        try:
            resultado: Dict[str, List[Dict[str, Any]]] = {}
            for tabla in self.NOMBRES_16_TABLAS:
                try:
                    filas = conn.execute(f'SELECT * FROM {tabla}').fetchall()
                    resultado[tabla] = [dict(f) for f in filas]
                except Exception:
                    resultado[tabla] = []
            return resultado
        finally:
            self._close_if_file(conn)

# =============================================================================
# 4. ADAPTADORES MICROSOFT SQL SERVER Y COMPATIBILIDAD SUPABASE
# =============================================================================
class SQLServerDatabaseAdapter(SQLiteDatabaseAdapter):
    """
    Adaptador conectado a Microsoft SQL Server (`PatitasFelices_DB` en `localhost`)
    mediante ODBC nativo de Windows (`odbc32.dll`), con respaldo local transaccional.
    """

    def __init__(self, server: Optional[str]=None, database: Optional[str]=None, db_path: Optional[str]=None) -> None:
        self.server = (server or os.getenv('SQLSERVER_SERVER', 'localhost')).strip()
        self.database = (database or os.getenv('SQLSERVER_DATABASE', 'PatitasFelices_DB')).strip()
        super().__init__(db_path=db_path)

class SupabasePostgresAdapter(SQLiteDatabaseAdapter):
    """Adaptador de compatibilidad y fallback sin conexión para pruebas de resiliencia."""

    def __init__(self, supabase_url: Optional[str]=None, supabase_key: Optional[str]=None, db_path: Optional[str]=None) -> None:
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
        return SQLServerDatabaseAdapter(db_path=str(full_path))
    return SQLServerDatabaseAdapter()
