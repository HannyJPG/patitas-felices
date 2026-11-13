"""Router de Tienda, Farmacia y Comprobantes PDF (Patrón Facade)."""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Header, HTTPException, Request, Response

from ..patterns import (
    ErrorConexionSQLServer,
    ErrorConsultaSQLServer,
    ErrorProcesoVenta,
    ErrorRegistroDuplicadoSQLServer,
    ErrorSeguridadProxy,
)
from ..schemas import CatalogoProductosResponse, CheckoutRequest

router = APIRouter()


@router.get("/api/productos", tags=["Tienda y Checkout (Facade)"], response_model=CatalogoProductosResponse)
def catalogo_productos(request: Request) -> Dict[str, Any]:
    tienda_facade = request.app.state.facade
    try:
        productos = tienda_facade.obtener_catalogo_activo()
        return {"total": len(productos), "productos": productos}
    except ErrorConexionSQLServer as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ErrorConsultaSQLServer as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/tienda/checkout", tags=["Tienda y Checkout (Facade)"])
def procesar_compra(
    pedido: CheckoutRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    proxy_seguridad = request.app.state.proxy
    adaptador_bd = request.app.state.db
    tienda_facade = request.app.state.facade
    usuario_id: Optional[int] = None
    usuario_db = None

    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        try:
            sesion = proxy_seguridad.validar_sesion(token)
            usuario_id = sesion["id"]
            usuario_db = adaptador_bd.obtener_usuario_por_id(usuario_id)
        except ErrorSeguridadProxy as exc:
            raise HTTPException(status_code=exc.codigo_http, detail=str(exc)) from exc
        except ErrorConexionSQLServer as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ErrorConsultaSQLServer as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        if usuario_id is not None and not usuario_db:
            usuario_db = adaptador_bd.obtener_usuario_por_id(usuario_id)

        cliente_nombre = usuario_db["nombre"] if usuario_db else (pedido.cliente_nombre or "Cliente Patitas Felices")
        tipo_doc = (pedido.tipo_documento or "DNI").upper().strip()
        doc_solicitado = pedido.cliente_documento.strip()

        if usuario_db and usuario_db.get("documento"):
            doc_final = str(usuario_db["documento"]).strip()
            tipo_doc = usuario_db.get("tipo_documento") or ("RUC" if len(doc_final) == 11 else "DNI")
        else:
            doc_final = doc_solicitado
            if tipo_doc == "DNI":
                if not doc_final.isdigit() or len(doc_final) != 8:
                    raise HTTPException(status_code=400, detail="El DNI debe contener exactamente 8 dígitos numéricos.")
            elif tipo_doc == "RUC":
                if not doc_final.isdigit() or len(doc_final) != 11:
                    raise HTTPException(status_code=400, detail="El RUC debe contener exactamente 11 dígitos numéricos.")
            else:
                raise HTTPException(status_code=400, detail="El tipo de documento debe ser DNI o RUC.")
            if usuario_db and hasattr(adaptador_bd, "validar_documento_disponible"):
                adaptador_bd.validar_documento_disponible(usuario_db["id"], doc_final)

        resultado = tienda_facade.procesar_venta(
            usuario_id=usuario_id,
            cliente_nombre=cliente_nombre,
            cliente_documento=doc_final,
            items=[i.model_dump() for i in pedido.items],
            metodo_pago=pedido.metodo_pago,
        )
        if usuario_db and not usuario_db.get("documento"):
            adaptador_bd.actualizar_documento_usuario(usuario_db["id"], tipo_doc, doc_final)
        return {
            "mensaje": "Venta procesada exitosamente mediante TiendaFacade.",
            "usuario_actualizado": {
                "id": usuario_id,
                "nombre": cliente_nombre,
                "tipo_documento": tipo_doc,
                "documento": doc_final,
            },
            **resultado,
        }
    except HTTPException:
        raise
    except (ErrorProcesoVenta, ValueError, ErrorRegistroDuplicadoSQLServer) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ErrorConexionSQLServer as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ErrorConsultaSQLServer as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/tienda/boleta/{venta_id}/pdf", tags=["Tienda y Checkout (Facade)"])
def descargar_boleta_pdf(
    venta_id: int,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Response:
    proxy_seguridad = request.app.state.proxy
    adaptador_bd = request.app.state.db
    tienda_facade = request.app.state.facade
    try:
        sesion = proxy_seguridad.validar_sesion(authorization or "")
        if hasattr(adaptador_bd, "obtener_venta_por_id"):
            venta = adaptador_bd.obtener_venta_por_id(venta_id)
        else:
            ventas = adaptador_bd.listar_ventas()
            venta = next((v for v in ventas if int(v["id"]) == venta_id), None)
    except ErrorSeguridadProxy as exc:
        raise HTTPException(status_code=exc.codigo_http, detail=str(exc)) from exc
    except ErrorConexionSQLServer as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ErrorConsultaSQLServer as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not venta:
        raise HTTPException(status_code=404, detail="Boleta no encontrada.")
    rol_actual = str(sesion.get("rol", "")).lower()
    uid_venta = venta.get("usuario_id")
    if rol_actual != "admin" and (uid_venta is None or int(uid_venta) != int(sesion.get("id", -1))):
        raise HTTPException(
            status_code=403,
            detail="No tienes permiso para descargar esta boleta electrónica.",
        )
    pdf_bytes = tienda_facade.pdf_generator.construir_pdf_en_memoria(venta)
    nombre_archivo = f"Boleta_{venta['numero_boleta']}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre_archivo}"'},
    )
