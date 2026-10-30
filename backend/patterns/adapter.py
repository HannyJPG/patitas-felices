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
        return conn

    def _close_if_file(self, conn: sqlite3.Connection) -> None:
        if self._persistent_conn is None:
            conn.close()

    def inicializar_esquema(self) -> None:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS Dueno (id_dueno INTEGER PRIMARY KEY AUTOINCREMENT, dni TEXT NOT NULL UNIQUE, correo TEXT NOT NULL UNIQUE, nombres TEXT NOT NULL, apellidos TEXT NOT NULL, telefono TEXT NOT NULL, fecha_registro TEXT NOT NULL DEFAULT (datetime('now', 'localtime')));
                CREATE TABLE IF NOT EXISTS Especie (Id_especie INTEGER PRIMARY KEY AUTOINCREMENT, Nombre TEXT NOT NULL, Descripcion TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS Razas (Id_raza INTEGER PRIMARY KEY AUTOINCREMENT, Id_especie INTEGER NOT NULL, nombre TEXT NOT NULL, Descripcion TEXT);
                CREATE TABLE IF NOT EXISTS Paciente (id_paciente INTEGER PRIMARY KEY AUTOINCREMENT, id_dueno INTEGER NOT NULL, Id_raza INTEGER NOT NULL, nombre TEXT NOT NULL, raza TEXT NOT NULL, sexo TEXT NOT NULL DEFAULT 'H', fecha_nacimiento TEXT NOT NULL DEFAULT '2023-05-10', estado TEXT NOT NULL DEFAULT 'Activo', fecha_registro TEXT NOT NULL DEFAULT (datetime('now', 'localtime')));
                CREATE TABLE IF NOT EXISTS Especialidad (Id_especialidad INTEGER PRIMARY KEY AUTOINCREMENT, Nombre TEXT NOT NULL, Descripcion TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS Veterinario (Id_veterinario INTEGER PRIMARY KEY AUTOINCREMENT, Id_especialidad INTEGER NOT NULL, numero_colegiatura TEXT NOT NULL UNIQUE, nombres TEXT NOT NULL, Apellidos TEXT NOT NULL, Telefono TEXT NOT NULL, correo TEXT NOT NULL UNIQUE, Fecha_contratacion TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS Servicios (Id_servicios INTEGER PRIMARY KEY AUTOINCREMENT, Nombre TEXT NOT NULL, Precio REAL NOT NULL, Estado TEXT NOT NULL DEFAULT 'Activo');
                CREATE TABLE IF NOT EXISTS Cita (Id_cita INTEGER PRIMARY KEY AUTOINCREMENT, Id_veterinario INTEGER NOT NULL, id_paciente INTEGER NOT NULL, fecha TEXT NOT NULL, motivo TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'Pendiente', fecha_registro TEXT NOT NULL DEFAULT (datetime('now', 'localtime')));
                CREATE TABLE IF NOT EXISTS Detalle_servicios (Id_cita INTEGER NOT NULL, Id_servicios INTEGER NOT NULL, precio_aplicado REAL NOT NULL, PRIMARY KEY (Id_cita, Id_servicios));
                CREATE TABLE IF NOT EXISTS Historial_clinico (Id_historial INTEGER PRIMARY KEY AUTOINCREMENT, Id_cita INTEGER NOT NULL, Fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')), Diagnostico TEXT NOT NULL, Tratamiento TEXT NOT NULL, Observaciones TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS Receta (Id_receta INTEGER PRIMARY KEY AUTOINCREMENT, Id_historial INTEGER NOT NULL, medicamento TEXT NOT NULL, Dosis TEXT NOT NULL, duracion_dias INTEGER NOT NULL, indicaciones TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS Factura (id_factura INTEGER PRIMARY KEY AUTOINCREMENT, Id_cita INTEGER, id_dueno INTEGER NOT NULL, tipo TEXT NOT NULL DEFAULT 'Boleta', serie TEXT NOT NULL DEFAULT 'B001', numero INTEGER NOT NULL, fecha_emision TEXT NOT NULL DEFAULT (datetime('now', 'localtime')), subtotal REAL NOT NULL, igv REAL NOT NULL, estado TEXT NOT NULL DEFAULT 'Pagado', xml_url TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS Pago (id_pago INTEGER PRIMARY KEY AUTOINCREMENT, Id_servicios INTEGER NOT NULL, descripcioon TEXT NOT NULL, cantidad INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, rol TEXT NOT NULL CHECK(rol IN ('cliente', 'doctor', 'admin')), estado TEXT NOT NULL DEFAULT 'activo' CHECK(estado IN ('activo', 'inactivo')), telefono TEXT, tipo_documento TEXT DEFAULT 'DNI', documento TEXT, creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')));
                CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL, categoria TEXT NOT NULL, descripcion TEXT NOT NULL, precio REAL NOT NULL, stock INTEGER NOT NULL DEFAULT 0, activo INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS detalle_ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER NOT NULL, producto_id INTEGER NOT NULL, producto_nombre TEXT NOT NULL, cantidad INTEGER NOT NULL, precio_unitario REAL NOT NULL, subtotal REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS mascotas (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER NOT NULL, nombre TEXT NOT NULL, especie TEXT NOT NULL DEFAULT 'Perro', raza TEXT NOT NULL DEFAULT 'Mestizo', edad INTEGER NOT NULL DEFAULT 1, peso_kg REAL NOT NULL DEFAULT 5.0, historial_resumen TEXT, creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')));
                CREATE TABLE IF NOT EXISTS citas (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, mascota_id INTEGER, doctor_id INTEGER, propietario TEXT NOT NULL, telefono TEXT NOT NULL, mascota_nombre TEXT NOT NULL, servicio TEXT NOT NULL, fecha TEXT NOT NULL, hora TEXT NOT NULL, motivo TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'pendiente', diagnostico TEXT DEFAULT '', tratamiento TEXT DEFAULT '', whatsapp_url TEXT DEFAULT '', creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')));
                CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, numero_boleta TEXT NOT NULL UNIQUE, usuario_id INTEGER NOT NULL, cliente_nombre TEXT NOT NULL, cliente_documento TEXT NOT NULL, subtotal REAL NOT NULL, igv REAL NOT NULL, total REAL NOT NULL, metodo_pago TEXT NOT NULL DEFAULT 'Tarjeta / Yape', estado TEXT NOT NULL DEFAULT 'pagado', creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')));
                CREATE TABLE IF NOT EXISTS solicitudes_mascota (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER NOT NULL, mascota_id INTEGER NOT NULL, tipo TEXT NOT NULL, datos_nuevos TEXT, motivo TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'pendiente', creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')));
                """
            )
            # Asegurar columnas tipo_documento y documento en usuarios si la tabla ya existía
            try:
                cur.execute("ALTER TABLE usuarios ADD COLUMN tipo_documento TEXT DEFAULT 'DNI'")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE usuarios ADD COLUMN documento TEXT")
            except Exception:
                pass

            cur.execute("SELECT COUNT(*) AS total FROM usuarios")
            if cur.fetchone()["total"] == 0:
                usuarios_iniciales = (
                    [
                        ("Dra. Melany Díaz (Admin)", "admin@patitasfelices.pe", hashear_password("admin123"), "admin", "activo", "990853697"),
                        ("Dr. Carlos Mendoza (Doctor)", "doctor@patitasfelices.pe", hashear_password("doctor123"), "doctor", "activo", "987654321"),
                        ("Lucía Fernández (Cliente)", "cliente@patitasfelices.pe", hashear_password("cliente123"), "cliente", "activo", "912345678"),
                        ("Usuario Suspendido (Prueba Proxy)", "inactivo@patitasfelices.pe", hashear_password("inactivo123"), "cliente", "inactivo", "900000000"),
                    ]
                    if self.db_path == ":memory:"
                    else [
                        ("Dra. Melany Díaz (Admin)", "admin@patitasfelices.pe", hashear_password("admin123"), "admin", "activo", "990853697"),
                    ]
                )
                cur.executemany(
                    "INSERT INTO usuarios (nombre, email, password_hash, rol, estado, telefono) VALUES (?, ?, ?, ?, ?, ?)",
                    usuarios_iniciales,
                )
                cur.executemany(
                    "INSERT INTO Dueno (dni, correo, nombres, apellidos, telefono) VALUES (?, ?, ?, ?, ?)",
                    [
                        ("74859632", "cliente@patitasfelices.pe", "Lucía", "Fernández", "912345678"),
                        ("45896321", "jorge.ramirez@correo.pe", "Jorge", "Ramírez", "987112233"),
                    ],
                )
                cur.executemany(
                    "INSERT INTO Especie (Nombre, Descripcion) VALUES (?, ?)",
                    [
                        ("Canino", "Perros domésticos de todas las razas"),
                        ("Felino", "Gatos domésticos"),
                    ],
                )
                cur.executemany(
                    "INSERT INTO Razas (Id_especie, nombre, Descripcion) VALUES (?, ?, ?)",
                    [
                        (1, "Golden Retriever", "Raza mediana-grande de temperamento dócil"),
                        (2, "Siamés", "Felino de pelaje corto y ojos azules"),
                    ],
                )
                cur.executemany(
                    "INSERT INTO Paciente (id_dueno, Id_raza, nombre, raza, sexo, fecha_nacimiento, estado) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (1, 1, "Luna", "Golden Retriever", "H", "2023-03-15", "Activo"),
                        (1, 2, "Michi", "Siamés", "M", "2024-06-10", "Activo"),
                    ],
                )
                cur.executemany(
                    "INSERT INTO Especialidad (Nombre, Descripcion) VALUES (?, ?)",
                    [
                        ("Medicina General e Interna", "Diagnóstico clínico primario y prevención"),
                        ("Dermatología y Cirugía Menor", "Cuidado especializado de piel y tejidos"),
                    ],
                )
                cur.executemany(
                    "INSERT INTO Veterinario (Id_veterinario, Id_especialidad, numero_colegiatura, nombres, Apellidos, Telefono, correo, Fecha_contratacion) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (1, 1, "CMVP-10452", "Carlos", "Mendoza", "987654321", "doctor@patitasfelices.pe", "2024-01-15"),
                        (2, 2, "CMVP-11890", "Melany", "Díaz Marín", "990853697", "admin@patitasfelices.pe", "2023-08-01"),
                    ],
                )
                cur.executemany(
                    "INSERT INTO Servicios (Nombre, Precio, Estado) VALUES (?, ?, ?)",
                    [
                        ("Consulta general", 60.00, "Activo"),
                        ("Vacunación", 75.00, "Activo"),
                        ("Desparasitación", 45.00, "Activo"),
                        ("Control y seguimiento", 40.00, "Activo"),
                    ],
                )
                cur.executemany(
                    "INSERT INTO Cita (Id_veterinario, id_paciente, fecha, motivo, estado) VALUES (?, ?, ?, ?, ?)",
                    [
                        (1, 1, "2026-10-28 10:00", "Revisión preventiva de piel y control de peso.", "Confirmada"),
                        (2, 2, "2026-10-29 11:30", "Refuerzo anual de vacuna triple felina.", "Pendiente"),
                    ],
                )
                cur.executemany(
                    "INSERT INTO Detalle_servicios (Id_cita, Id_servicios, precio_aplicado) VALUES (?, ?, ?)",
                    [
                        (1, 1, 60.00),
                        (2, 2, 75.00),
                    ],
                )
                cur.executemany(
                    "INSERT INTO Historial_clinico (Id_cita, Diagnostico, Tratamiento, Observaciones) VALUES (?, ?, ?, ?)",
                    [
                        (1, "Dermatitis alérgica leve controlada.", "Baño con clorhexidina cada 7 días.", "Paciente dócil, peso 24.5 kg."),
                    ],
                )
                cur.executemany(
                    "INSERT INTO Receta (Id_historial, medicamento, Dosis, duracion_dias, indicaciones) VALUES (?, ?, ?, ?, ?)",
                    [
                        (1, "Shampoo Dermatológico Clorhexidina 250ml", "Aplicación tópica dejando actuar 10 min", 21, "Secar con toalla limpia sin frotar."),
                    ],
                )
                cur.executemany(
                    "INSERT INTO Factura (Id_cita, id_dueno, tipo, serie, numero, subtotal, igv, estado, xml_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (1, 1, "Boleta", "B001", 1, 50.85, 9.15, "Pagado", "/api/tienda/boleta/1/pdf"),
                    ],
                )
                cur.executemany(
                    "INSERT INTO Pago (Id_servicios, descripcioon, cantidad) VALUES (?, ?, ?)",
                    [
                        (1, "Pago Yape por Consulta general de Luna", 1),
                    ],
                )
                cur.executemany(
                    "INSERT INTO productos (codigo, nombre, categoria, descripcion, precio, stock, activo) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        ("VET-001", "Antipulgas Bravecto Chewable 10-20kg", "Farmacia", "Protección oral por 12 semanas contra pulgas y garrapatas.", 145.00, 25, 1),
                        ("VET-002", "Alimento Clínico Renal Canine 2kg", "Nutrición", "Dieta terapéutica de soporte renal e hidratación.", 89.50, 18, 1),
                        ("VET-003", "Shampoo Dermatológico Clorhexidina 250ml", "Higiene", "Fórmula hipoalergénica antiséptica para piel sensible.", 48.00, 30, 1),
                        ("VET-004", "Suplemento Omega 3 & Vitaminas Pelaje", "Suplementos", "60 cápsulas blandas para articulaciones y brillo capilar.", 65.00, 20, 1),
                        ("VET-005", "Collar Isabelino Ajustable Acolchado", "Accesorios", "Recuperación postoperatoria cómoda sin roce.", 35.00, 15, 1),
                        ("VET-006", "Kit Dental Enzimático Veterinario", "Higiene", "Pasta enzimática y cepillo suave de doble cabezal.", 42.00, 12, 1),
                    ],
                )
                cur.executemany(
                    "INSERT INTO mascotas (usuario_id, nombre, especie, raza, edad, peso_kg, historial_resumen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (3, "Luna", "Perro", "Golden Retriever", 3, 24.5, "Vacunación séxtuple vigente. Peso saludable."),
                        (3, "Michi", "Gato", "Siamés", 2, 4.2, "Desparasitación interna completada en octubre."),
                    ],
                )
                cur.executemany(
                    """
                    INSERT INTO citas (
                        usuario_id, mascota_id, doctor_id, propietario, telefono,
                        mascota_nombre, servicio, fecha, hora, motivo, estado,
                        diagnostico, tratamiento, whatsapp_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            3, 1, 2, "Lucía Fernández", "912345678", "Luna", "consulta-general",
                            "2026-10-30", "10:00", "Revisión preventiva de piel y control de peso.",
                            "confirmada", "Dermatitis leve controlada.", "Baño medicado cada 7 días por 3 semanas.",
                            "https://wa.me/51990853697?text=Cita%20confirmada",
                        ),
                        (
                            3, 2, 2, "Lucía Fernández", "912345678", "Michi", "vacunacion",
                            "2026-10-31", "11:30", "Refuerzo anual de vacuna triple felina.",
                            "pendiente", "", "", "https://wa.me/51990853697?text=Solicitud%20vacunacion",
                        ),
                    ],
                )
            # Migrar automáticamente contraseñas en texto plano preexistentes a PBKDF2-SHA256
            filas_u = cur.execute("SELECT id, password_hash FROM usuarios").fetchall()
            for u_row in filas_u:
                ph_actual = u_row["password_hash"] or ""
                if ph_actual and not str(ph_actual).startswith(_PBKDF2_PREFIX):
                    cur.execute(
                        "UPDATE usuarios SET password_hash = ? WHERE id = ?",
                        (hashear_password(str(ph_actual)), u_row["id"]),
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
        conn = self._get_connection()
        try:
            password_seguro = hashear_password(str(datos["password_hash"]))
            cur = conn.execute(
                """
                INSERT INTO usuarios (nombre, email, password_hash, rol, estado, telefono, tipo_documento, documento)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datos["nombre"].strip(),
                    datos["email"].strip().lower(),
                    password_seguro,
                    datos.get("rol", "cliente"),
                    datos.get("estado", "activo"),
                    datos.get("telefono", "").strip(),
                    datos.get("tipo_documento", "DNI"),
                    datos.get("documento"),
                ),
            )
            nuevo_id = cur.lastrowid
            # Sincronización automática con la tabla Dueno del DER de 16 tablas
            if datos.get("rol", "cliente") == "cliente":
                partes = datos["nombre"].strip().split(" ", 1)
                nombres = partes[0]
                apellidos = partes[1] if len(partes) > 1 else "Cliente"
                dni_val = datos.get("documento") or f"CLI{nuevo_id:05d}"
                cur.execute(
                    """
                    INSERT OR IGNORE INTO Dueno (dni, correo, nombres, apellidos, telefono)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (dni_val, datos["email"].strip().lower(), nombres, apellidos, datos.get("telefono", "").strip()),
                )
            conn.commit()
            cur = conn.execute("SELECT id, nombre, email, password_hash, rol, estado, telefono, tipo_documento, documento, creado_en FROM usuarios WHERE id = ?", (nuevo_id,))
            return dict(cur.fetchone())
        finally:
            self._close_if_file(conn)

    def actualizar_documento_usuario(self, usuario_id: int, tipo_documento: str, documento: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            conn.execute(
                "UPDATE usuarios SET tipo_documento = ?, documento = ? WHERE id = ?",
                (tipo_documento, documento, usuario_id),
            )
            cur = conn.execute("SELECT email FROM usuarios WHERE id = ?", (usuario_id,))
            row = cur.fetchone()
            if row:
                conn.execute("UPDATE Dueno SET dni = ? WHERE correo = ?", (documento, row["email"]))
            conn.commit()
            return self.obtener_usuario_por_id(usuario_id)
        finally:
            self._close_if_file(conn)

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
        conn = self._get_connection()
        try:
            cur = conn.execute("SELECT * FROM ventas WHERE usuario_id = ? ORDER BY id DESC", (usuario_id,))
            ventas = [dict(r) for r in cur.fetchall()]
            for v in ventas:
                cur_det = conn.execute("SELECT * FROM detalle_ventas WHERE venta_id = ? ORDER BY id ASC", (v["id"],))
                v["detalles"] = [dict(d) for d in cur_det.fetchall()]
            return ventas
        finally:
            self._close_if_file(conn)

    def crear_solicitud_mascota(
        self, usuario_id: int, mascota_id: int, tipo: str, motivo: str, datos_nuevos: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        import json
        conn = self._get_connection()
        try:
            datos_json = json.dumps(datos_nuevos) if datos_nuevos else None
            cur = conn.execute(
                """
                INSERT INTO solicitudes_mascota (usuario_id, mascota_id, tipo, datos_nuevos, motivo, estado)
                VALUES (?, ?, ?, ?, ?, 'pendiente')
                """,
                (usuario_id, mascota_id, tipo, datos_json, motivo.strip()),
            )
            conn.commit()
            solicitud_id = cur.lastrowid
            cur = conn.execute("SELECT * FROM solicitudes_mascota WHERE id = ?", (solicitud_id,))
            return dict(cur.fetchone())
        finally:
            self._close_if_file(conn)

    def listar_solicitudes_mascota(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        import json
        conn = self._get_connection()
        try:
            query = """
                SELECT s.*, u.nombre AS propietario_nombre, u.email AS propietario_email,
                       m.nombre AS mascota_nombre, m.especie AS mascota_especie, m.raza AS mascota_raza
                FROM solicitudes_mascota s
                JOIN usuarios u ON u.id = s.usuario_id
                LEFT JOIN mascotas m ON m.id = s.mascota_id
            """
            params = ()
            if usuario_id is not None:
                query += " WHERE s.usuario_id = ?"
                params = (usuario_id,)
            query += " ORDER BY s.id DESC"
            cur = conn.execute(query, params)
            filas = [dict(r) for r in cur.fetchall()]
            for f in filas:
                if f.get("datos_nuevos"):
                    try:
                        f["datos_nuevos"] = json.loads(f["datos_nuevos"])
                    except Exception:
                        pass
            return filas
        finally:
            self._close_if_file(conn)

    def resolver_solicitud_mascota(self, solicitud_id: int, accion: str) -> Dict[str, Any]:
        import json
        conn = self._get_connection()
        try:
            cur = conn.execute("SELECT * FROM solicitudes_mascota WHERE id = ?", (solicitud_id,))
            solicitud = cur.fetchone()
            if not solicitud:
                raise LookupError("Solicitud no encontrada.")
            solicitud = dict(solicitud)
            if solicitud["estado"] != "pendiente":
                raise ValueError("Esta solicitud ya fue resuelta previamente.")

            accion_limpia = accion.lower().strip()
            if accion_limpia not in ("aprobar", "rechazar"):
                raise ValueError("La acción debe ser 'aprobar' o 'rechazar'.")

            nuevo_estado = "aprobada" if accion_limpia == "aprobar" else "rechazada"

            if accion_limpia == "aprobar":
                if solicitud["tipo"] == "eliminar":
                    conn.execute("DELETE FROM mascotas WHERE id = ?", (solicitud["mascota_id"],))
                elif solicitud["tipo"] == "editar" and solicitud.get("datos_nuevos"):
                    try:
                        nuevos = json.loads(solicitud["datos_nuevos"]) if isinstance(solicitud["datos_nuevos"], str) else solicitud["datos_nuevos"]
                        conn.execute(
                            """
                            UPDATE mascotas SET nombre = ?, especie = ?, raza = ?, edad = ?, peso_kg = ?, historial_resumen = ?
                            WHERE id = ?
                            """,
                            (
                                nuevos.get("nombre", ""),
                                nuevos.get("especie", "Perro"),
                                nuevos.get("raza", "Mestizo"),
                                int(nuevos.get("edad", 1)),
                                float(nuevos.get("peso_kg", 5.0)),
                                nuevos.get("historial_resumen", ""),
                                solicitud["mascota_id"],
                            ),
                        )
                    except Exception as e:
                        raise ValueError(f"Error aplicando cambios de mascota: {e}")

            conn.execute("UPDATE solicitudes_mascota SET estado = ? WHERE id = ?", (nuevo_estado, solicitud_id))
            conn.commit()
            solicitud["estado"] = nuevo_estado
            return solicitud
        finally:
            self._close_if_file(conn)

    def crear_doctor(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            cur = conn.execute(
                """
                INSERT INTO Veterinario (Id_especialidad, numero_colegiatura, nombres, Apellidos, Telefono, correo, Fecha_contratacion)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datos.get("especialidad_id", 1),
                    datos.get("cmvp", "CMVP-00000"),
                    datos.get("nombres", datos.get("nombre", "")),
                    datos.get("apellidos", ""),
                    datos.get("telefono", ""),
                    datos.get("correo", datos.get("email", "")),
                    datos.get("fecha_contratacion", "2026-10-29"),
                ),
            )
            conn.commit()
            return {"id": cur.lastrowid, **datos}
        finally:
            self._close_if_file(conn)

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

    def listar_mascotas(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            if usuario_id is not None:
                cur = conn.execute("SELECT m.*, u.nombre AS propietario_nombre FROM mascotas m JOIN usuarios u ON u.id = m.usuario_id WHERE m.usuario_id = ? ORDER BY m.id ASC", (usuario_id,))
            else:
                cur = conn.execute("SELECT m.*, u.nombre AS propietario_nombre FROM mascotas m JOIN usuarios u ON u.id = m.usuario_id ORDER BY m.id ASC")
            return [dict(r) for r in cur.fetchall()]
        finally:
            self._close_if_file(conn)

    def crear_mascota(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            cur = conn.execute(
                """
                INSERT INTO mascotas (usuario_id, nombre, especie, raza, edad, peso_kg, historial_resumen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(datos["usuario_id"]),
                    str(datos["nombre"]).strip(),
                    str(datos.get("especie", "Perro")).strip(),
                    str(datos.get("raza", "Mestizo")).strip(),
                    int(datos.get("edad", 1)),
                    float(datos.get("peso_kg", 5.0)),
                    str(datos.get("historial_resumen", "")).strip(),
                ),
            )
            nuevo_id = cur.lastrowid
            # Sincronización con la tabla Paciente del modelo de 16 tablas
            try:
                conn.execute(
                    """
                    INSERT INTO Paciente (id_dueno, Id_raza, nombre, raza, sexo, fecha_nacimiento, estado)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(datos["usuario_id"]),
                        1,
                        str(datos["nombre"]).strip(),
                        str(datos.get("raza", "Mestizo")).strip(),
                        str(datos.get("sexo", "H")).strip()[:1].upper(),
                        "2024-01-01",
                        "Activo",
                    ),
                )
            except Exception:
                pass
            conn.commit()
            cur = conn.execute("SELECT m.*, u.nombre AS propietario_nombre FROM mascotas m JOIN usuarios u ON u.id = m.usuario_id WHERE m.id = ?", (nuevo_id,))
            return dict(cur.fetchone())
        finally:
            self._close_if_file(conn)

    def eliminar_mascota(self, mascota_id: int, usuario_id: Optional[int] = None) -> bool:
        conn = self._get_connection()
        try:
            if usuario_id is not None:
                cur = conn.execute("DELETE FROM mascotas WHERE id = ? AND usuario_id = ?", (mascota_id, usuario_id))
            else:
                cur = conn.execute("DELETE FROM mascotas WHERE id = ?", (mascota_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            self._close_if_file(conn)

    def obtener_disponibilidad_horarios(self, fecha: str) -> Dict[str, Any]:
        horarios_posibles = ["08:30", "10:00", "11:30", "13:00", "15:30", "17:00", "18:30"]
        conn = self._get_connection()
        try:
            cur = conn.execute(
                """
                SELECT hora, COUNT(*) AS ocupados
                FROM citas
                WHERE fecha = ? AND estado != 'cancelada'
                GROUP BY hora
                """,
                (fecha,),
            )
            conteo_por_hora = {}
            for r in cur.fetchall():
                h_str = str(r["hora"])[:5]
                conteo_por_hora[h_str] = int(r["ocupados"])

            disponibilidad = {}
            for h in horarios_posibles:
                ocupados = conteo_por_hora.get(h, 0)
                disponibilidad[h] = {
                    "ocupados": ocupados,
                    "capacidad_maxima": 3,
                    "disponible": ocupados < 3,
                }
            return {
                "fecha": fecha,
                "capacidad_por_turno": 3,
                "horarios": disponibilidad,
            }
        finally:
            self._close_if_file(conn)

    def crear_cita(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            fecha = str(datos["fecha"]).strip()
            hora = str(datos["hora"]).strip()[:5]
            cur_conteo = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM citas
                WHERE fecha = ? AND SUBSTR(hora, 1, 5) = ? AND estado != 'cancelada'
                """,
                (fecha, hora),
            )
            ocupados = cur_conteo.fetchone()["total"]
            if ocupados >= 3:
                raise ValueError(
                    f"El horario de las {hora} para el día {fecha} ya cuenta con sus 3 cupos médicos ocupados (3 doctores en turno). Por favor selecciona otro horario."
                )

            cur = conn.execute(
                """
                INSERT INTO citas (
                    usuario_id, mascota_id, doctor_id, propietario, telefono,
                    mascota_nombre, servicio, fecha, hora, motivo, estado,
                    diagnostico, tratamiento, whatsapp_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datos.get("usuario_id"), datos.get("mascota_id"), datos.get("doctor_id", 2),
                    datos["propietario"], datos["telefono"], datos["mascota_nombre"], datos["servicio"],
                    datos["fecha"], datos["hora"], datos["motivo"], datos.get("estado", "pendiente"),
                    datos.get("diagnostico", ""), datos.get("tratamiento", ""), datos.get("whatsapp_url", ""),
                ),
            )
            cita_id = cur.lastrowid
            conn.commit()
            row = conn.execute("SELECT * FROM citas WHERE id = ?", (cita_id,)).fetchone()
            return dict(row)
        finally:
            self._close_if_file(conn)

    def listar_citas(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            if usuario_id is not None:
                cur = conn.execute("SELECT * FROM citas WHERE usuario_id = ? ORDER BY fecha ASC, hora ASC", (usuario_id,))
            else:
                cur = conn.execute("SELECT * FROM citas ORDER BY fecha ASC, hora ASC")
            return [dict(r) for r in cur.fetchall()]
        finally:
            self._close_if_file(conn)

    def actualizar_cita_doctor(
        self, cita_id: int, estado: str, diagnostico: str, tratamiento: str, doctor_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            conn.execute(
                "UPDATE citas SET estado = ?, diagnostico = ?, tratamiento = ?, doctor_id = COALESCE(?, doctor_id) WHERE id = ?",
                (estado, diagnostico, tratamiento, doctor_id, cita_id),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM citas WHERE id = ?", (cita_id,)).fetchone()
            return dict(row) if row else None
        finally:
            self._close_if_file(conn)

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
        conn = self._get_connection()
        try:
            cur = conn.execute(
                """
                INSERT INTO ventas (numero_boleta, usuario_id, cliente_nombre, cliente_documento, subtotal, igv, total, metodo_pago, estado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cabecera["numero_boleta"], cabecera["usuario_id"], cabecera["cliente_nombre"],
                    cabecera["cliente_documento"], cabecera["subtotal"], cabecera["igv"],
                    cabecera["total"], cabecera.get("metodo_pago", "Tarjeta / Yape"), cabecera.get("estado", "pagado"),
                ),
            )
            venta_id = cur.lastrowid
            for d in detalles:
                conn.execute(
                    "INSERT INTO detalle_ventas (venta_id, producto_id, producto_nombre, cantidad, precio_unitario, subtotal) VALUES (?, ?, ?, ?, ?, ?)",
                    (venta_id, d["producto_id"], d["producto_nombre"], d["cantidad"], d["precio_unitario"], d["subtotal"]),
                )
            conn.commit()
            venta_row = conn.execute("SELECT * FROM ventas WHERE id = ?", (venta_id,)).fetchone()
            detalles_rows = conn.execute("SELECT * FROM detalle_ventas WHERE venta_id = ?", (venta_id,)).fetchall()
            resultado = dict(venta_row)
            resultado["detalles"] = [dict(d) for d in detalles_rows]
            return resultado
        finally:
            self._close_if_file(conn)

    def listar_ventas(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            ventas_rows = conn.execute("SELECT * FROM ventas ORDER BY id DESC").fetchall()
            resultado = []
            for v in ventas_rows:
                v_dict = dict(v)
                d_rows = conn.execute("SELECT * FROM detalle_ventas WHERE venta_id = ?", (v_dict["id"],)).fetchall()
                v_dict["detalles"] = [dict(d) for d in d_rows]
                resultado.append(v_dict)
            return resultado
        finally:
            self._close_if_file(conn)

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
# 4. ADAPTER SUPABASE POSTGRESQL (REST API EN LA NUBE)
# =============================================================================

class SupabasePostgresAdapter(IDatabaseAdapter):
    """
    Adapter concreto para Supabase PostgreSQL en la nube.
    Interactúa mediante la REST API nativa (PostgREST) usando un pool de conexiones HTTP persistente (Keep-Alive).
    """

    _USER_CACHE_TTL = 30.0

    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None) -> None:
        raw_url = supabase_url if supabase_url is not None else os.getenv("SUPABASE_URL", "")
        raw_key = supabase_key if supabase_key is not None else os.getenv("SUPABASE_KEY", "")
        self.supabase_url = raw_url.strip().strip('"').strip("'").rstrip("/")
        self.supabase_key = raw_key.strip().strip('"').strip("'")
        self._configurado = bool(self.supabase_url.startswith("http") and self.supabase_key)
        self.headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._client = httpx.Client(
            timeout=10.0,
            headers=self.headers,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
        self._user_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}
        self._local_sqlite = SQLiteDatabaseAdapter()

    def _url(self, tabla: str) -> str:
        return f"{self.supabase_url}/rest/v1/{tabla}"

    def inicializar_esquema(self) -> None:
        pass

    def _invalidar_cache_usuario(self, usuario_id: int) -> None:
        self._user_cache.pop(int(usuario_id), None)

    def _completar_documento_usuario(self, user: Dict[str, Any]) -> Dict[str, Any]:
        if not user.get("documento") and user.get("id"):
            try:
                resp_v = self._client.get(
                    f"{self._url('ventas')}?usuario_id=eq.{user['id']}&select=cliente_documento&order=id.desc&limit=1"
                )
                if resp_v.status_code == 200 and resp_v.json():
                    doc = resp_v.json()[0].get("cliente_documento")
                    if doc:
                        user["documento"] = doc
                        user["tipo_documento"] = "RUC" if len(doc) == 11 else "DNI"
            except Exception:
                pass
        return user

    def obtener_usuario_por_email(self, email: str) -> Optional[Dict[str, Any]]:
        if not self._configurado:
            return self._local_sqlite.obtener_usuario_por_email(email)
        try:
            resp = self._client.get(f"{self._url('usuarios')}?email=ilike.{email.strip()}&limit=1")
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    user = self._completar_documento_usuario(data[0])
                    if user.get("id"):
                        self._user_cache[int(user["id"])] = (time.monotonic(), dict(user))
                    return user
                return None
        except Exception:
            pass
        return self._local_sqlite.obtener_usuario_por_email(email)

    def crear_usuario(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        if not self._configurado:
            return self._local_sqlite.crear_usuario(datos)
        payload = {
            "nombre": datos["nombre"].strip(),
            "email": datos["email"].strip().lower(),
            "password_hash": hashear_password(str(datos["password_hash"])),
            "rol": datos.get("rol", "cliente"),
            "estado": datos.get("estado", "activo"),
            "telefono": datos.get("telefono", "").strip(),
        }
        try:
            resp = self._client.post(self._url("usuarios"), json=payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                creado = data[0] if isinstance(data, list) and data else payload
                if creado.get("id"):
                    self._user_cache[int(creado["id"])] = (time.monotonic(), dict(creado))
                return creado
        except Exception:
            return self._local_sqlite.crear_usuario(datos)
        raise RuntimeError(f"Error creando usuario en Supabase ({resp.status_code}): {resp.text}")

    def crear_doctor(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        if not self._configurado:
            return self._local_sqlite.crear_doctor(datos)
        payload = {
            "usuario_id": datos.get("usuario_id"),
            "numero_colegiatura": datos.get("cmvp", "CMVP-00000"),
            "nombres": datos.get("nombres", datos.get("nombre", "")),
            "apellidos": datos.get("apellidos", ""),
            "telefono": datos.get("telefono", ""),
            "correo": datos.get("correo", datos.get("email", "")),
            "especialidad": datos.get("especialidad", "Medicina General"),
        }
        try:
            resp = self._client.post(self._url("doctores"), json=payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                return data[0] if isinstance(data, list) and data else payload
        except Exception:
            pass
        return payload

    def obtener_usuario_por_id(self, usuario_id: int) -> Optional[Dict[str, Any]]:
        if not self._configurado:
            return self._local_sqlite.obtener_usuario_por_id(usuario_id)
        uid = int(usuario_id)
        ahora = time.monotonic()
        en_cache = self._user_cache.get(uid)
        if en_cache and (ahora - en_cache[0]) < self._USER_CACHE_TTL:
            return dict(en_cache[1])

        try:
            resp = self._client.get(f"{self._url('usuarios')}?id=eq.{uid}&limit=1")
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    user = self._completar_documento_usuario(data[0])
                    self._user_cache[uid] = (ahora, dict(user))
                    return user
                return None
        except Exception:
            pass
        return self._local_sqlite.obtener_usuario_por_id(usuario_id)

    def actualizar_documento_usuario(self, usuario_id: int, tipo_documento: str, documento: str) -> Optional[Dict[str, Any]]:
        self._invalidar_cache_usuario(usuario_id)
        try:
            self._client.patch(
                f"{self._url('usuarios')}?id=eq.{usuario_id}",
                json={"tipo_documento": tipo_documento, "documento": documento},
            )
        except Exception:
            pass
        user = self.obtener_usuario_por_id(usuario_id)
        if user:
            user["tipo_documento"] = tipo_documento
            user["documento"] = documento
            self._user_cache[int(usuario_id)] = (time.monotonic(), dict(user))
        return user

    def listar_usuarios(self) -> List[Dict[str, Any]]:
        if not self._configurado:
            return self._local_sqlite.listar_usuarios()
        try:
            resp = self._client.get(
                f"{self._url('usuarios')}?select=id,nombre,email,rol,estado,telefono,creado_en&order=id.asc"
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return self._local_sqlite.listar_usuarios()

    def actualizar_estado_usuario(self, usuario_id: int, nuevo_estado: str) -> Optional[Dict[str, Any]]:
        self._invalidar_cache_usuario(usuario_id)
        if not self._configurado:
            return self._local_sqlite.actualizar_estado_usuario(usuario_id, nuevo_estado)
        try:
            resp = self._client.patch(
                f"{self._url('usuarios')}?id=eq.{usuario_id}",
                json={"estado": nuevo_estado},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data[0] if data else None
        except Exception:
            pass
        return self._local_sqlite.actualizar_estado_usuario(usuario_id, nuevo_estado)

    def listar_mascotas(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self._configurado:
            return self._local_sqlite.listar_mascotas(usuario_id)
        query = f"{self._url('mascotas')}?select=*&order=id.asc"
        if usuario_id is not None:
            query += f"&usuario_id=eq.{usuario_id}"
        try:
            resp = self._client.get(query)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return self._local_sqlite.listar_mascotas(usuario_id)

    def crear_mascota(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        if not self._configurado:
            return self._local_sqlite.crear_mascota(datos)
        payload = {
            "usuario_id": int(datos["usuario_id"]),
            "nombre": str(datos["nombre"]).strip(),
            "especie": str(datos.get("especie", "Perro")).strip(),
            "raza": str(datos.get("raza", "Mestizo")).strip(),
            "edad": int(datos.get("edad", 1)),
            "peso_kg": float(datos.get("peso_kg", 5.0)),
            "historial_resumen": str(datos.get("historial_resumen", "")).strip(),
        }
        try:
            resp = self._client.post(self._url("mascotas"), json=payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                return data[0] if isinstance(data, list) and data else payload
        except Exception:
            return self._local_sqlite.crear_mascota(datos)
        raise RuntimeError(f"Error creando mascota en Supabase ({resp.status_code}): {resp.text}")

    def eliminar_mascota(self, mascota_id: int, usuario_id: Optional[int] = None) -> bool:
        if not self._configurado:
            return self._local_sqlite.eliminar_mascota(mascota_id, usuario_id)
        query = f"{self._url('mascotas')}?id=eq.{mascota_id}"
        if usuario_id is not None:
            query += f"&usuario_id=eq.{usuario_id}"
        try:
            resp = self._client.delete(query)
            return resp.status_code in (200, 204)
        except Exception:
            return self._local_sqlite.eliminar_mascota(mascota_id, usuario_id)

    def obtener_disponibilidad_horarios(self, fecha: str) -> Dict[str, Any]:
        if not self._configurado:
            return self._local_sqlite.obtener_disponibilidad_horarios(fecha)
        horarios_posibles = ["08:30", "10:00", "11:30", "13:00", "15:30", "17:00", "18:30"]
        query = f"{self._url('citas')}?fecha=eq.{fecha}&estado=neq.cancelada&select=hora"
        conteo_por_hora: Dict[str, int] = {}
        try:
            resp = self._client.get(query)
            if resp.status_code == 200:
                for c in resp.json():
                    h_str = str(c.get("hora", ""))[:5]
                    conteo_por_hora[h_str] = conteo_por_hora.get(h_str, 0) + 1
        except Exception:
            return self._local_sqlite.obtener_disponibilidad_horarios(fecha)

        disponibilidad = {}
        for h in horarios_posibles:
            ocupados = conteo_por_hora.get(h, 0)
            disponibilidad[h] = {
                "ocupados": ocupados,
                "capacidad_maxima": 3,
                "disponible": ocupados < 3,
            }
        return {
            "fecha": fecha,
            "capacidad_por_turno": 3,
            "horarios": disponibilidad,
        }

    def crear_cita(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        if not self._configurado:
            return self._local_sqlite.crear_cita(datos)
        fecha = str(datos["fecha"]).strip()
        hora = str(datos["hora"]).strip()[:5]

        # Validación de cupo máximo de 3 doctores por turno
        query_check = f"{self._url('citas')}?fecha=eq.{fecha}&estado=neq.cancelada&select=hora"
        try:
            resp_check = self._client.get(query_check)
            if resp_check.status_code == 200:
                citas_existentes = resp_check.json()
                ocupados = sum(1 for c in citas_existentes if str(c.get("hora", ""))[:5] == hora)
                if ocupados >= 3:
                    raise ValueError(
                        f"El horario de las {hora} para el día {fecha} ya cuenta con sus 3 cupos médicos ocupados (3 doctores en turno). Por favor selecciona otro horario."
                    )
        except ValueError:
            raise
        except Exception:
            pass

        payload = {
            "usuario_id": datos.get("usuario_id"),
            "mascota_id": datos.get("mascota_id"),
            "doctor_id": datos.get("doctor_id", 2),
            "propietario": datos["propietario"],
            "telefono": datos["telefono"],
            "mascota_nombre": datos["mascota_nombre"],
            "servicio": datos["servicio"],
            "fecha": datos["fecha"],
            "hora": datos["hora"],
            "motivo": datos["motivo"],
            "estado": datos.get("estado", "pendiente"),
            "diagnostico": datos.get("diagnostico", ""),
            "tratamiento": datos.get("tratamiento", ""),
            "whatsapp_url": datos.get("whatsapp_url", ""),
        }
        try:
            resp = self._client.post(self._url("citas"), json=payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                return data[0] if data else payload
        except Exception:
            return self._local_sqlite.crear_cita(datos)
        raise ValueError(f"No se pudo registrar la cita médica en la base de datos: {resp.text}")

    def listar_citas(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self._configurado:
            return self._local_sqlite.listar_citas(usuario_id)
        query = f"{self._url('citas')}?select=*&order=fecha.asc,hora.asc"
        if usuario_id is not None:
            query += f"&usuario_id=eq.{usuario_id}"
        try:
            resp = self._client.get(query)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return self._local_sqlite.listar_citas(usuario_id)

    def actualizar_cita_doctor(
        self, cita_id: int, estado: str, diagnostico: str, tratamiento: str, doctor_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        if not self._configurado:
            return self._local_sqlite.actualizar_cita_doctor(cita_id, estado, diagnostico, tratamiento, doctor_id)
        payload = {
            "estado": estado,
            "diagnostico": diagnostico,
            "tratamiento": tratamiento,
        }
        if doctor_id is not None:
            payload["doctor_id"] = doctor_id

        try:
            resp = self._client.patch(f"{self._url('citas')}?id=eq.{cita_id}", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data[0] if data else None
        except Exception:
            pass
        return self._local_sqlite.actualizar_cita_doctor(cita_id, estado, diagnostico, tratamiento, doctor_id)

    def listar_productos(self, solo_activos: bool = True) -> List[Dict[str, Any]]:
        if not self._configurado:
            return self._local_sqlite.listar_productos(solo_activos)
        query = f"{self._url('productos')}?select=*&order=id.asc"
        if solo_activos:
            query += "&activo=eq.true"
        try:
            resp = self._client.get(query)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return self._local_sqlite.listar_productos(solo_activos)

    def obtener_producto(self, producto_id: int) -> Optional[Dict[str, Any]]:
        if not self._configurado:
            return self._local_sqlite.obtener_producto(producto_id)
        try:
            resp = self._client.get(f"{self._url('productos')}?id=eq.{producto_id}&limit=1")
            if resp.status_code == 200:
                data = resp.json()
                return data[0] if data else None
        except Exception:
            pass
        return self._local_sqlite.obtener_producto(producto_id)

    def descontar_stock_producto(self, producto_id: int, cantidad: int) -> bool:
        if not self._configurado:
            return self._local_sqlite.descontar_stock_producto(producto_id, cantidad)
        prod = self.obtener_producto(producto_id)
        if not prod or prod.get("stock", 0) < cantidad:
            return False
        nuevo_stock = prod["stock"] - cantidad
        try:
            resp = self._client.patch(
                f"{self._url('productos')}?id=eq.{producto_id}",
                json={"stock": nuevo_stock},
            )
            return resp.status_code == 200
        except Exception:
            return self._local_sqlite.descontar_stock_producto(producto_id, cantidad)

    def registrar_venta_y_detalles(self, cabecera: Dict[str, Any], detalles: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self._configurado:
            return self._local_sqlite.registrar_venta_y_detalles(cabecera, detalles)
        payload_venta = {
            "numero_boleta": cabecera["numero_boleta"],
            "usuario_id": cabecera["usuario_id"],
            "cliente_nombre": cabecera["cliente_nombre"],
            "cliente_documento": cabecera["cliente_documento"],
            "subtotal": cabecera["subtotal"],
            "igv": cabecera["igv"],
            "total": cabecera["total"],
            "metodo_pago": cabecera.get("metodo_pago", "Tarjeta / Yape"),
            "estado": cabecera.get("estado", "pagado"),
        }
        try:
            resp_v = self._client.post(self._url("ventas"), json=payload_venta)
            if resp_v.status_code not in (200, 201):
                raise RuntimeError(f"Error al registrar venta en Supabase: {resp_v.text}")
            venta_creada = resp_v.json()[0]
            venta_id = venta_creada["id"]

            items_payload = []
            for d in detalles:
                items_payload.append({
                    "venta_id": venta_id,
                    "producto_id": d["producto_id"],
                    "producto_nombre": d["producto_nombre"],
                    "cantidad": d["cantidad"],
                    "precio_unitario": d["precio_unitario"],
                    "subtotal": d["subtotal"],
                })

            resp_d = self._client.post(self._url("detalle_ventas"), json=items_payload)
            detalles_creados = resp_d.json() if resp_d.status_code in (200, 201) else []
            venta_creada["detalles"] = detalles_creados
            return venta_creada
        except Exception:
            return self._local_sqlite.registrar_venta_y_detalles(cabecera, detalles)

    def listar_ventas(self) -> List[Dict[str, Any]]:
        if not self._configurado:
            return self._local_sqlite.listar_ventas()
        try:
            resp_v = self._client.get(f"{self._url('ventas')}?select=*&order=id.desc")
            if resp_v.status_code != 200:
                return []
            ventas = resp_v.json()

            resp_d = self._client.get(f"{self._url('detalle_ventas')}?select=*&order=id.asc")
            todos_detalles = resp_d.json() if resp_d.status_code == 200 else []

            detalles_por_venta: Dict[int, List[Dict[str, Any]]] = {}
            for d in todos_detalles:
                detalles_por_venta.setdefault(d["venta_id"], []).append(d)

            for v in ventas:
                v["detalles"] = detalles_por_venta.get(v["id"], [])
            return ventas
        except Exception:
            return self._local_sqlite.listar_ventas()

    def obtener_todas_las_16_tablas(self) -> Dict[str, List[Dict[str, Any]]]:
        if not self._configurado:
            return self._local_sqlite.obtener_todas_las_16_tablas()
        tablas_principales = ["usuarios", "mascotas", "citas", "productos", "ventas", "detalle_ventas"]
        resultado: Dict[str, List[Dict[str, Any]]] = {}
        try:
            for t in tablas_principales:
                resp = self._client.get(f"{self._url(t)}?select=*&limit=50")
                resultado[t] = resp.json() if resp.status_code == 200 else []
            return resultado
        except Exception:
            return self._local_sqlite.obtener_todas_las_16_tablas()

    def cambiar_password_usuario(self, usuario_id: int, password_actual: str, password_nueva: str) -> bool:
        self._invalidar_cache_usuario(usuario_id)
        if not self._configurado:
            return self._local_sqlite.cambiar_password_usuario(usuario_id, password_actual, password_nueva)
        user = self.obtener_usuario_por_id(usuario_id)
        if not user or not verificar_password(password_actual, str(user.get("password_hash", ""))):
            raise ValueError("La contraseña actual no es correcta.")
        try:
            resp = self._client.patch(
                f"{self._url('usuarios')}?id=eq.{usuario_id}",
                json={"password_hash": hashear_password(password_nueva)},
            )
            self._invalidar_cache_usuario(usuario_id)
            return resp.status_code in (200, 204)
        except Exception:
            return self._local_sqlite.cambiar_password_usuario(usuario_id, password_actual, password_nueva)

    def listar_compras_usuario(self, usuario_id: int) -> List[Dict[str, Any]]:
        if not self._configurado:
            return self._local_sqlite.listar_compras_usuario(usuario_id)
        try:
            resp_v = self._client.get(
                f"{self._url('ventas')}?usuario_id=eq.{usuario_id}&select=*&order=id.desc"
            )
            if resp_v.status_code != 200:
                return []
            ventas = resp_v.json()
            resp_d = self._client.get(f"{self._url('detalle_ventas')}?select=*&order=id.asc")
            todos_detalles = resp_d.json() if resp_d.status_code == 200 else []
            detalles_por_venta: Dict[int, List[Dict[str, Any]]] = {}
            for d in todos_detalles:
                detalles_por_venta.setdefault(d["venta_id"], []).append(d)
            for v in ventas:
                v["detalles"] = detalles_por_venta.get(v["id"], [])
            return ventas
        except Exception:
            return self._local_sqlite.listar_compras_usuario(usuario_id)

    def crear_solicitud_mascota(
        self, usuario_id: int, mascota_id: int, tipo: str, motivo: str, datos_nuevos: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return self._local_sqlite.crear_solicitud_mascota(usuario_id, mascota_id, tipo, motivo, datos_nuevos)

    def listar_solicitudes_mascota(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        return self._local_sqlite.listar_solicitudes_mascota(usuario_id)

    def resolver_solicitud_mascota(self, solicitud_id: int, accion: str) -> Dict[str, Any]:
        sol = self._local_sqlite.resolver_solicitud_mascota(solicitud_id, accion)
        if accion.lower() == "aprobar":
            if sol["tipo"] == "eliminar":
                self.eliminar_mascota(sol["mascota_id"])
            elif sol["tipo"] == "editar" and sol.get("datos_nuevos"):
                nuevos = sol["datos_nuevos"]
                try:
                    self._client.patch(
                        f"{self._url('mascotas')}?id=eq.{sol['mascota_id']}",
                        json={
                            "nombre": nuevos.get("nombre"),
                            "especie": nuevos.get("especie"),
                            "raza": nuevos.get("raza"),
                            "edad": int(nuevos.get("edad", 1)),
                            "peso_kg": float(nuevos.get("peso_kg", 5.0)),
                            "historial_resumen": nuevos.get("historial_resumen"),
                        },
                    )
                except Exception:
                    pass
        return sol


# =============================================================================
# 5. FÁBRICA DE ADAPTADORES (FACTORY METHOD)
# =============================================================================

def obtener_adaptador_bd() -> IDatabaseAdapter:
    """Fábrica que devuelve el Adapter de Base de Datos SQLite unificado (16 tablas)."""
    db_path = os.getenv("SQLITE_PATH")
    if db_path:
        base_dir = Path(__file__).resolve().parent.parent.parent
        full_path = base_dir / db_path if not Path(db_path).is_absolute() else Path(db_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return SQLiteDatabaseAdapter(str(full_path))
    return SQLiteDatabaseAdapter()
