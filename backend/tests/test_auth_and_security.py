"""Pruebas de autenticación, RBAC administrativo, IDOR, 503 y seguridad de sesiones."""

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


def test_flujo_completo_endpoints_fastapi(client: TestClient) -> None:
    # 1. Login como Cliente
    res_login = client.post(
        "/api/auth/login",
        json={"email": "cliente@patitasfelices.pe", "password": "cliente123"},
    )
    assert res_login.status_code == 200
    datos_cliente = res_login.json()
    token_cliente = datos_cliente["token"]
    assert datos_cliente["rbac"]["ruta_principal"] == "/tienda"

    # 2. Compra en tienda y descarga de PDF
    res_compra = client.post(
        "/api/tienda/checkout",
        headers={"Authorization": f"Bearer {token_cliente}"},
        json={
            "cliente_nombre": "Lucía Fernández",
            "cliente_documento": "74859632",
            "metodo_pago": "Yape",
            "items": [{"producto_id": 3, "cantidad": 2}],
        },
    )
    assert res_compra.status_code == 200
    venta_id = res_compra.json()["venta"]["id"]

    # Boleta PDF requiere autenticación y pertenencia
    assert client.get(f"/api/tienda/boleta/{venta_id}/pdf").status_code == 401
    res_pdf = client.get(
        f"/api/tienda/boleta/{venta_id}/pdf",
        headers={"Authorization": f"Bearer {token_cliente}"},
    )
    assert res_pdf.status_code == 200
    assert res_pdf.headers["content-type"] == "application/pdf"
    assert res_pdf.content.startswith(b"%PDF-1.4")

    # 3. Login como Doctor y actualización de diagnóstico
    res_doc = client.post(
        "/api/auth/login",
        json={"email": "doctor@patitasfelices.pe", "password": "doctor123"},
    )
    token_doctor = res_doc.json()["token"]
    res_diag = client.patch(
        "/api/doctor/citas/1",
        headers={"Authorization": f"Bearer {token_doctor}"},
        json={
            "estado": "atendida",
            "diagnostico": "Paciente completamente recuperado.",
            "tratamiento": "Alta médica.",
        },
    )
    assert res_diag.status_code == 200
    assert res_diag.json()["cita"]["estado"] == "atendida"

    # 4. Login como Admin y desactivación de usuario para probar el Proxy en vivo
    res_admin = client.post(
        "/api/auth/login",
        json={"email": "admin@patitasfelices.pe", "password": "admin123"},
    )
    token_admin = res_admin.json()["token"]
    res_inactivar = client.patch(
        "/api/admin/usuarios/3/estado",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"estado": "inactivo"},
    )
    assert res_inactivar.status_code == 200
    assert res_inactivar.json()["usuario"]["estado"] == "inactivo"

    # Ahora el token anterior del cliente 3 es bloqueado inmediatamente por AuthSessionProxy
    res_bloqueado = client.get(
        "/api/cliente/mis-citas",
        headers={"Authorization": f"Bearer {token_cliente}"},
    )
    assert res_bloqueado.status_code == 403

    # 5. Visor en vivo de las 16 tablas requiere rol admin (401 sin token, 403 si no es admin)
    assert client.get("/api/bd/tablas").status_code == 401
    res_tablas = client.get(
        "/api/bd/tablas",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_tablas.status_code == 200
    cuerpo_tablas = res_tablas.json()
    assert cuerpo_tablas["total_tablas"] == 16
    tablas = cuerpo_tablas["tablas"]
    for nombre_tabla in (
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
    ):
        assert nombre_tabla in tablas
        assert len(tablas[nombre_tabla]) >= 1

    res_visor = client.get("/visor-bd")
    assert res_visor.status_code == 200
    assert "Visor en Vivo de las 16 Tablas" in res_visor.text

def test_registro_cliente_exitoso_y_bloqueo_duplicados(db_memoria: SQLServerDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    # 1. Registro exitoso de nuevo cliente
    payload_nuevo = {
        "nombre": "Renato Castillo",
        "email": "renato@ejemplo.com",
        "password": "claveSegura123",
        "telefono": "987112233",
    }
    res = client.post("/api/auth/register", json=payload_nuevo)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "token" in data
    assert data["usuario"]["email"] == "renato@ejemplo.com"
    assert data["usuario"]["rol"] == "cliente"
    assert data["usuario"]["estado"] == "activo"
    assert data["rbac"]["rol"] == "cliente"

    # Verificar que puede consultar su sesión con el token recibido
    token = data["token"]
    res_sesion = client.get("/api/auth/sesion", headers={"Authorization": f"Bearer {token}"})
    assert res_sesion.status_code == 200
    assert res_sesion.json()["usuario"]["email"] == "renato@ejemplo.com"

    # 2. Intento de registro duplicado con el mismo correo -> 400 Bad Request
    res_duplicado = client.post("/api/auth/register", json=payload_nuevo)
    assert res_duplicado.status_code == 400
    assert "Ya existe una cuenta" in res_duplicado.json()["detail"]

def test_admin_alta_personal_doctor_y_admin(db_memoria: SQLServerDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    # Login como admin existente
    res_login_admin = client.post(
        "/api/auth/login",
        json={"email": "admin@patitasfelices.pe", "password": "admin123"},
    )
    assert res_login_admin.status_code == 200
    token_admin = res_login_admin.json()["token"]

    # 1. Alta interna de un nuevo Doctor por el Admin
    payload_doctor = {
        "nombre": "Dra. Sofía Alarcón",
        "email": "sofia.alarcon@patitasfelices.pe",
        "password": "doctoraClave2026",
        "rol": "doctor",
        "telefono": "981234567",
        "cmvp": "CMVP-18942",
        "especialidad": "Cirugía y Traumatología",
    }
    res_doc = client.post(
        "/api/admin/usuarios",
        headers={"Authorization": f"Bearer {token_admin}"},
        json=payload_doctor,
    )
    assert res_doc.status_code == 200, res_doc.text
    usuario_doc = res_doc.json()["usuario"]
    assert usuario_doc["rol"] == "doctor"
    assert usuario_doc["email"] == "sofia.alarcon@patitasfelices.pe"

    # El nuevo doctor puede iniciar sesión con sus credenciales creadas
    res_login_doc = client.post(
        "/api/auth/login",
        json={"email": "sofia.alarcon@patitasfelices.pe", "password": "doctoraClave2026"},
    )
    assert res_login_doc.status_code == 200
    assert res_login_doc.json()["rbac"]["rol"] == "doctor"
    assert res_login_doc.json()["rbac"]["ruta_espacio"] == "/doctor"

    # 1.b Intento de registrar otro doctor con la MISMA colegiatura CMVP -> Debe ser rechazado (400)
    res_doc_duplicado = client.post(
        "/api/admin/usuarios",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "nombre": "Dr. Otro Médico",
            "email": "otro.medico@patitasfelices.pe",
            "password": "doctoraClave2026",
            "rol": "doctor",
            "telefono": "981234599",
            "cmvp": "CMVP-18942",
            "especialidad": "Medicina General",
        },
    )
    assert res_doc_duplicado.status_code == 400
    assert "colegiatura" in res_doc_duplicado.json()["detail"].lower()
    assert db_memoria.obtener_usuario_por_email("otro.medico@patitasfelices.pe") is None

    # 1.c Alta de un Administrador sin colegiatura -> Debe crearse sin pedir CMVP
    res_nuevo_admin = client.post(
        "/api/admin/usuarios",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "nombre": "Admin General",
            "email": "admin2@patitasfelices.pe",
            "password": "adminClave2026",
            "rol": "admin",
            "telefono": "981000111",
            "cmvp": "",
            "especialidad": "",
        },
    )
    assert res_nuevo_admin.status_code == 200
    assert res_nuevo_admin.json()["usuario"]["rol"] == "admin"

    # 2. Intento de crear personal sin token o con rol de cliente -> 401 o 403
    res_sin_auth = client.post("/api/admin/usuarios", json=payload_doctor)
    assert res_sin_auth.status_code in (401, 403)

def test_checkout_bloquea_nombre_y_registra_documento_unico(db_memoria: SQLServerDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    # 1. Registrar un nuevo usuario "Pepe Loco" sin documento previo
    res_reg = client.post(
        "/api/auth/register",
        json={"nombre": "Pepe Loco", "email": "pepe@ejemplo.com", "password": "claveSegura123", "telefono": "987654321"},
    )
    assert res_reg.status_code == 200
    token_pepe = res_reg.json()["token"]

    # 2. Pepe compra en la tienda enviando un nombre diferente ("Nombre Falso") y su DNI "88776655"
    payload_compra = {
        "cliente_nombre": "Nombre Falso",
        "tipo_documento": "DNI",
        "cliente_documento": "88776655",
        "metodo_pago": "Yape / Plin",
        "items": [{"producto_id": 1, "cantidad": 1}],
    }
    res_compra = client.post(
        "/api/tienda/checkout",
        headers={"Authorization": f"Bearer {token_pepe}"},
        json=payload_compra,
    )
    assert res_compra.status_code == 200, res_compra.text
    datos_compra = res_compra.json()

    # El sistema fuerza el nombre real de la cuenta ("Pepe Loco") y no permite el nombre falso
    assert datos_compra["venta"]["cliente_nombre"] == "Pepe Loco"
    assert datos_compra["venta"]["cliente_documento"] == "88776655"

    # 3. Pepe intenta comprar nuevamente pero intentando cambiar su DNI a otro número
    payload_cambio = {
        "cliente_nombre": "Pepe Loco",
        "tipo_documento": "DNI",
        "cliente_documento": "99999999",
        "metodo_pago": "Yape / Plin",
        "items": [{"producto_id": 1, "cantidad": 1}],
    }
    res_compra_2 = client.post(
        "/api/tienda/checkout",
        headers={"Authorization": f"Bearer {token_pepe}"},
        json=payload_cambio,
    )
    assert res_compra_2.status_code == 200
    # Como el documento es un identificador único verificado, prevalece el original "88776655"
    assert res_compra_2.json()["venta"]["cliente_documento"] == "88776655"

def test_cliente_registra_documento_en_perfil(db_memoria: SQLServerDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    # Registro de nuevo usuario
    res_reg = client.post(
        "/api/auth/register",
        json={"nombre": "Carlos Rivas", "email": "carlos.rivas@ejemplo.com", "password": "claveSegura123", "telefono": "981234567"},
    )
    token = res_reg.json()["token"]

    # 1. Registrar RUC (11 dígitos)
    res_doc = client.post(
        "/api/cliente/documento",
        headers={"Authorization": f"Bearer {token}"},
        json={"tipo_documento": "RUC", "documento": "20123456789"},
    )
    assert res_doc.status_code == 200, res_doc.text

    # 2. Consultar mis citas y perfil para verificar que aparezca el RUC registrado
    res_citas = client.get(
        "/api/cliente/mis-citas",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_citas.status_code == 200
    perfil = res_citas.json()["perfil"]
    assert perfil["documento"] == "20123456789"
    assert perfil["tipo_documento"] == "RUC"

    # 3. Intentar modificarlo nuevamente debe ser rechazado
    res_reintento = client.post(
        "/api/cliente/documento",
        headers={"Authorization": f"Bearer {token}"},
        json={"tipo_documento": "DNI", "documento": "12345678"},
    )
    assert res_reintento.status_code == 400
    assert "no modificable" in res_reintento.json()["detail"]

def test_cambio_password_cliente_y_bloqueo_clave_invalida(db_memoria: SQLServerDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    # 1. Login con cliente predeterminado (cliente@patitasfelices.pe / cliente123)
    res_login = client.post("/api/auth/login", json={"email": "cliente@patitasfelices.pe", "password": "cliente123"})
    assert res_login.status_code == 200
    token = res_login.json()["token"]

    # 2. Intento de cambio con contraseña actual incorrecta
    res_fallo = client.post(
        "/api/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"password_actual": "claveErronea", "password_nueva": "nuevaClave123"},
    )
    assert res_fallo.status_code == 400
    assert "no es correcta" in res_fallo.json()["detail"]

    # 3. Cambio exitoso
    res_ok = client.post(
        "/api/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"password_actual": "cliente123", "password_nueva": "nuevaClave123"},
    )
    assert res_ok.status_code == 200

    # 4. Verificar login con la nueva contraseña
    res_relogin = client.post("/api/auth/login", json={"email": "cliente@patitasfelices.pe", "password": "nuevaClave123"})
    assert res_relogin.status_code == 200

def test_seguridad_password_hashing_pbkdf2(db_memoria: SQLServerDatabaseAdapter) -> None:
    """Verifica que las contraseñas nunca se almacenen en texto plano sino con PBKDF2-SHA256."""
    from backend.patterns import hashear_password, verificar_password

    hash_generado = hashear_password("miClaveSecreta2026")
    assert hash_generado.startswith("pbkdf2_sha256$")
    assert "miClaveSecreta2026" not in hash_generado
    assert verificar_password("miClaveSecreta2026", hash_generado) is True
    assert verificar_password("claveIncorrecta", hash_generado) is False

    usuario_admin = db_memoria.obtener_usuario_por_email("admin@patitasfelices.pe")
    assert usuario_admin is not None
    assert str(usuario_admin["password_hash"]).startswith("pbkdf2_sha256$")
    assert usuario_admin["password_hash"] != "admin123"

def test_usuarios_eliminados_no_inician_sesion_en_bd_sincronizada() -> None:
    """Verifica que en una base de datos SQL Server inicializada desde cero solo exista el admin base y cuentas demo eliminadas reciban 401."""
    db_real = SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=True, include_demo_users=False)
    app = crear_app(db_adapter=db_real)
    client_real = TestClient(app)

    # Admin existente sí puede iniciar sesión
    res_admin = client_real.post(
        "/api/auth/login",
        json={"email": "admin@patitasfelices.pe", "password": "admin123"},
    )
    assert res_admin.status_code == 200

    # Doctor y Cliente demo no incluidos en producción deben recibir 401 Unauthorized
    for email_eliminado, pass_eliminado in (
        ("doctor@patitasfelices.pe", "doctor123"),
        ("cliente@patitasfelices.pe", "cliente123"),
        ("inactivo@patitasfelices.pe", "inactivo123"),
    ):
        res = client_real.post(
            "/api/auth/login",
            json={"email": email_eliminado, "password": pass_eliminado},
        )
        assert res.status_code == 401

def test_endpoints_retornan_503_si_sqlserver_desconectado(
    db_memoria: SQLServerDatabaseAdapter,
):
    """Los endpoints públicos y administrativos deben responder 503 cuando SQL Server cae."""
    from backend.patterns.proxy import generar_token_jwt
    from backend.patterns.sqlserver_schema import SQLServerConnection

    db = db_memoria
    app = crear_app(db_adapter=db)
    client = TestClient(app)

    token_admin = generar_token_jwt({"id": 1, "rol": "admin", "email": "admin@patitasfelices.pe"})
    db.conn = SQLServerConnection(server="localhost,65432", database="PatitasFelices_Test_DB")
    assert client.get("/api/productos").status_code == 503
    assert client.get("/api/bd/tablas").status_code == 401
    assert (
        client.get(
            "/api/bd/tablas",
            headers={"Authorization": f"Bearer {token_admin}"},
        ).status_code
        == 503
    )
    assert client.get("/api/citas/disponibilidad?fecha=2026-10-27").status_code == 503
    assert (
        client.post(
            "/api/tienda/checkout",
            json={
                "cliente_nombre": "Cliente",
                "tipo_documento": "DNI",
                "cliente_documento": "12345678",
                "items": [{"producto_id": 1, "cantidad": 1}],
                "metodo_pago": "Yape",
            },
        ).status_code
        == 503
    )

def test_admin_no_puede_autosuspenderse():
    """Un administrador activo no debe poder suspender su propia cuenta."""
    db = SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=True, include_demo_users=True)
    app = crear_app(db_adapter=db)
    client = TestClient(app)

    login = client.post(
        "/api/auth/login",
        json={"email": "admin@patitasfelices.pe", "password": "admin123"},
    )
    assert login.status_code == 200
    token_admin = login.json()["token"]
    admin_id = login.json()["usuario"]["id"]

    res = client.patch(
        f"/api/admin/usuarios/{admin_id}/estado",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"estado": "inactivo"},
    )
    assert res.status_code == 400
    assert db.obtener_usuario_por_id(admin_id)["estado"] == "activo"

def test_guest_checkout_no_secuestra_dueno_de_usuario_registrado():
    """Un invitado usando el DNI de un usuario registrado no debe adjuntar la compra a la cuenta de ese usuario."""
    db = SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=True, include_demo_users=True)
    app = crear_app(db_adapter=db)
    client = TestClient(app)

    prod = db.listar_productos()[0]
    # Lucía (usuario_id=3 en demo seed) o registremos un cliente con DNI propio
    res_reg = client.post(
        "/api/auth/register",
        json={
            "nombre": "Carlos Quispe",
            "email": "carlos.dueno@patitasfelices.pe",
            "password": "Password123!",
            "telefono": "999888777",
        },
    )
    assert res_reg.status_code == 200
    uid_carlos = res_reg.json()["usuario"]["id"]
    db.actualizar_documento_usuario(uid_carlos, "DNI", "71234567")

    # Invitado sin token intenta comprar con ese mismo DNI
    res_guest = client.post(
        "/api/tienda/checkout",
        json={
            "cliente_nombre": "Visitante Externo",
            "tipo_documento": "DNI",
            "cliente_documento": "71234567",
            "items": [{"producto_id": int(prod["id"]), "cantidad": 1}],
            "metodo_pago": "Yape",
        },
    )
    assert res_guest.status_code == 200
    assert len(db.listar_compras_usuario(uid_carlos)) == 0

def test_seguridad_idor_boleta_y_cita_anonima_no_asocia_tercero():
    """Un cliente no puede descargar boletas ajenas y una cita anónima no debe asociarse a usuario_id del body."""
    db = SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=True, include_demo_users=True)
    app = crear_app(db_adapter=db)
    client = TestClient(app)

    login_admin = client.post(
        "/api/auth/login",
        json={"email": "admin@patitasfelices.pe", "password": "admin123"},
    )
    token_admin = login_admin.json()["token"]
    prod = db.listar_productos()[0]
    res_venta = client.post(
        "/api/tienda/checkout",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "cliente_nombre": "Admin",
            "tipo_documento": "DNI",
            "cliente_documento": "70000001",
            "items": [{"producto_id": int(prod["id"]), "cantidad": 1}],
            "metodo_pago": "Yape",
        },
    )
    assert res_venta.status_code == 200
    venta_id = res_venta.json()["venta"]["id"]

    login_cliente = client.post(
        "/api/auth/login",
        json={"email": "cliente@patitasfelices.pe", "password": "cliente123"},
    )
    token_cliente = login_cliente.json()["token"]
    assert (
        client.get(
            f"/api/tienda/boleta/{venta_id}/pdf",
            headers={"Authorization": f"Bearer {token_cliente}"},
        ).status_code
        == 403
    )

    citas_antes_cliente = len(db.listar_citas(usuario_id=3))
    res_cita = client.post(
        "/api/citas",
        json={
            "usuario_id": 3,
            "propietario": "Invitado Anónimo",
            "telefono": "999777666",
            "mascota_nombre": "Boby",
            "servicio": "consulta",
            "fecha": "2026-12-22",
            "hora": "10:00",
            "motivo": "Chequeo general",
        },
    )
    assert res_cita.status_code == 200
    assert len(db.listar_citas(usuario_id=3)) == citas_antes_cliente


def test_crm_oculta_datos_demo_por_defecto_y_expone_con_query_demo(client: TestClient) -> None:
    """GET /api/admin/crm debe ocultar datos demo por defecto (demo=0) y exponerlos solo con ?demo=1."""
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@patitasfelices.pe", "password": "admin123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    res_real = client.get("/api/admin/crm", headers=headers)
    assert res_real.status_code == 200
    crm_real = res_real.json()
    assert crm_real["ventas_referencia_demo"] == []
    assert crm_real["balance_financiero"]["modo_demostracion"] is False

    res_demo = client.get("/api/admin/crm?demo=1", headers=headers)
    assert res_demo.status_code == 200
    crm_demo = res_demo.json()
    assert len(crm_demo["ventas_referencia_demo"]) >= 1
    assert crm_demo["ventas_referencia_demo"][0]["es_demostracion"] is True
