"""
Pruebas Unitarias y de Integración con Pytest - Clínica Veterinaria Patitas Felices
Valida:
1. Cálculo de boletas, descuento de stock y PDF en memoria (Patrón Facade).
2. Permisos por rol RBAC y vistas dinámicas (Patrón Strategy).
3. Guardián de seguridad JWT y bloqueo de usuarios inactivos (Patrón Proxy).
4. Formateo de URL de WhatsApp y persistencia desacoplada (Patrón Adapter).
5. Endpoints RESTful de FastAPI.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import crear_app
from backend.patterns import (
    AdminRoleStrategy,
    AuthSessionProxy,
    ClientRoleStrategy,
    DoctorRoleStrategy,
    ErrorProcesoVenta,
    ErrorSeguridadProxy,
    RBACContext,
    RealClinicController,
    SQLServerDatabaseAdapter,
    SubsistemaCRMTransacciones,
    TiendaFacade,
    WhatsAppAdapter,
    generar_token_jwt,
)


@pytest.fixture(scope="session", autouse=True)
def limpiar_bd_temporal_sqlserver():
    """Elimina la base de datos temporal de pruebas en SQL Server al finalizar la suite."""
    yield
    from backend.patterns.sqlserver_schema import SQLServerConnection

    conn_master = SQLServerConnection(database="master")
    conn_master.execute(
        """
        IF DB_ID(N'PatitasFelices_Test_DB') IS NOT NULL
        BEGIN
            ALTER DATABASE [PatitasFelices_Test_DB] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
            DROP DATABASE [PatitasFelices_Test_DB];
        END
        """
    )
    conn_master.close()


@pytest.fixture()
def db_memoria() -> SQLServerDatabaseAdapter:
    """Base de datos de pruebas aislada en Microsoft SQL Server (PatitasFelices_Test_DB)."""
    return SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=True, include_demo_users=True)


@pytest.fixture()
def client(db_memoria: SQLServerDatabaseAdapter) -> TestClient:
    """Cliente de pruebas FastAPI conectado al adaptador SQL Server de pruebas."""
    app = crear_app(db_adapter=db_memoria)
    return TestClient(app)
