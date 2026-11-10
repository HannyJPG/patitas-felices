"""Exportación de los 4 Patrones de Diseño GoF implementados en Python."""

from .adapter import (
    ErrorConexionSQLServer,
    ErrorConsultaSQLServer,
    ErrorRegistroDuplicadoSQLServer,
    IDatabaseAdapter,
    IWhatsAppNotificationAdapter,
    SQLServerDatabaseAdapter,
    WhatsAppAdapter,
    hashear_password,
    obtener_adaptador_bd,
    verificar_password,
)
from .facade import (
    ErrorProcesoVenta,
    SubsistemaCRMTransacciones,
    SubsistemaGeneradorPDF,
    SubsistemaInventario,
    TiendaFacade,
)
from .proxy import (
    AuthSessionProxy,
    ErrorSeguridadProxy,
    ISecureController,
    RealClinicController,
    generar_token_jwt,
    verificar_token_jwt,
)
from .strategy import (
    AdminRoleStrategy,
    ClientRoleStrategy,
    DoctorRoleStrategy,
    RBACContext,
    RoleAuthorizationStrategy,
)

__all__ = [
    "ErrorConexionSQLServer",
    "ErrorConsultaSQLServer",
    "ErrorRegistroDuplicadoSQLServer",
    "IDatabaseAdapter",
    "IWhatsAppNotificationAdapter",
    "SQLServerDatabaseAdapter",
    "WhatsAppAdapter",
    "hashear_password",
    "obtener_adaptador_bd",
    "verificar_password",
    "TiendaFacade",
    "SubsistemaInventario",
    "SubsistemaCRMTransacciones",
    "SubsistemaGeneradorPDF",
    "ErrorProcesoVenta",
    "ISecureController",
    "RealClinicController",
    "AuthSessionProxy",
    "ErrorSeguridadProxy",
    "generar_token_jwt",
    "verificar_token_jwt",
    "RoleAuthorizationStrategy",
    "ClientRoleStrategy",
    "DoctorRoleStrategy",
    "AdminRoleStrategy",
    "RBACContext",
]
