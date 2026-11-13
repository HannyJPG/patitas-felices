"""Pruebas de patrones GoF (Facade, Strategy, Proxy, Adapter) y atomicidad de checkout."""

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


def test_calculo_exacto_boleta_igv() -> None:
    items = [
        {"producto_id": 1, "cantidad": 2, "precio_unitario": 59.00, "subtotal": 118.00},
    ]
    totales = SubsistemaCRMTransacciones.calcular_totales_boleta(items)
    assert totales["total"] == 118.00
    assert totales["subtotal"] == 100.00
    assert totales["igv"] == 18.00

def test_tienda_facade_procesa_venta_descuenta_stock_y_genera_pdf(db_memoria: SQLServerDatabaseAdapter) -> None:
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

def test_tienda_facade_rechaza_venta_sin_stock(db_memoria: SQLServerDatabaseAdapter) -> None:
    facade = TiendaFacade(db_memoria)
    with pytest.raises(ErrorProcesoVenta, match="Stock insuficiente"):
        facade.procesar_venta(
            usuario_id=3,
            cliente_nombre="Lucía Fernández",
            cliente_documento="74859632",
            items=[{"producto_id": 1, "cantidad": 999}],
        )

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

def test_proxy_bloquea_token_ausente_y_usuario_inactivo(db_memoria: SQLServerDatabaseAdapter) -> None:
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

def test_checkout_rechaza_jwt_invalido_y_compensa_stock_en_fallo(
    db_memoria: SQLServerDatabaseAdapter, monkeypatch
):
    """
    Un token inválido en /api/tienda/checkout debe retornar 401/403 (sin fallback silencioso),
    y un fallo al registrar la factura debe revertir el descuento de inventario.
    """
    db = db_memoria
    app = crear_app(db_adapter=db)
    client = TestClient(app)

    prod = db.listar_productos()[0]
    stock_inicial = int(prod["stock"])

    res_bad_jwt = client.post(
        "/api/tienda/checkout",
        headers={"Authorization": "Bearer token.adulterado.invalido"},
        json={
            "cliente_nombre": "Atacante",
            "tipo_documento": "DNI",
            "cliente_documento": "12345678",
            "items": [{"producto_id": int(prod["id"]), "cantidad": 1}],
            "metodo_pago": "Tarjeta",
        },
    )
    assert res_bad_jwt.status_code == 401

    facade = TiendaFacade(db)

    def fallo_crm(*args, **kwargs):
        raise RuntimeError("Fallo simulado al registrar factura")

    monkeypatch.setattr(facade.crm, "registrar_transaccion", fallo_crm)
    with pytest.raises(RuntimeError):
        facade.procesar_venta(
            usuario_id=1,
            cliente_nombre="Cliente Prueba",
            cliente_documento="87654321",
            items=[{"producto_id": int(prod["id"]), "cantidad": 2}],
            metodo_pago="Yape",
        )

    prod_post = db.obtener_producto(int(prod["id"]))
    assert int(prod_post["stock"]) == stock_inicial

def test_checkout_rechaza_tipo_documento_invalido_y_rollback_atomico_detalle_ventas():
    """Checkout debe rechazar tipo_documento desconocido y no dejar Factura huérfana si falla detalle_ventas."""
    from backend.patterns.sqlserver_schema import ErrorConsultaSQLServer

    db = SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=True, include_demo_users=True)
    app = crear_app(db_adapter=db)
    client = TestClient(app)

    prod = db.listar_productos()[0]
    res_bad_doc = client.post(
        "/api/tienda/checkout",
        json={
            "cliente_nombre": "Visitante Test",
            "tipo_documento": "PASAPORTE",
            "cliente_documento": "ABC12345",
            "items": [{"producto_id": int(prod["id"]), "cantidad": 1}],
            "metodo_pago": "Yape",
        },
    )
    assert res_bad_doc.status_code == 400

    facturas_antes = int(db.conn.scalar("SELECT CAST(COUNT(*) AS VARCHAR(10)) FROM dbo.Factura"))
    with pytest.raises(ErrorConsultaSQLServer):
        db.registrar_venta_y_detalles(
            {
                "usuario_id": 1,
                "cliente_nombre": "Admin",
                "cliente_documento": "12345678",
                "numero_boleta": "B001-999999",
                "subtotal": 10.0,
                "igv": 1.8,
                "total": 11.8,
                "estado": "pagado",
                "metodo_pago": "Yape",
            },
            [
                {
                    "producto_id": 999999,
                    "cantidad": 1,
                    "precio_unitario": 10.0,
                    "subtotal": 10.0,
                }
            ],
        )
    facturas_despues = int(db.conn.scalar("SELECT CAST(COUNT(*) AS VARCHAR(10)) FROM dbo.Factura"))
    assert facturas_despues == facturas_antes
