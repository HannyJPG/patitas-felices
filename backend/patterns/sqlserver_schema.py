"""
Motor de conexión ODBC y esquema en Tercera Forma Normal (3FN - 16 tablas)
para Microsoft SQL Server (PatitasFelices_DB).
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import queue
import threading
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("patitas_felices.sqlserver")

_SCHEMA_SQL_FILE = Path(__file__).resolve().parents[2] / "database" / "schema_sqlserver.sql"

NOMBRES_16_TABLAS: list[str] = [
    "Dueno",
    "Especie",
    "Razas",
    "Paciente",
    "Especialidad",
    "Veterinario",
    "Servicios",
    "Cita",
    "Detalle_servicios",
    "Historial_clinico",
    "Receta",
    "Factura",
    "Pago",
    "usuarios",
    "productos",
    "detalle_ventas",
]


class ErrorConexionSQLServer(RuntimeError):
    """Excepción lanzada cuando Microsoft SQL Server no está disponible o falla la conexión."""


class ErrorRegistroDuplicadoSQLServer(ValueError):
    """Excepción lanzada cuando SQL Server rechaza un registro por restricción UNIQUE (2627/2601)."""


class ErrorConsultaSQLServer(RuntimeError):
    """Excepción lanzada cuando ocurre un error de ejecución en una sentencia T-SQL."""

    def __init__(self, message: str, native_err: int = 0, sqlstate: str = "") -> None:
        super().__init__(message)
        self.native_err = native_err
        self.sqlstate = sqlstate


def sql_lit(val: Any) -> str:
    """Formatea un valor de Python como literal seguro T-SQL para Microsoft SQL Server."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, (int, float)):
        return str(val)
    text = str(val).replace("'", "''")
    return f"N'{text}'"


def _sql_param_type(val: Any) -> str:
    """Determina la declaración de tipo T-SQL para parámetros de sys.sp_executesql."""
    if isinstance(val, bool):
        return "BIT"
    if isinstance(val, int):
        return "INT"
    if isinstance(val, float):
        return "FLOAT"
    return "NVARCHAR(MAX)"


def build_parametrized_batch(sql: str, params: Optional[dict[str, Any]] = None) -> str:
    """
    Envuelve una consulta T-SQL con parámetros nombrados (@param) dentro de sys.sp_executesql
    para garantizar ejecución parametrizada nativa en SQL Server y prevenir SQL Injection.
    """
    if not params:
        return sql
    decls: list[str] = []
    assigns: list[str] = []
    for key, val in params.items():
        clean_key = key.lstrip("@")
        decls.append(f"@{clean_key} {_sql_param_type(val)}")
        assigns.append(f"@{clean_key} = {sql_lit(val)}")
    stmt_lit = sql_lit(sql)
    params_lit = sql_lit(", ".join(decls))
    assigns_sql = ", ".join(assigns)
    return f"EXEC sys.sp_executesql @stmt = {stmt_lit}, @params = {params_lit}, {assigns_sql};"


def _extract_odbc_diag(odbc: Any, handle_type: int, handle: Any) -> tuple[str, int, str]:
    """Obtiene el SQLSTATE y código de error nativo desde el administrador ODBC sin exponer credenciales."""
    sqlstate_buf = ctypes.create_unicode_buffer(6)
    native_err = ctypes.c_int(0)
    msg_buf = ctypes.create_unicode_buffer(1024)
    msg_len = ctypes.c_short(0)
    rc = odbc.SQLGetDiagRecW(
        handle_type,
        handle,
        1,
        sqlstate_buf,
        ctypes.byref(native_err),
        msg_buf,
        1024,
        ctypes.byref(msg_len),
    )
    if rc in (0, 1):
        return sqlstate_buf.value, int(native_err.value), msg_buf.value
    return "", 0, ""


class SQLServerConnection:
    """Conexión nativa con pool thread-safe a Microsoft SQL Server mediante ODBC de Windows (odbc32.dll)."""

    def __init__(
        self,
        server: str = "localhost",
        database: str = "PatitasFelices_DB",
        driver: Optional[str] = None,
        pool_size: Optional[int] = None,
    ) -> None:
        self.server = server.strip() or "localhost"
        self.database = database.strip() or "PatitasFelices_DB"
        self.driver = (driver or os.getenv("SQLSERVER_DRIVER", "ODBC Driver 17 for SQL Server")).strip()
        raw_pool = pool_size if pool_size is not None else int(os.getenv("SQLSERVER_POOL_SIZE", "8"))
        self.pool_size = max(1, int(raw_pool))
        self._lock = threading.RLock()
        self._pool_lock = threading.Lock()
        self._pool: queue.LifoQueue[tuple[Any, Any, Any]] = queue.LifoQueue(maxsize=self.pool_size)
        self._active_handles = 0
        self._epoch = 0

    def _build_conn_str(self, target_db: str) -> str:
        sql_user = os.getenv("SQLSERVER_USER", "").strip()
        sql_pass = os.getenv("SQLSERVER_PASSWORD", "").strip()
        if sql_user and sql_pass:
            return (
                f"Driver={{{self.driver}}};Server={self.server};Database={target_db};"
                f"UID={sql_user};PWD={sql_pass};TrustServerCertificate=yes;"
            )
        return (
            f"Driver={{{self.driver}}};Server={self.server};Database={target_db};"
            "Trusted_Connection=yes;TrustServerCertificate=yes;"
        )

    def _connect(self, db_override: Optional[str] = None) -> tuple[Any, Any, Any]:
        odbc = ctypes.windll.odbc32
        henv = ctypes.c_void_p()
        hdbc = ctypes.c_void_p()
        if odbc.SQLAllocHandle(1, None, ctypes.byref(henv)) not in (0, 1):
            raise ErrorConexionSQLServer(
                "No se pudo inicializar el entorno ODBC para conectar con SQL Server."
            )
        odbc.SQLSetEnvAttr(henv, 200, 3, 0)
        if odbc.SQLAllocHandle(2, henv, ctypes.byref(hdbc)) not in (0, 1):
            odbc.SQLFreeHandle(1, henv)
            raise ErrorConexionSQLServer(
                "No se pudo reservar el manejador de conexión ODBC para SQL Server."
            )

        # Tiempo máximo de espera de conexión: 3 segundos (SQL_ATTR_LOGIN_TIMEOUT = 103)
        odbc.SQLSetConnectAttrW(hdbc, 103, ctypes.c_void_p(3), 0)

        target_db = db_override or self.database
        conn_str = self._build_conn_str(target_db)
        out_buf = ctypes.create_unicode_buffer(1024)
        out_len = ctypes.c_short()
        rc = odbc.SQLDriverConnectW(
            hdbc, None, conn_str, len(conn_str), out_buf, 1024, ctypes.byref(out_len), 0
        )
        if rc not in (0, 1):
            sqlstate, native_err, _ = _extract_odbc_diag(odbc, 2, hdbc)
            odbc.SQLFreeHandle(2, hdbc)
            odbc.SQLFreeHandle(1, henv)
            raise ErrorConexionSQLServer(
                "No se pudo conectar con Microsoft SQL Server. Verifique que el servicio de base de datos esté activo y disponible "
                f"(SQLSTATE {sqlstate or 'N/A'}, código {native_err})."
            )
        return odbc, henv, hdbc

    @staticmethod
    def _close_handle(handle: tuple[Any, Any, Any]) -> None:
        odbc, henv, hdbc = handle
        try:
            odbc.SQLDisconnect(hdbc)
        except Exception:
            logger.debug("Error al desconectar handle ODBC.", exc_info=True)
        try:
            odbc.SQLFreeHandle(2, hdbc)
        except Exception:
            logger.debug("Error al liberar HDBC.", exc_info=True)
        try:
            odbc.SQLFreeHandle(1, henv)
        except Exception:
            logger.debug("Error al liberar HENV.", exc_info=True)

    def _acquire_handle(self) -> tuple[tuple[Any, Any, Any], int]:
        while True:
            try:
                handle = self._pool.get_nowait()
                with self._pool_lock:
                    return handle, self._epoch
            except queue.Empty:
                pass

            crear_nueva = False
            with self._pool_lock:
                epoch_actual = self._epoch
                if self._active_handles < self.pool_size:
                    self._active_handles += 1
                    crear_nueva = True

            if crear_nueva:
                try:
                    handle = self._connect()
                    return handle, epoch_actual
                except Exception:
                    with self._pool_lock:
                        self._active_handles = max(0, self._active_handles - 1)
                    raise

            try:
                handle = self._pool.get(timeout=30.0)
                with self._pool_lock:
                    return handle, self._epoch
            except queue.Empty as exc:
                raise ErrorConexionSQLServer(
                    "Tiempo de espera agotado esperando una conexión libre del pool de SQL Server."
                ) from exc

    def _release_handle(
        self, handle: tuple[Any, Any, Any], epoch: int, broken: bool = False
    ) -> None:
        devolver = False
        if not broken:
            with self._pool_lock:
                if epoch == self._epoch and not self._pool.full():
                    try:
                        self._pool.put_nowait(handle)
                        devolver = True
                    except queue.Full:
                        devolver = False
        if not devolver:
            self._close_handle(handle)
            with self._pool_lock:
                if epoch == self._epoch:
                    self._active_handles = max(0, self._active_handles - 1)

    def close(self) -> None:
        drenados: list[tuple[Any, Any, Any]] = []
        with self._pool_lock:
            self._epoch += 1
            self._active_handles = 0
            while True:
                try:
                    drenados.append(self._pool.get_nowait())
                except queue.Empty:
                    break
        for handle in drenados:
            self._close_handle(handle)

    def _handle_stmt_error(self, odbc: Any, hstmt: Any, raise_on_error: bool) -> bool:
        sqlstate, native_err, msg = _extract_odbc_diag(odbc, 3, hstmt)
        if sqlstate.startswith("08") or sqlstate in ("HYT00", "HYT01"):
            raise ErrorConexionSQLServer(
                "Se perdió la conexión con Microsoft SQL Server. Verifique que el servidor de base de datos esté en ejecución."
            )
        if native_err in (2627, 2601) or sqlstate == "23000":
            if native_err in (2627, 2601):
                raise ErrorRegistroDuplicadoSQLServer(
                    "Ya existe un registro con ese dato único (correo electrónico o documento) en SQL Server."
                )
        if raise_on_error:
            detalle = f": {msg.strip()}" if msg and msg.strip() else ""
            raise ErrorConsultaSQLServer(
                f"Error de base de datos en SQL Server (SQLSTATE {sqlstate or 'N/A'}, código {native_err}){detalle}",
                native_err=native_err,
                sqlstate=sqlstate,
            )
        return False

    def scalar(
        self,
        sql: str,
        params: Optional[dict[str, Any]] = None,
        raise_on_error: bool = True,
    ) -> str:
        """Ejecuta una consulta T-SQL (opcionalmente parametrizada) y devuelve el primer valor escalar."""
        stmt_sql = build_parametrized_batch(sql, params)
        full_sql = "SET NOCOUNT ON;\n" + stmt_sql

        for attempt in range(2):
            handle, epoch = self._acquire_handle()
            odbc, _, hdbc = handle
            broken = False
            hstmt = ctypes.c_void_p()
            if odbc.SQLAllocHandle(3, hdbc, ctypes.byref(hstmt)) not in (0, 1):
                self._release_handle(handle, epoch, broken=True)
                if attempt == 0:
                    continue
                raise ErrorConexionSQLServer(
                    "No se pudo preparar la consulta en Microsoft SQL Server."
                )
            try:
                rc = odbc.SQLExecDirectW(hstmt, full_sql, len(full_sql))
                if rc not in (0, 1, 100):
                    sqlstate, _, _ = _extract_odbc_diag(odbc, 3, hstmt)
                    if sqlstate.startswith("08"):
                        broken = True
                    if attempt == 0 and sqlstate.startswith("08"):
                        continue
                    self._handle_stmt_error(odbc, hstmt, raise_on_error=raise_on_error)
                    return ""
                chunks: list[str] = []
                while True:
                    while odbc.SQLFetch(hstmt) in (0, 1):
                        while True:
                            buf = ctypes.create_unicode_buffer(65536)
                            ind = ctypes.c_ssize_t()
                            rc_data = odbc.SQLGetData(hstmt, 1, -8, buf, 65536 * 2, ctypes.byref(ind))
                            if rc_data not in (0, 1) or ind.value in (-1, 0):
                                break
                            if buf.value:
                                chunks.append(buf.value)
                            if rc_data == 0:
                                break
                    if chunks:
                        break
                    rc_more = odbc.SQLMoreResults(hstmt)
                    if rc_more == 100:
                        break
                    if rc_more not in (0, 1):
                        sqlstate_more, _, _ = _extract_odbc_diag(odbc, 3, hstmt)
                        if sqlstate_more.startswith("08"):
                            broken = True
                        self._handle_stmt_error(odbc, hstmt, raise_on_error=raise_on_error)
                        return ""
                return "".join(chunks)
            except ErrorConexionSQLServer:
                broken = True
                raise
            finally:
                odbc.SQLFreeHandle(3, hstmt)
                self._release_handle(handle, epoch, broken=broken)
        return ""

    def execute(
        self,
        sql: str,
        params: Optional[dict[str, Any]] = None,
        raise_on_error: bool = True,
    ) -> bool:
        """Ejecuta una sentencia o lote DML/DDL (opcionalmente parametrizado) en SQL Server."""
        stmt_sql = build_parametrized_batch(sql, params)
        full_sql = "SET NOCOUNT ON;\n" + stmt_sql

        for attempt in range(2):
            handle, epoch = self._acquire_handle()
            odbc, _, hdbc = handle
            broken = False
            hstmt = ctypes.c_void_p()
            if odbc.SQLAllocHandle(3, hdbc, ctypes.byref(hstmt)) not in (0, 1):
                self._release_handle(handle, epoch, broken=True)
                if attempt == 0:
                    continue
                raise ErrorConexionSQLServer(
                    "No se pudo preparar la sentencia en Microsoft SQL Server."
                )
            try:
                rc = odbc.SQLExecDirectW(hstmt, full_sql, len(full_sql))
                if rc not in (0, 1, 100):
                    sqlstate, _, _ = _extract_odbc_diag(odbc, 3, hstmt)
                    if sqlstate.startswith("08"):
                        broken = True
                    if attempt == 0 and sqlstate.startswith("08"):
                        continue
                    self._handle_stmt_error(odbc, hstmt, raise_on_error=raise_on_error)
                    return False
                while True:
                    rc_more = odbc.SQLMoreResults(hstmt)
                    if rc_more == 100:
                        break
                    if rc_more not in (0, 1):
                        sqlstate_more, _, _ = _extract_odbc_diag(odbc, 3, hstmt)
                        if sqlstate_more.startswith("08"):
                            broken = True
                        self._handle_stmt_error(odbc, hstmt, raise_on_error=raise_on_error)
                        return False
                return True
            except ErrorConexionSQLServer:
                broken = True
                raise
            finally:
                odbc.SQLFreeHandle(3, hstmt)
                self._release_handle(handle, epoch, broken=broken)
        return False

    def query_json(
        self,
        select_sql: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Ejecuta un SELECT en SQL Server serializando las filas con FOR JSON PATH."""
        clean_sql = select_sql.strip().rstrip(";")
        wrapped = f"SELECT ({clean_sql} FOR JSON PATH, INCLUDE_NULL_VALUES) AS j"
        raw = self.scalar(wrapped, params=params, raise_on_error=True)
        if not raw:
            return []
        data = json.loads(raw)
        return data if isinstance(data, list) else []

    def query_one(
        self,
        select_sql: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        rows = self.query_json(select_sql, params=params)
        return rows[0] if rows else None

    def ensure_database_exists(self) -> None:
        """Garantiza que la base de datos exista en la instancia de SQL Server."""
        with self._lock:
            odbc, henv, hdbc = self._connect(db_override="master")
            hstmt = ctypes.c_void_p()
            if odbc.SQLAllocHandle(3, hdbc, ctypes.byref(hstmt)) not in (0, 1):
                odbc.SQLDisconnect(hdbc)
                odbc.SQLFreeHandle(2, hdbc)
                odbc.SQLFreeHandle(1, henv)
                raise ErrorConexionSQLServer(
                    "No se pudo preparar la verificación de base de datos en Microsoft SQL Server."
                )
            try:
                db_lit = self.database.replace("'", "''")
                db_ident = self.database.replace("]", "]]")
                sql = f"IF DB_ID(N'{db_lit}') IS NULL CREATE DATABASE [{db_ident}];"
                rc = odbc.SQLExecDirectW(hstmt, sql, len(sql))
                if rc not in (0, 1, 100):
                    self._handle_stmt_error(odbc, hstmt, raise_on_error=True)
            finally:
                odbc.SQLFreeHandle(3, hstmt)
                odbc.SQLDisconnect(hdbc)
                odbc.SQLFreeHandle(2, hdbc)
                odbc.SQLFreeHandle(1, henv)


def ensure_sqlserver_schema(
    conn: SQLServerConnection,
    hash_password: Callable[[str], str],
    reset_tables: bool = False,
    include_demo_users: bool = False,
) -> None:
    """
    Inicializa las 16 tablas canónicas en 3FN en Microsoft SQL Server desde database/schema_sqlserver.sql
    y garantiza los datos semilla iniciales.
    """
    conn.ensure_database_exists()

    tablas_in = ", ".join(sql_lit(t) for t in NOMBRES_16_TABLAS)
    existing_count_str = conn.scalar(
        f"SELECT CAST(COUNT(*) AS VARCHAR(10)) FROM sys.tables WHERE is_ms_shipped = 0 AND name IN ({tablas_in})"
    )
    existing_count = int(existing_count_str) if existing_count_str.isdigit() else 0

    if existing_count < len(NOMBRES_16_TABLAS) and _SCHEMA_SQL_FILE.is_file():
        raw_ddl = _SCHEMA_SQL_FILE.read_text(encoding="utf-8")
        for batch in raw_ddl.split("\nGO"):
            clean = batch.strip()
            if not clean:
                continue
            if "CREATE DATABASE" in clean or "USE [PatitasFelices_DB]" in clean:
                continue
            conn.execute(clean, raise_on_error=True)

    if reset_tables and conn.database.strip().lower() == "patitasfelices_db":
        raise RuntimeError(
            "Operación bloqueada por seguridad: reset_tables=True está estrictamente prohibido sobre la base de datos de producción PatitasFelices_DB."
        )

    if reset_tables:
        conn.execute(
            """
            DELETE FROM dbo.detalle_ventas;
            DELETE FROM dbo.Pago;
            DELETE FROM dbo.Factura;
            DELETE FROM dbo.Receta;
            DELETE FROM dbo.Historial_clinico;
            DELETE FROM dbo.Detalle_servicios;
            DELETE FROM dbo.Cita;
            DELETE FROM dbo.Paciente;
            DELETE FROM dbo.Veterinario;
            DELETE FROM dbo.Especialidad;
            DELETE FROM dbo.Razas;
            DELETE FROM dbo.Especie;
            DELETE FROM dbo.Dueno;
            DELETE FROM dbo.Servicios;
            DELETE FROM dbo.productos;
            DELETE FROM dbo.usuarios;
            """
        )

    aplicar_migraciones_versionadas(conn)
    seed_sqlserver(conn, hash_password, include_demo_users=include_demo_users)


SCHEMA_VERSION_PROPERTY = "patitas_schema_version"

MIGRACIONES_SQLSERVER: list[tuple[str, str, list[str]]] = [
    (
        "2026.11.12.01",
        "Índices de rendimiento sargables en Cita, Factura y Paciente",
        [
            """
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = N'IX_Cita_Fecha_Estado' AND object_id = OBJECT_ID(N'dbo.Cita')
            )
            CREATE INDEX IX_Cita_Fecha_Estado
                ON dbo.Cita (fecha, estado) INCLUDE (Id_veterinario, hora);
            """,
            """
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = N'IX_Factura_Cita_IdFactura' AND object_id = OBJECT_ID(N'dbo.Factura')
            )
            CREATE INDEX IX_Factura_Cita_IdFactura
                ON dbo.Factura (Id_cita, id_factura DESC) INCLUDE (id_dueno, serie, numero, total, fecha_emision);
            """,
            """
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = N'IX_Paciente_Dueno_Estado' AND object_id = OBJECT_ID(N'dbo.Paciente')
            )
            CREATE INDEX IX_Paciente_Dueno_Estado
                ON dbo.Paciente (id_dueno, estado);
            """,
        ],
    ),
]


def obtener_version_esquema(conn: SQLServerConnection) -> Optional[str]:
    """Lee la versión de esquema registrada en sys.extended_properties sin crear tablas adicionales."""
    valor = conn.scalar(
        """
        SELECT TOP 1 CAST(value AS NVARCHAR(64))
        FROM sys.extended_properties
        WHERE class = 0 AND name = CAST(@prop AS NVARCHAR(128))
        """,
        params={"prop": SCHEMA_VERSION_PROPERTY},
        raise_on_error=False,
    )
    limpio = str(valor or "").strip()
    return limpio or None


def establecer_version_esquema(conn: SQLServerConnection, version: str) -> None:
    """Registra o actualiza la propiedad extendida patitas_schema_version en la base actual."""
    conn.execute(
        """
        DECLARE @pname SYSNAME = CAST(@prop AS NVARCHAR(128));
        DECLARE @val SQL_VARIANT = CAST(@ver AS NVARCHAR(64));
        IF EXISTS (SELECT 1 FROM sys.extended_properties WHERE class = 0 AND name = @pname)
            EXEC sys.sp_updateextendedproperty @name = @pname, @value = @val;
        ELSE
            EXEC sys.sp_addextendedproperty @name = @pname, @value = @val;
        """,
        params={"prop": SCHEMA_VERSION_PROPERTY, "ver": version},
        raise_on_error=True,
    )


def aplicar_migraciones_versionadas(conn: SQLServerConnection) -> Optional[str]:
    """Ejecuta migraciones idempotentes pendientes usando sys.extended_properties como bitácora."""
    version_actual = obtener_version_esquema(conn)
    for version, descripcion, sentencias in MIGRACIONES_SQLSERVER:
        if version_actual is not None and version <= version_actual:
            continue
        for sql in sentencias:
            conn.execute(sql, raise_on_error=True)
        establecer_version_esquema(conn, version)
        logger.info("Migración SQL Server aplicada (%s): %s", version, descripcion)
        version_actual = version
    return version_actual


def seed_sqlserver(
    conn: SQLServerConnection,
    hash_password: Callable[[str], str],
    include_demo_users: bool = False,
) -> None:
    """Inserta los registros semilla en las 16 tablas de SQL Server con IDs deterministas si están vacías."""
    users_rows = [
        f"(1, {sql_lit('Dra. Melany Díaz (Admin)')}, {sql_lit('admin@patitasfelices.pe')}, {sql_lit(hash_password('admin123'))}, 'admin', 'activo', '990853697')"
    ]
    if include_demo_users:
        users_rows.extend(
            [
                f"(2, {sql_lit('Dr. Carlos Mendoza (Veterinario)')}, {sql_lit('doctor@patitasfelices.pe')}, {sql_lit(hash_password('doctor123'))}, 'doctor', 'activo', '987654321')",
                f"(3, {sql_lit('Lucía Fernández (Cliente)')}, {sql_lit('cliente@patitasfelices.pe')}, {sql_lit(hash_password('cliente123'))}, 'cliente', 'activo', '912345678')",
                f"(4, {sql_lit('Usuario Suspendido (Prueba Proxy)')}, {sql_lit('inactivo@patitasfelices.pe')}, {sql_lit(hash_password('inactivo123'))}, 'cliente', 'inactivo', '900000000')",
            ]
        )

    conn.execute(
        f"""
        IF NOT EXISTS (SELECT 1 FROM dbo.usuarios)
        BEGIN
            SET IDENTITY_INSERT dbo.usuarios ON;
            INSERT INTO dbo.usuarios (id, nombre, email, password_hash, rol, estado, telefono)
            VALUES {', '.join(users_rows)};
            SET IDENTITY_INSERT dbo.usuarios OFF;
            DBCC CHECKIDENT ('dbo.usuarios', RESEED);
        END;
        """
    )

    conn.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM dbo.Dueno)
        BEGIN
            DECLARE @uid_cli INT = (SELECT TOP 1 id FROM dbo.usuarios WHERE email = 'cliente@patitasfelices.pe');
            SET IDENTITY_INSERT dbo.Dueno ON;
            INSERT INTO dbo.Dueno (id_dueno, usuario_id, dni, tipo_documento, nombres, apellidos, telefono)
            VALUES
                (1, @uid_cli, '74859632', 'DNI', N'Lucía', N'Fernández', '912345678'),
                (2, NULL, '45896321', 'DNI', N'Jorge', N'Ramírez', '987112233');
            SET IDENTITY_INSERT dbo.Dueno OFF;
            DBCC CHECKIDENT ('dbo.Dueno', RESEED);
        END;
        """
    )

    conn.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM dbo.Especie)
        BEGIN
            SET IDENTITY_INSERT dbo.Especie ON;
            INSERT INTO dbo.Especie (Id_especie, Nombre, Descripcion)
            VALUES
                (1, N'Perro', N'Especie canina'),
                (2, N'Gato', N'Especie felina'),
                (3, N'Ave', N'Aves domésticas'),
                (4, N'Conejo', N'Lagomorfos domésticos'),
                (5, N'Otro', N'Otras especies');
            SET IDENTITY_INSERT dbo.Especie OFF;
            DBCC CHECKIDENT ('dbo.Especie', RESEED);
        END;
        """
    )

    conn.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM dbo.Razas)
        BEGIN
            SET IDENTITY_INSERT dbo.Razas ON;
            INSERT INTO dbo.Razas (Id_raza, Id_especie, nombre, Descripcion)
            VALUES
                (1, 1, N'Golden Retriever', N'Raza canina'),
                (2, 2, N'Siamés', N'Raza felina'),
                (3, 1, N'Mestizo', N'Sin clasificación específica'),
                (4, 2, N'Mestizo', N'Sin clasificación específica');
            SET IDENTITY_INSERT dbo.Razas OFF;
            DBCC CHECKIDENT ('dbo.Razas', RESEED);
        END;
        """
    )

    conn.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM dbo.Especialidad)
        BEGIN
            SET IDENTITY_INSERT dbo.Especialidad ON;
            INSERT INTO dbo.Especialidad (Id_especialidad, Nombre, Descripcion)
            VALUES
                (1, N'Medicina General e Interna', N'Diagnóstico clínico y prevención'),
                (2, N'Dermatología y Cirugía Menor', N'Atención de piel y tejidos');
            SET IDENTITY_INSERT dbo.Especialidad OFF;
            DBCC CHECKIDENT ('dbo.Especialidad', RESEED);
        END;
        """
    )

    conn.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM dbo.Veterinario)
        BEGIN
            DECLARE @uid_doc INT = (SELECT TOP 1 id FROM dbo.usuarios WHERE email = 'doctor@patitasfelices.pe');
            DECLARE @uid_adm INT = (SELECT TOP 1 id FROM dbo.usuarios WHERE email = 'admin@patitasfelices.pe');
            SET IDENTITY_INSERT dbo.Veterinario ON;
            INSERT INTO dbo.Veterinario (Id_veterinario, usuario_id, Id_especialidad, numero_colegiatura, nombres, Apellidos, Telefono, Fecha_contratacion)
            VALUES
                (1, @uid_doc, 1, 'CMVP-10452', N'Carlos', N'Mendoza', '987654321', '2024-01-15'),
                (2, CASE WHEN @uid_doc IS NULL THEN @uid_adm ELSE NULL END, 2, 'CMVP-11890', N'Melany', N'Díaz Marín', '990853697', '2023-08-01');
            SET IDENTITY_INSERT dbo.Veterinario OFF;
            DBCC CHECKIDENT ('dbo.Veterinario', RESEED);
        END;
        """
    )

    conn.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM dbo.Servicios)
        BEGIN
            SET IDENTITY_INSERT dbo.Servicios ON;
            INSERT INTO dbo.Servicios (Id_servicios, Nombre, Precio, Estado)
            VALUES
                (1, N'Consulta general', 60.00, 'Activo'),
                (2, N'Vacunación', 75.00, 'Activo'),
                (3, N'Desparasitación', 45.00, 'Activo'),
                (4, N'Control y seguimiento', 40.00, 'Activo');
            SET IDENTITY_INSERT dbo.Servicios OFF;
            DBCC CHECKIDENT ('dbo.Servicios', RESEED);
        END;
        """
    )

    conn.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM dbo.productos)
        BEGIN
            SET IDENTITY_INSERT dbo.productos ON;
            INSERT INTO dbo.productos (id, codigo, nombre, categoria, descripcion, precio, stock, activo)
            VALUES
                (1, 'VET-001', N'Antipulgas Bravecto Chewable 10-20kg', N'Farmacia', N'Protección por 12 semanas contra pulgas y garrapatas.', 145.00, 25, 1),
                (2, 'VET-002', N'Alimento Clínico Renal Canine 2kg', N'Nutrición', N'Dieta terapéutica de soporte renal e hidratación.', 89.50, 18, 1),
                (3, 'VET-003', N'Shampoo Dermatológico Clorhexidina 250ml', N'Higiene', N'Fórmula hipoalergénica antiséptica para piel sensible.', 48.00, 30, 1),
                (4, 'VET-004', N'Suplemento Omega 3 & Vitaminas Pelaje', N'Suplementos', N'Cápsulas blandas para articulaciones y pelaje.', 65.00, 20, 1),
                (5, 'VET-005', N'Collar Isabelino Ajustable Acolchado', N'Accesorios', N'Recuperación postoperatoria cómoda.', 35.00, 15, 1),
                (6, 'VET-006', N'Kit Dental Enzimático Veterinario', N'Higiene', N'Pasta enzimática y cepillo veterinario.', 42.00, 12, 1);
            SET IDENTITY_INSERT dbo.productos OFF;
            DBCC CHECKIDENT ('dbo.productos', RESEED);
        END;
        """
    )

    conn.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM dbo.Paciente)
        BEGIN
            SET IDENTITY_INSERT dbo.Paciente ON;
            INSERT INTO dbo.Paciente (id_paciente, id_dueno, Id_raza, nombre, sexo, fecha_nacimiento, peso_kg, historial_resumen, estado)
            VALUES
                (1, 1, 1, N'Luna', 'H', '2023-03-15', 24.50, N'Vacunación vigente.', 'Activo'),
                (2, 1, 2, N'Michi', 'M', '2024-06-10', 4.20, N'Control preventivo al día.', 'Activo');
            SET IDENTITY_INSERT dbo.Paciente OFF;
            DBCC CHECKIDENT ('dbo.Paciente', RESEED);
        END;
        """
    )

    conn.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM dbo.Cita)
        BEGIN
            SET IDENTITY_INSERT dbo.Cita ON;
            INSERT INTO dbo.Cita (Id_cita, Id_veterinario, id_paciente, fecha, hora, motivo, estado)
            VALUES
                (1, 1, 1, '2026-10-30', '10:00', N'Control general.', 'confirmada'),
                (2, 1, 2, '2026-10-31', '11:30', N'Refuerzo de vacuna.', 'pendiente');
            SET IDENTITY_INSERT dbo.Cita OFF;
            DBCC CHECKIDENT ('dbo.Cita', RESEED);

            INSERT INTO dbo.Detalle_servicios (Id_cita, Id_servicios, precio_aplicado)
            VALUES
                (1, 1, 60.00),
                (2, 2, 75.00);
        END;
        """
    )

    conn.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM dbo.Historial_clinico)
        BEGIN
            SET IDENTITY_INSERT dbo.Historial_clinico ON;
            INSERT INTO dbo.Historial_clinico (Id_historial, Id_cita, Diagnostico, Tratamiento, Observaciones)
            VALUES (1, 1, N'Dermatitis leve controlada.', N'Baño medicado cada 7 días.', N'Paciente estable.');
            SET IDENTITY_INSERT dbo.Historial_clinico OFF;
            DBCC CHECKIDENT ('dbo.Historial_clinico', RESEED);
        END;
        """
    )

    conn.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM dbo.Receta)
        BEGIN
            SET IDENTITY_INSERT dbo.Receta ON;
            INSERT INTO dbo.Receta (Id_receta, Id_historial, medicamento, Dosis, duracion_dias, indicaciones)
            VALUES (1, 1, N'Shampoo Dermatológico Clorhexidina 250ml', N'Aplicación tópica', 21, N'Secar con toalla limpia.');
            SET IDENTITY_INSERT dbo.Receta OFF;
            DBCC CHECKIDENT ('dbo.Receta', RESEED);
        END;
        """
    )

    conn.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM dbo.Factura)
        BEGIN
            SET IDENTITY_INSERT dbo.Factura ON;
            INSERT INTO dbo.Factura (id_factura, Id_cita, id_dueno, tipo, serie, numero, subtotal, igv, total, estado)
            VALUES (1, 1, 1, 'Factura', 'F001', 1, 50.85, 9.15, 60.00, 'Pagado');
            SET IDENTITY_INSERT dbo.Factura OFF;
            DBCC CHECKIDENT ('dbo.Factura', RESEED);

            SET IDENTITY_INSERT dbo.Pago ON;
            INSERT INTO dbo.Pago (id_pago, id_factura, metodo_pago, monto, estado)
            VALUES (1, 1, 'Yape', 60.00, 'Pagado');
            SET IDENTITY_INSERT dbo.Pago OFF;
            DBCC CHECKIDENT ('dbo.Pago', RESEED);

            SET IDENTITY_INSERT dbo.detalle_ventas ON;
            INSERT INTO dbo.detalle_ventas (id, id_factura, producto_id, cantidad, precio_unitario, subtotal)
            VALUES (1, 1, 3, 1, 48.00, 48.00);
            SET IDENTITY_INSERT dbo.detalle_ventas OFF;
            DBCC CHECKIDENT ('dbo.detalle_ventas', RESEED);
        END;
        """
    )
