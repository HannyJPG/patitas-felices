"""Pruebas de integridad de esquema 3FN, ERD, pool multihilo y SQL Server."""

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


def test_sqlserver_adapter_conexion_activa() -> None:
    """Verifica que SQLServerDatabaseAdapter se conecte directamente a Microsoft SQL Server."""
    from backend.patterns import SQLServerDatabaseAdapter

    adaptador = SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=True, include_demo_users=True)
    app = crear_app(db_adapter=adaptador)
    client = TestClient(app, raise_server_exceptions=False)

    res_login = client.post(
        "/api/auth/login",
        json={"email": "admin@patitasfelices.pe", "password": "admin123"},
    )
    assert res_login.status_code == 200
    assert res_login.json()["usuario"]["rol"] == "admin"

def test_catalogo_productos_y_crm_finanzas_estructurados(client: TestClient) -> None:
    """Verifica que /api/productos no lance HTTP 500 y que /api/admin/crm incluya balance_financiero y ultimas_ventas."""
    # 1. Catálogo de Farmacia e Insumos (/api/productos)
    res_prod = client.get("/api/productos")
    assert res_prod.status_code == 200
    datos_prod = res_prod.json()
    assert datos_prod["total"] >= 6
    assert len(datos_prod["productos"]) == datos_prod["total"]
    assert all(p.get("activo", 1) == 1 for p in datos_prod["productos"])

    # 2. CRM y Finanzas (/api/admin/crm)
    res_login = client.post(
        "/api/auth/login",
        json={"email": "admin@patitasfelices.pe", "password": "admin123"},
    )
    token_admin = res_login.json()["token"]
    res_crm = client.get("/api/admin/crm", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_crm.status_code == 200
    crm = res_crm.json()
    assert "balance_financiero" in crm
    assert "ultimas_ventas" in crm
    assert crm["balance_financiero"]["total_transacciones"] >= 1
    assert crm["balance_financiero"]["ingresos_totales"] > 0
    assert crm["balance_financiero"]["ticket_promedio"] > 0
    assert len(crm["ultimas_ventas"]) >= 1

def test_concordancia_estricta_16_tablas_sqlserver_y_erd() -> None:
    """Verifica que SQL Server, prueba_1.erd.json y schema_sqlserver.sql contengan exactamente las 16 tablas canónicas en 3FN sin redundancias y sin archivos SQLite."""
    import json
    from pathlib import Path

    db = SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=True, include_demo_users=True)

    root_dir = Path(__file__).resolve().parents[2]
    erd_path = root_dir / "database" / "prueba_1.erd.json"
    sqlserver_path = root_dir / "database" / "schema_sqlserver.sql"

    assert erd_path.exists(), "Debe existir database/prueba_1.erd.json"
    assert sqlserver_path.exists(), "Debe existir database/schema_sqlserver.sql"
    assert not (root_dir / "database" / "schema_sqlite.sql").exists()
    assert not (root_dir / "database" / "patitas_felices.db").exists()
    assert not (root_dir / "database" / "schema_mysql.sql").exists()
    assert not (root_dir / "database" / "schema_supabase_postgres.sql").exists()

    # 1. Verificar tablas físicas reales en SQL Server (sys.tables)
    rows_tablas = db.conn.query_json(
        "SELECT t.name AS table_name, c.name AS col_name FROM sys.tables t JOIN sys.columns c ON c.object_id = t.object_id WHERE t.is_ms_shipped = 0"
    )
    mapa_columnas: dict[str, set[str]] = {}
    for r in rows_tablas:
        mapa_columnas.setdefault(r["table_name"], set()).add(r["col_name"])

    tablas_sqlserver = set(mapa_columnas.keys())
    assert len(tablas_sqlserver) == 16
    assert tablas_sqlserver == set(SQLServerDatabaseAdapter.NOMBRES_16_TABLAS)
    for tabla_obsoleta in ("mascotas", "citas", "ventas", "solicitudes_mascota"):
        assert tabla_obsoleta not in tablas_sqlserver

    # 2. Verificar eliminación estricta de columnas redundantes (3FN pura)
    columnas_prohibidas = {
        "usuarios": {"tipo_documento", "documento"},
        "Dueno": {"correo"},
        "Paciente": {"edad"},
        "Veterinario": {"correo"},
        "Cita": {"propietario", "telefono", "mascota_nombre", "servicio"},
        "Factura": {"numero_boleta", "cliente_nombre", "cliente_documento", "metodo_pago"},
        "detalle_ventas": {"producto_nombre"},
    }
    for tabla, cols_redundantes in columnas_prohibidas.items():
        cols_actuales = mapa_columnas.get(tabla, set())
        assert cols_actuales.isdisjoint(cols_redundantes), f"La tabla {tabla} aún tiene columnas redundantes: {cols_actuales & cols_redundantes}"

    # 3. Verificar concordancia exacta de tablas y columnas con prueba_1.erd.json
    erd_data = json.loads(erd_path.read_text(encoding="utf-8"))
    erd_tables = erd_data["collections"]["tableEntities"]
    erd_cols = erd_data["collections"]["tableColumnEntities"]
    tablas_erd = {erd_tables[tid]["name"] for tid in erd_data["doc"]["tableIds"]}
    assert len(tablas_erd) == 16
    assert tablas_erd == tablas_sqlserver

    for tid in erd_data["doc"]["tableIds"]:
        t_entity = erd_tables[tid]
        t_name = t_entity["name"]
        cols_erd = {erd_cols[cid]["name"] for cid in t_entity["columnIds"]}
        cols_sql = mapa_columnas.get(t_name, set())
        assert cols_erd == cols_sql, f"Diferencia de columnas en {t_name}: ERD={cols_erd} vs SQL={cols_sql}"

    # 4. Verificar que las 16 tablas tengan datos reales (>= 1 fila)
    datos_16 = db.obtener_todas_las_16_tablas()
    assert len(datos_16) == 16
    for nombre_tabla, filas in datos_16.items():
        assert len(filas) >= 1, f"La tabla {nombre_tabla} debe tener al menos 1 registro"

def test_auditoria_7_pruebas_obligatorias_persistencia_sqlserver() -> None:
    """
    Ejecuta las 7 pruebas obligatorias de la auditoría de persistencia de usuarios en SQL Server:
    1. Registro, 2. Consulta SELECT directa, 3. Autenticación, 4. Persistencia tras reinicio,
    5. Control de duplicados, 6. Contraseña incorrecta, 7. Manejo de caída de conexión SQL Server.
    """
    from backend.patterns.sqlserver_schema import SQLServerConnection

    # Inicializar primera instancia de la aplicación (Sesión 1 del servidor)
    db_sesion1 = SQLServerDatabaseAdapter(
        "PatitasFelices_Test_DB", reset_tables=True, include_demo_users=False
    )
    app_sesion1 = crear_app(db_adapter=db_sesion1)
    client_sesion1 = TestClient(app_sesion1)

    email_prueba = "valeria.auditoria@patitasfelices.pe"
    password_prueba = "ClaveSegura#2026"

    # =========================================================================
    # PRUEBA 1: REGISTRO DESDE EL ENDPOINT DEL FORMULARIO DE REGISTRO
    # =========================================================================
    res_reg = client_sesion1.post(
        "/api/auth/register",
        json={
            "nombre": "Valeria Quispe",
            "email": email_prueba,
            "password": password_prueba,
            "telefono": "998877665",
        },
    )
    assert res_reg.status_code == 200, res_reg.text
    datos_reg = res_reg.json()
    assert datos_reg["usuario"]["id"] >= 2
    assert datos_reg["usuario"]["email"] == email_prueba
    assert datos_reg["usuario"]["rol"] == "cliente"
    assert datos_reg["usuario"]["estado"] == "activo"
    assert "password_hash" not in datos_reg["usuario"]

    # =========================================================================
    # PRUEBA 2: CONSULTA SELECT DIRECTA EN SQL SERVER
    # =========================================================================
    fila_sql = db_sesion1.conn.query_one(
        "SELECT id, nombre, email, password_hash, rol, estado, telefono FROM dbo.usuarios WHERE email = @email",
        params={"email": email_prueba},
    )
    assert fila_sql is not None, "El usuario debe existir físicamente en dbo.usuarios de SQL Server"
    assert fila_sql["nombre"] == "Valeria Quispe"
    assert fila_sql["email"] == email_prueba
    assert fila_sql["rol"] == "cliente"
    assert fila_sql["estado"] == "activo"
    assert fila_sql["telefono"] == "998877665"
    assert str(fila_sql["password_hash"]).startswith("pbkdf2_sha256$")
    assert fila_sql["password_hash"] != password_prueba

    fila_dueno = db_sesion1.conn.query_one(
        "SELECT id_dueno, usuario_id, nombres, apellidos, telefono FROM dbo.Dueno WHERE usuario_id = @uid",
        params={"uid": int(fila_sql["id"])},
    )
    assert fila_dueno is not None, "El registro asociado en dbo.Dueno debe haberse creado transaccionalmente"
    assert fila_dueno["nombres"] == "Valeria"
    assert fila_dueno["apellidos"] == "Quispe"

    # =========================================================================
    # PRUEBA 3: AUTENTICACIÓN (CERRAR SESIÓN E INICIAR SESIÓN)
    # =========================================================================
    res_login = client_sesion1.post(
        "/api/auth/login",
        json={"email": email_prueba, "password": password_prueba},
    )
    assert res_login.status_code == 200
    token_login = res_login.json()["token"]
    res_sesion = client_sesion1.get(
        "/api/auth/sesion",
        headers={"Authorization": f"Bearer {token_login}"},
    )
    assert res_sesion.status_code == 200
    assert res_sesion.json()["usuario"]["email"] == email_prueba
    assert "password_hash" not in res_sesion.json()["usuario"]

    # =========================================================================
    # PRUEBA 4: PERSISTENCIA DESPUÉS DE CERRAR Y REINICIAR LA APLICACIÓN
    # =========================================================================
    db_sesion1.conn.close()
    del client_sesion1
    del app_sesion1
    del db_sesion1

    # Nueva instancia del servidor conectándose a SQL Server sin reiniciar tablas
    db_sesion2 = SQLServerDatabaseAdapter(
        "PatitasFelices_Test_DB", reset_tables=False, include_demo_users=False
    )
    app_sesion2 = crear_app(db_adapter=db_sesion2)
    client_sesion2 = TestClient(app_sesion2)

    res_login_post_reinicio = client_sesion2.post(
        "/api/auth/login",
        json={"email": email_prueba, "password": password_prueba},
    )
    assert res_login_post_reinicio.status_code == 200
    assert res_login_post_reinicio.json()["usuario"]["nombre"] == "Valeria Quispe"
    assert res_login_post_reinicio.json()["usuario"]["rol"] == "cliente"

    # =========================================================================
    # PRUEBA 5: DUPLICADOS (MISMO CORREO ELECTRÓNICO)
    # =========================================================================
    res_dup = client_sesion2.post(
        "/api/auth/register",
        json={
            "nombre": "Valeria Duplicada",
            "email": email_prueba.upper(),
            "password": "OtraPassword123",
            "telefono": "911223344",
        },
    )
    assert res_dup.status_code == 400
    assert "Ya existe una cuenta" in res_dup.json()["detail"]

    total_filas = db_sesion2.conn.scalar(
        "SELECT CAST(COUNT(*) AS VARCHAR(10)) FROM dbo.usuarios WHERE LOWER(email) = LOWER(@email)",
        params={"email": email_prueba},
    )
    assert int(total_filas) == 1

    # =========================================================================
    # PRUEBA 6: CONTRASEÑA INCORRECTA
    # =========================================================================
    res_bad_pass = client_sesion2.post(
        "/api/auth/login",
        json={"email": email_prueba, "password": "PasswordIncorrecta999"},
    )
    assert res_bad_pass.status_code == 401
    assert "incorrectos" in res_bad_pass.json()["detail"].lower()

    # =========================================================================
    # PRUEBA 7: CONEXIÓN CAÍDA / SQL SERVER NO DISPONIBLE
    # =========================================================================
    # Apuntar la conexión del adaptador a un puerto local sin SQL Server activo
    db_sesion2.conn = SQLServerConnection(server="localhost,65432", database="PatitasFelices_Test_DB")
    res_sin_sql = client_sesion2.post(
        "/api/auth/register",
        json={
            "nombre": "Usuario Sin BD",
            "email": "sinbd@patitasfelices.pe",
            "password": "ClaveSegura123",
            "telefono": "900112233",
        },
    )
    assert res_sin_sql.status_code == 503
    assert "SQL Server" in res_sin_sql.json()["detail"]

def test_sqlserver_concurrencia_multihilo_y_scalar_largo(
    db_memoria: SQLServerDatabaseAdapter,
):
    """
    Verifica que SQLServerConnection serializa llamadas concurrentes sin errores HY000
    ('Connection is busy') y lee respuestas SQLGetData mayores a 65,535 caracteres.
    """
    db = db_memoria

    def tarea(i: int) -> int:
        productos = db.listar_productos()
        usuarios = db.listar_usuarios()
        return len(productos) + len(usuarios) + (i * 0)

    with ThreadPoolExecutor(max_workers=6) as pool:
        resultados = list(pool.map(tarea, range(12)))
    assert len(resultados) == 12
    assert all(r >= 1 for r in resultados)

    cadena_larga = db.conn.scalar("SELECT REPLICATE(CAST('A' AS NVARCHAR(MAX)), 70000)")
    assert len(cadena_larga) == 70000

def test_execute_multi_statement_y_scalar_vacio_en_sqlserver():
    """execute() debe propagar errores en sentencias posteriores del lote y scalar() manejar OUTPUT vacío."""
    from backend.patterns.sqlserver_schema import ErrorConsultaSQLServer

    db = SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=True, include_demo_users=True)
    with pytest.raises(ErrorConsultaSQLServer):
        db.conn.execute("SELECT 1 AS ok; THROW 50000, N'Error en segundo statement', 1;")

    vacio = db.conn.scalar("UPDATE dbo.productos SET stock = stock OUTPUT INSERTED.id WHERE id = -999")
    assert vacio == ""


def test_versionado_esquema_sqlserver_extended_properties(
    db_memoria: SQLServerDatabaseAdapter,
) -> None:
    """Verifica el registro de versión en sys.extended_properties sin crear tablas adicionales fuera de las 16 canónicas."""
    from backend.patterns.sqlserver_schema import obtener_version_esquema

    assert obtener_version_esquema(db_memoria.conn) == "2026.11.12.01"
    tablas = db_memoria.conn.query_json(
        "SELECT name FROM sys.tables WHERE is_ms_shipped = 0"
    )
    assert len(tablas) == 16
