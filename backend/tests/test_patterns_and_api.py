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
    SQLiteDatabaseAdapter,
    SubsistemaCRMTransacciones,
    TiendaFacade,
    WhatsAppAdapter,
    generar_token_jwt,
)


@pytest.fixture()
def db_memoria() -> SQLiteDatabaseAdapter:
    """Base de datos SQLite en memoria aislada por cada prueba."""
    return SQLiteDatabaseAdapter(":memory:")


@pytest.fixture()
def client(db_memoria: SQLiteDatabaseAdapter) -> TestClient:
    """Cliente de pruebas FastAPI conectado al adaptador en memoria."""
    app = crear_app(db_adapter=db_memoria)
    return TestClient(app)


# =============================================================================
# 1. PRUEBAS DEL PATRÓN FACADE (CÁLCULO DE BOLETAS, STOCK Y PDF EN MEMORIA)
# =============================================================================

def test_calculo_exacto_boleta_igv() -> None:
    items = [
        {"producto_id": 1, "cantidad": 2, "precio_unitario": 59.00, "subtotal": 118.00},
    ]
    totales = SubsistemaCRMTransacciones.calcular_totales_boleta(items)
    assert totales["total"] == 118.00
    assert totales["subtotal"] == 100.00
    assert totales["igv"] == 18.00


def test_tienda_facade_procesa_venta_descuenta_stock_y_genera_pdf(db_memoria: SQLiteDatabaseAdapter) -> None:
    facade = TiendaFacade(db_memoria)
    producto_inicial = db_memoria.obtener_producto(1)
    assert producto_inicial is not None
    stock_antes = producto_inicial["stock"]

    resultado = facade.procesar_venta(
        usuario_id=3,
        cliente_nombre="Lucía Fernández",
        cliente_documento="74859632",
        items=[{"producto_id": 1, "cantidad": 2}],
        metodo_pago="Yape",
    )

    # 1. Verifica registro CRM y numeración de boleta
    venta = resultado["venta"]
    assert venta["numero_boleta"] == "B001-000001"
    assert venta["total"] == 290.00  # 2 * 145.00
    assert round(venta["subtotal"] + venta["igv"], 2) == 290.00

    # 2. Verifica descuento de stock en la BD
    producto_despues = db_memoria.obtener_producto(1)
    assert producto_despues is not None
    assert producto_despues["stock"] == stock_antes - 2

    # 3. Verifica construcción del archivo PDF real en memoria
    pdf_bytes = base64.b64decode(resultado["pdf_base64"])
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"CLINICA VETERINARIA PATITAS FELICES" in pdf_bytes
    assert b"B001-000001" in pdf_bytes


def test_tienda_facade_rechaza_venta_sin_stock(db_memoria: SQLiteDatabaseAdapter) -> None:
    facade = TiendaFacade(db_memoria)
    with pytest.raises(ErrorProcesoVenta, match="Stock insuficiente"):
        facade.procesar_venta(
            usuario_id=3,
            cliente_nombre="Lucía Fernández",
            cliente_documento="74859632",
            items=[{"producto_id": 1, "cantidad": 999}],
        )


# =============================================================================
# 2. PRUEBAS DEL PATRÓN STRATEGY + RBAC (PERMISOS POR STAKEHOLDER)
# =============================================================================

def test_rbac_strategies_permisos_y_vistas() -> None:
    contexto = RBACContext("cliente")
    assert contexto.autorizar("comprar_productos") is True
    assert contexto.autorizar("agendar_cita") is True
    assert contexto.autorizar("ver_crm_dashboard") is False
    assert contexto.autorizar("actualizar_diagnostico") is False
    assert contexto.obtener_vista_y_permisos()["ruta_principal"] == "/tienda"

    # Cambio dinámico de estrategia a Doctor
    contexto.cambiar_estrategia(DoctorRoleStrategy())
    assert contexto.autorizar("ver_agenda_doctor") is True
    assert contexto.autorizar("actualizar_diagnostico") is True
    assert contexto.autorizar("cambiar_estado_usuario") is False
    assert contexto.obtener_vista_y_permisos()["ruta_principal"] == "/doctor"

    # Cambio dinámico de estrategia a Admin
    contexto.cambiar_estrategia(AdminRoleStrategy())
    assert contexto.autorizar("ver_crm_dashboard") is True
    assert contexto.autorizar("cambiar_estado_usuario") is True
    assert contexto.obtener_vista_y_permisos()["ruta_principal"] == "/admin"


# =============================================================================
# 3. PRUEBAS DEL PATRÓN PROXY (GUARDIÁN DE SESIÓN JWT Y USUARIOS ACTIVOS)
# =============================================================================

def test_proxy_bloquea_token_ausente_y_usuario_inactivo(db_memoria: SQLiteDatabaseAdapter) -> None:
    controlador = RealClinicController(db_memoria)
    proxy = AuthSessionProxy(controlador, db_memoria)

    # Sin token -> 401
    with pytest.raises(ErrorSeguridadProxy) as exc_sin_token:
        proxy.ejecutar_accion(None, "ver_crm_dashboard")
    assert exc_sin_token.value.codigo_http == 401

    # Usuario 4 está 'inactivo' en el seed -> 403 aunque tenga JWT válido
    token_inactivo = generar_token_jwt({"sub": 4, "rol": "cliente"})
    with pytest.raises(ErrorSeguridadProxy, match="inactiva") as exc_inactivo:
        proxy.ejecutar_accion(token_inactivo, "ver_mis_citas")
    assert exc_inactivo.value.codigo_http == 403

    # Cliente activo intentando entrar al CRM de Admin -> 403 por RBAC
    token_cliente = generar_token_jwt({"sub": 3, "rol": "cliente"})
    with pytest.raises(ErrorSeguridadProxy, match="Acceso denegado por RBAC") as exc_rbac:
        proxy.ejecutar_accion(token_cliente, "ver_crm_dashboard")
    assert exc_rbac.value.codigo_http == 403

    # Admin activo accediendo al CRM -> permitido
    token_admin = generar_token_jwt({"sub": 1, "rol": "admin"})
    respuesta = proxy.ejecutar_accion(token_admin, "ver_crm_dashboard")
    assert "resumen" in respuesta
    assert respuesta["resumen"]["total_usuarios"] >= 4


# =============================================================================
# 4. PRUEBAS DEL PATRÓN ADAPTER (WHATSAPP URL Y BASE DE DATOS)
# =============================================================================

def test_whatsapp_adapter_formatea_url_correctamente() -> None:
    adapter = WhatsAppAdapter("51990853697")
    url = adapter.generar_enlace_cita(
        {
            "propietario": "Lucía Fernández",
            "telefono": "912345678",
            "mascota_nombre": "Luna",
            "servicio": "vacunacion",
            "fecha": "2026-11-05",
            "hora": "09:30",
            "motivo": "Refuerzo anual de vacuna séxtuple.",
        }
    )
    assert url.startswith("https://wa.me/51990853697?text=")
    assert "Luna" in url
    assert "05%2F11%2F2026" in url


# =============================================================================
# 5. PRUEBAS INTEGRALES DE ENDPOINTS FASTAPI (LOGIN, CHECKOUT, AGENDA Y CRM)
# =============================================================================

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

    res_pdf = client.get(f"/api/tienda/boleta/{venta_id}/pdf")
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

    # 5. Visor en vivo de las 16 tablas de la Base de Datos (prueba_1.erd.json)
    res_tablas = client.get("/api/bd/tablas")
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


def test_registro_cliente_exitoso_y_bloqueo_duplicados(db_memoria: SQLiteDatabaseAdapter) -> None:
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


def test_admin_alta_personal_doctor_y_admin(db_memoria: SQLiteDatabaseAdapter) -> None:
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

    # 2. Intento de crear personal sin token o con rol de cliente -> 401 o 403
    res_sin_auth = client.post("/api/admin/usuarios", json=payload_doctor)
    assert res_sin_auth.status_code in (401, 403)


def test_cliente_crea_y_elimina_mascota(db_memoria: SQLiteDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    # Login como cliente existente
    res_login = client.post(
        "/api/auth/login",
        json={"email": "cliente@patitasfelices.pe", "password": "cliente123"},
    )
    assert res_login.status_code == 200
    token_cliente = res_login.json()["token"]

    # 1. Registrar una nueva mascota
    payload_mascota = {
        "nombre": "Boby",
        "especie": "Perro",
        "raza": "Beagle",
        "edad": 2,
        "peso_kg": 12.5,
        "sexo": "M",
        "historial_resumen": "Vacuna antirrábica aplicada.",
    }
    res_crear = client.post(
        "/api/cliente/mascotas",
        headers={"Authorization": f"Bearer {token_cliente}"},
        json=payload_mascota,
    )
    assert res_crear.status_code == 200, res_crear.text
    mascota_creada = res_crear.json()["mascota"]
    assert mascota_creada["nombre"] == "Boby"
    assert mascota_creada["raza"] == "Beagle"
    mascota_id = mascota_creada["id"]

    # 2. Consultar lista de mis mascotas
    res_listar = client.get(
        "/api/cliente/mis-mascotas",
        headers={"Authorization": f"Bearer {token_cliente}"},
    )
    assert res_listar.status_code == 200
    mascotas = res_listar.json()["mascotas"]
    assert any(m["id"] == mascota_id for m in mascotas)

    # 3. Eliminar la mascota creada
    res_eliminar = client.delete(
        f"/api/cliente/mascotas/{mascota_id}",
        headers={"Authorization": f"Bearer {token_cliente}"},
    )
    assert res_eliminar.status_code == 200
    assert res_eliminar.json()["eliminado"] is True


def test_checkout_bloquea_nombre_y_registra_documento_unico(db_memoria: SQLiteDatabaseAdapter) -> None:
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


def test_cliente_registra_documento_en_perfil(db_memoria: SQLiteDatabaseAdapter) -> None:
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


def test_cambio_password_cliente_y_bloqueo_clave_invalida(db_memoria: SQLiteDatabaseAdapter) -> None:
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


def test_flujo_solicitud_mascota_cliente_y_aprobacion_admin(db_memoria: SQLiteDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    # Cliente crea mascota
    res_login_c = client.post("/api/auth/login", json={"email": "cliente@patitasfelices.pe", "password": "cliente123"})
    token_cliente = res_login_c.json()["token"]

    res_m = client.post(
        "/api/cliente/mascotas",
        headers={"Authorization": f"Bearer {token_cliente}"},
        json={"nombre": "Pelusa", "especie": "Gato", "raza": "Angora", "edad": 2, "peso_kg": 3.5},
    )
    assert res_m.status_code == 200
    mascota_id = res_m.json()["mascota"]["id"]

    # Cliente solicita edición con justificación descriptiva
    payload_sol = {
        "tipo": "editar",
        "motivo": "Aumento de peso post-esterilización y cambio de dieta",
        "datos_nuevos": {
            "nombre": "Pelusa",
            "especie": "Gato",
            "raza": "Angora",
            "edad": 3,
            "peso_kg": 4.2,
            "historial_resumen": "Control de peso verificado",
        },
    }
    res_sol = client.post(
        f"/api/cliente/mascotas/{mascota_id}/solicitar-cambio",
        headers={"Authorization": f"Bearer {token_cliente}"},
        json=payload_sol,
    )
    assert res_sol.status_code == 200
    solicitud_id = res_sol.json()["solicitud"]["id"]

    # Cliente consulta sus solicitudes
    res_mis_sol = client.get("/api/cliente/solicitudes", headers={"Authorization": f"Bearer {token_cliente}"})
    assert res_mis_sol.status_code == 200
    assert any(s["id"] == solicitud_id for s in res_mis_sol.json()["solicitudes"])

    # Admin consulta la bandeja de solicitudes y la aprueba
    res_login_a = client.post("/api/auth/login", json={"email": "admin@patitasfelices.pe", "password": "admin123"})
    token_admin = res_login_a.json()["token"]

    res_admin_list = client.get("/api/admin/solicitudes-mascotas", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_admin_list.status_code == 200

    res_aprobar = client.post(
        f"/api/admin/solicitudes-mascotas/{solicitud_id}/resolver",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"accion": "aprobar"},
    )
    assert res_aprobar.status_code == 200
    assert res_aprobar.json()["solicitud"]["estado"] == "aprobada"

    # Verificar que los datos de Pelusa se actualizaron en la base de datos
    res_mascotas = client.get("/api/cliente/mis-mascotas", headers={"Authorization": f"Bearer {token_cliente}"})
    pelusa_actualizada = next(m for m in res_mascotas.json()["mascotas"] if m["id"] == mascota_id)
    assert pelusa_actualizada["peso_kg"] == 4.2
    assert pelusa_actualizada["edad"] == 3


def test_cliente_consulta_sus_compras(db_memoria: SQLiteDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    res_login_c = client.post("/api/auth/login", json={"email": "cliente@patitasfelices.pe", "password": "cliente123"})
    token_cliente = res_login_c.json()["token"]

    # Realizar compra
    client.post(
        "/api/tienda/checkout",
        headers={"Authorization": f"Bearer {token_cliente}"},
        json={
            "cliente_nombre": "Lucía Fernández",
            "tipo_documento": "DNI",
            "cliente_documento": "74859632",
            "metodo_pago": "Yape / Plin",
            "items": [{"producto_id": 1, "cantidad": 1}],
        },
    )

    # Consultar mis compras
    res_compras = client.get("/api/cliente/mis-compras", headers={"Authorization": f"Bearer {token_cliente}"})
    assert res_compras.status_code == 200
    compras = res_compras.json()["compras"]
    assert len(compras) >= 1
    assert "detalles" in compras[0]


def test_disponibilidad_horarios_y_limite_tres_doctores(db_memoria: SQLiteDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    fecha_test = "2026-11-01"
    hora_test = "08:30"

    # 1. Consultar disponibilidad inicial (todos los cupos libres)
    res_disp = client.get(f"/api/citas/disponibilidad?fecha={fecha_test}")
    assert res_disp.status_code == 200
    horarios = res_disp.json()["horarios"]
    assert hora_test in horarios
    assert horarios[hora_test]["ocupados"] == 0
    assert horarios[hora_test]["disponible"] is True

    # 2. Registrar 3 citas para llenar los 3 doctores de ese turno
    for i in range(1, 4):
        res_cita = client.post(
            "/api/citas",
            json={
                "propietario": f"Paciente {i}",
                "telefono": f"98765432{i}",
                "mascota_nombre": f"Mascota {i}",
                "servicio": "consulta-general",
                "fecha": fecha_test,
                "hora": hora_test,
                "motivo": f"Control rutinario {i}",
            },
        )
        assert res_cita.status_code == 200, res_cita.text

    # 3. Verificar que la disponibilidad ahora marca 3 ocupados y no disponible
    res_disp_lleno = client.get(f"/api/citas/disponibilidad?fecha={fecha_test}")
    assert res_disp_lleno.status_code == 200
    horario_lleno = res_disp_lleno.json()["horarios"][hora_test]
    assert horario_lleno["ocupados"] == 3
    assert horario_lleno["disponible"] is False

    # 4. Intentar registrar una 4ta cita en el mismo turno debe fallar con 400
    res_cita_cuarta = client.post(
        "/api/citas",
        json={
            "propietario": "Paciente 4 (Sin cupo)",
            "telefono": "987654324",
            "mascota_nombre": "Mascota 4",
            "servicio": "consulta-general",
            "fecha": fecha_test,
            "hora": hora_test,
            "motivo": "Urgencia médica por malestar general",
        },
    )
    assert res_cita_cuarta.status_code == 400
    assert "3 cupos médicos" in res_cita_cuarta.json()["detail"]


def test_seguridad_password_hashing_pbkdf2(db_memoria: SQLiteDatabaseAdapter) -> None:
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


def test_supabase_adapter_fallback_sin_variables_no_da_error_500() -> None:
    """Verifica que si DB_ENGINE=supabase pero faltan variables en la nube, hace fallback sin lanzar HTTP 500."""
    from backend.patterns import SupabasePostgresAdapter

    adaptador_sin_env = SupabasePostgresAdapter(supabase_url="", supabase_key="")
    app = crear_app(db_adapter=adaptador_sin_env)
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


def test_usuarios_eliminados_no_inician_sesion_en_bd_sincronizada() -> None:
    """Verifica que en la base de datos sincronizada (Supabase / SQLite en disco) los usuarios eliminados no puedan iniciar sesión."""
    db_real = SQLiteDatabaseAdapter()
    app = crear_app(db_adapter=db_real)
    client_real = TestClient(app)

    # Admin existente sí puede iniciar sesión
    res_admin = client_real.post(
        "/api/auth/login",
        json={"email": "admin@patitasfelices.pe", "password": "admin123"},
    )
    assert res_admin.status_code == 200

    # Doctor y Cliente eliminados de Supabase deben recibir 401 Unauthorized
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


def test_concordancia_estricta_16_tablas_sqlite_y_erd() -> None:
    """Verifica que SQLite, prueba_1.erd.json y schema_sqlite.sql contengan exactamente las 16 tablas canónicas en 3FN sin tablas paralelas."""
    import json
    from pathlib import Path

    db = SQLiteDatabaseAdapter(":memory:")

    root_dir = Path(__file__).resolve().parents[2]
    erd_path = root_dir / "database" / "prueba_1.erd.json"
    sql_path = root_dir / "database" / "schema_sqlite.sql"

    assert erd_path.exists(), "Debe existir database/prueba_1.erd.json"
    assert sql_path.exists(), "Debe existir database/schema_sqlite.sql"
    assert not (root_dir / "database" / "schema_mysql.sql").exists()
    assert not (root_dir / "database" / "schema_supabase_postgres.sql").exists()

    # 1. Verificar tablas físicas reales en sqlite_master
    conn = db._get_connection()
    tablas_sqlite = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    assert len(tablas_sqlite) == 16
    assert tablas_sqlite == set(SQLiteDatabaseAdapter.NOMBRES_16_TABLAS)
    for tabla_obsoleta in ("mascotas", "citas", "ventas", "solicitudes_mascota"):
        assert tabla_obsoleta not in tablas_sqlite

    # 2. Verificar concordancia con prueba_1.erd.json
    erd_data = json.loads(erd_path.read_text(encoding="utf-8"))
    tablas_erd = {
        erd_data["collections"]["tableEntities"][tid]["name"]
        for tid in erd_data["doc"]["tableIds"]
    }
    assert len(tablas_erd) == 16
    assert tablas_erd == tablas_sqlite

    # 3. Verificar que las 16 tablas tengan datos reales (>= 1 fila)
    datos_16 = db.obtener_todas_las_16_tablas()
    assert len(datos_16) == 16
    for nombre_tabla, filas in datos_16.items():
        assert len(filas) >= 1, f"La tabla {nombre_tabla} debe tener al menos 1 registro"




