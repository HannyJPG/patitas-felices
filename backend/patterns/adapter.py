"""
PATRÓN ADAPTER (Estructural - GoF)
Implementa el desacoplamiento de Base de Datos (Microsoft SQL Server) y WhatsApp.
Integra el modelo canónico en 3FN de 16 tablas sin redundancias basado en `prueba_1.erd.json`.
"""
from abc import ABC, abstractmethod
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .repositories import (
    _PBKDF2_PREFIX,
    CitasRepositoryMixin,
    IWhatsAppNotificationAdapter,
    MascotasRepositoryMixin,
    TiendaRepositoryMixin,
    UsuariosRepositoryMixin,
    WhatsAppAdapter,
    es_email_valido,
    hashear_password,
    separar_nombres_apellidos,
    verificar_password,
)
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


class SQLServerDatabaseAdapter(
    UsuariosRepositoryMixin,
    MascotasRepositoryMixin,
    CitasRepositoryMixin,
    TiendaRepositoryMixin,
    IDatabaseAdapter,
):
    """
    Adaptador concreto conectado directamente a Microsoft SQL Server (`PatitasFelices_DB` en `localhost`)
    mediante ODBC nativo de Windows (`odbc32.dll`), ejecutando consultas T-SQL sobre las 16 tablas en 3FN.
    """

    NOMBRES_16_TABLAS = NOMBRES_16_TABLAS
    soporta_stock_en_tx = True

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

    def obtener_todas_las_16_tablas(
        self, limit_per_table: Optional[int] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        resultado: Dict[str, List[Dict[str, Any]]] = {}
        top_clause = (
            f"TOP ({max(1, min(1000, int(limit_per_table)))}) "
            if limit_per_table is not None
            else ""
        )
        for tabla in self.NOMBRES_16_TABLAS:
            try:
                if tabla == "usuarios":
                    resultado[tabla] = self.conn.query_json(
                        f"""
                        SELECT {top_clause}
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
                    resultado[tabla] = self.conn.query_json(f"SELECT {top_clause}* FROM dbo.{tabla}")
            except ErrorConexionSQLServer:
                raise
            except Exception as exc:
                raise ErrorConsultaSQLServer(
                    f"No se pudo consultar la tabla '{tabla}' en SQL Server."
                ) from exc
        return resultado


def obtener_adaptador_bd() -> IDatabaseAdapter:
    return SQLServerDatabaseAdapter(
        database=os.getenv("SQLSERVER_DATABASE", "PatitasFelices_DB"),
        server=os.getenv("SQLSERVER_SERVER", "localhost"),
    )


__all__ = [
    "ErrorConexionSQLServer",
    "ErrorConsultaSQLServer",
    "ErrorRegistroDuplicadoSQLServer",
    "IDatabaseAdapter",
    "IWhatsAppNotificationAdapter",
    "SQLServerDatabaseAdapter",
    "WhatsAppAdapter",
    "es_email_valido",
    "hashear_password",
    "obtener_adaptador_bd",
    "separar_nombres_apellidos",
    "verificar_password",
]
