"""
PATRÓN FACADE (Estructural - GoF)
Puntos de sustentación: 1 y 7.
Propósito: Simplificar el proceso de Checkout de la Tienda Veterinaria.
Cuando el cliente compra en Astro, el Frontend solo invoca a TiendaFacade.procesar_venta().
Por dentro, la fachada coordina 3 subsistemas complejos:
1) SubsistemaInventario: Verifica disponibilidad y descuenta el stock en la BD.
2) SubsistemaCRMTransacciones: Calcula subtotal, IGV (18%) y total, y registra la venta
   en las tablas `ventas` y `detalle_ventas` para el CRM del Administrador.
3) SubsistemaGeneradorPDF: Construye en memoria un archivo PDF real (%PDF-1.4) con los
   datos fiscales de la Clínica Patitas Felices y el detalle de la boleta electrónica.
"""

import base64
from datetime import datetime
from typing import Any, Dict, List
import unicodedata

from .adapter import IDatabaseAdapter, IWhatsAppNotificationAdapter, WhatsAppAdapter


class ErrorProcesoVenta(ValueError):
    """Excepción de negocio cuando el checkout no puede completarse (ej. stock insuficiente)."""


# =============================================================================
# SUBSISTEMA 1: GESTIÓN DE INVENTARIO Y STOCK
# =============================================================================

class SubsistemaInventario:
    """Subsistema encargado de verificar disponibilidad y descontar stock en la BD."""

    def __init__(self, db_adapter: IDatabaseAdapter) -> None:
        self.db = db_adapter

    def validar_y_preparar_items(self, items_solicitados: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not items_solicitados:
            raise ErrorProcesoVenta("El carrito de compras está vacío.")

        items_validados: List[Dict[str, Any]] = []
        for item in items_solicitados:
            producto_id = int(item.get("producto_id", 0))
            cantidad = int(item.get("cantidad", 0))
            if cantidad <= 0:
                raise ErrorProcesoVenta("La cantidad de cada producto debe ser mayor a cero.")

            producto = self.db.obtener_producto(producto_id)
            if not producto or not producto.get("activo", 1):
                raise ErrorProcesoVenta(f"El producto con ID {producto_id} no está disponible.")

            stock_actual = int(producto["stock"])
            if stock_actual < cantidad:
                raise ErrorProcesoVenta(
                    f"Stock insuficiente para '{producto['nombre']}'. "
                    f"Disponible: {stock_actual}, solicitado: {cantidad}."
                )

            precio_unitario = round(float(producto["precio"]), 2)
            subtotal_item = round(precio_unitario * cantidad, 2)
            items_validados.append(
                {
                    "producto_id": producto_id,
                    "codigo": producto["codigo"],
                    "producto_nombre": producto["nombre"],
                    "cantidad": cantidad,
                    "precio_unitario": precio_unitario,
                    "subtotal": subtotal_item,
                }
            )
        return items_validados

    def descontar_stock(self, items_validados: List[Dict[str, Any]]) -> None:
        for item in items_validados:
            exito = self.db.descontar_stock_producto(item["producto_id"], item["cantidad"])
            if not exito:
                raise ErrorProcesoVenta(
                    f"No se pudo descontar el stock del producto '{item['producto_nombre']}'."
                )


# =============================================================================
# SUBSISTEMA 2: CÁLCULO TRIBUTARIO Y REGISTRO EN CRM (VENTAS / DETALLE_VENTAS)
# =============================================================================

class SubsistemaCRMTransacciones:
    """
    Subsistema financiero que calcula los importes de la Boleta Electrónica Peruana
    (Subtotal / Valor Venta, IGV 18% y Total) y persiste la transacción para el CRM.
    """

    TASA_IGV = 0.18

    def __init__(self, db_adapter: IDatabaseAdapter) -> None:
        self.db = db_adapter

    @classmethod
    def calcular_totales_boleta(cls, items_validados: List[Dict[str, Any]]) -> Dict[str, float]:
        total_bruto = round(sum(float(i["subtotal"]) for i in items_validados), 2)
        subtotal_base = round(total_bruto / (1.0 + cls.TASA_IGV), 2)
        igv = round(total_bruto - subtotal_base, 2)
        return {
            "subtotal": subtotal_base,
            "igv": igv,
            "total": total_bruto,
        }

    def registrar_transaccion(
        self,
        usuario_id: int,
        cliente_nombre: str,
        cliente_documento: str,
        metodo_pago: str,
        items_validados: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        totales = self.calcular_totales_boleta(items_validados)
        ventas_existentes = self.db.listar_ventas()
        correlativo = len(ventas_existentes) + 1
        numero_boleta = f"B001-{correlativo:06d}"

        cabecera = {
            "numero_boleta": numero_boleta,
            "usuario_id": usuario_id,
            "cliente_nombre": cliente_nombre.strip() or "Cliente Patitas Felices",
            "cliente_documento": cliente_documento.strip() or "00000000",
            "subtotal": totales["subtotal"],
            "igv": totales["igv"],
            "total": totales["total"],
            "metodo_pago": metodo_pago,
            "estado": "pagado",
        }
        return self.db.registrar_venta_y_detalles(cabecera, items_validados)


# =============================================================================
# SUBSISTEMA 3: GENERADOR DE BOLETA PDF EN MEMORIA (PDF 1.4 NATIVO)
# =============================================================================

class SubsistemaGeneradorPDF:
    """
    Subsistema de documentos: Construye un archivo PDF 1.4 estándar en memoria (bytes)
    con los datos de Clínica Patitas Felices, RUC, número de boleta, detalle e IGV.
    No requiere librerías binarias externas, garantizando portabilidad total.
    """

    CLINICA_NOMBRE = "CLINICA VETERINARIA PATITAS FELICES S.A.C."
    CLINICA_RUC = "20609876543"
    CLINICA_DIRECCION = "Lima, Peru - Atencion Veterinaria Integral"
    CLINICA_TELEFONO = "+51 990 853 697"

    @staticmethod
    def _limpiar_ascii(texto: str) -> str:
        normalizado = unicodedata.normalize("NFKD", str(texto))
        limpio = normalizado.encode("ascii", "ignore").decode("ascii")
        return limpio.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def construir_pdf_en_memoria(self, venta: Dict[str, Any]) -> bytes:
        fecha_emision = venta.get("creado_en") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lineas_pdf = [
            f"=== {self.CLINICA_NOMBRE} ===",
            f"RUC: {self.CLINICA_RUC}   |   WhatsApp: {self.CLINICA_TELEFONO}",
            f"Direccion: {self.CLINICA_DIRECCION}",
            "----------------------------------------------------------------------",
            f"BOLETA DE VENTA ELECTRONICA: {venta['numero_boleta']}",
            f"Fecha de Emision : {fecha_emision}",
            f"Cliente          : {venta['cliente_nombre']}",
            f"DNI / RUC        : {venta['cliente_documento']}",
            f"Metodo de Pago   : {venta.get('metodo_pago', 'Tarjeta / Yape')}",
            "----------------------------------------------------------------------",
            "CANT   DESCRIPCION                               P.UNIT     IMPORTE",
            "----------------------------------------------------------------------",
        ]

        for det in venta.get("detalles", []):
            nombre_corto = str(det["producto_nombre"])[:38].ljust(38)
            cant_str = str(det["cantidad"]).rjust(3)
            punit_str = f"S/ {float(det['precio_unitario']):6.2f}"
            sub_str = f"S/ {float(det['subtotal']):7.2f}"
            lineas_pdf.append(f" {cant_str}   {nombre_corto}  {punit_str}   {sub_str}")

        lineas_pdf.extend(
            [
                "----------------------------------------------------------------------",
                f"OP. GRAVADA (SUBTOTAL) : S/ {float(venta['subtotal']):.2f}",
                f"I.G.V. (18%)           : S/ {float(venta['igv']):.2f}",
                f"IMPORTE TOTAL PAGADO   : S/ {float(venta['total']):.2f}",
                "----------------------------------------------------------------------",
                "Gracias por confiar el cuidado de su mascota a Patitas Felices.",
                "Representacion impresa de la Boleta de Venta Electronica.",
            ]
        )

        comandos_texto = ["BT", "/F1 10 Tf", "50 770 Td", "14 TL"]
        for idx, linea in enumerate(lineas_pdf):
            segura = self._limpiar_ascii(linea)
            if idx == 0:
                comandos_texto.append(f"({segura}) Tj")
            else:
                comandos_texto.append(f"T* ({segura}) Tj")
        comandos_texto.append("ET")
        stream_content = "\n".join(comandos_texto).encode("ascii")

        objetos: List[bytes] = [
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
            (
                b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
            ),
            b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n",
            (
                f"5 0 obj\n<< /Length {len(stream_content)} >>\nstream\n".encode("ascii")
                + stream_content
                + b"\nendstream\nendobj\n"
            ),
        ]

        pdf = bytearray(b"%PDF-1.4\n")
        offsets: List[int] = [0]
        for obj in objetos:
            offsets.append(len(pdf))
            pdf.extend(obj)

        xref_pos = len(pdf)
        pdf.extend(f"xref\n0 {len(objetos) + 1}\n".encode("ascii"))
        pdf.extend(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            pdf.extend(f"{off:010d} 00000 n \n".encode("ascii"))

        pdf.extend(
            (
                f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref_pos}\n%%EOF\n"
            ).encode("ascii")
        )
        return bytes(pdf)


# =============================================================================
# FACHADA PRINCIPAL: TIENDAFACADE
# =============================================================================

class TiendaFacade:
    """
    Fachada principal para el Checkout de la Tienda Veterinaria.
    Oculta la complejidad de los 3 subsistemas detrás de `procesar_venta()`.
    """

    def __init__(
        self,
        db_adapter: IDatabaseAdapter,
        whatsapp_adapter: IWhatsAppNotificationAdapter | None = None,
    ) -> None:
        self.inventario = SubsistemaInventario(db_adapter)
        self.crm = SubsistemaCRMTransacciones(db_adapter)
        self.pdf_generator = SubsistemaGeneradorPDF()
        self.whatsapp = whatsapp_adapter or WhatsAppAdapter()

    def procesar_venta(
        self,
        usuario_id: int,
        cliente_nombre: str,
        cliente_documento: str,
        items: List[Dict[str, Any]],
        metodo_pago: str = "Tarjeta / Yape",
    ) -> Dict[str, Any]:
        # 1. Subsistema de Inventario: validar disponibilidad y descontar stock
        items_validados = self.inventario.validar_y_preparar_items(items)
        self.inventario.descontar_stock(items_validados)

        # 2. Subsistema CRM: calcular subtotal/IGV/total y guardar venta + detalles
        venta_registrada = self.crm.registrar_transaccion(
            usuario_id=usuario_id,
            cliente_nombre=cliente_nombre,
            cliente_documento=cliente_documento,
            metodo_pago=metodo_pago,
            items_validados=items_validados,
        )

        # 3. Subsistema Generador PDF: crear la boleta PDF en memoria
        pdf_bytes = self.pdf_generator.construir_pdf_en_memoria(venta_registrada)
        pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")

        # Integración adicional con WhatsAppAdapter para enviar constancia
        whatsapp_url = self.whatsapp.generar_enlace_boleta(
            numero_boleta=venta_registrada["numero_boleta"],
            cliente=venta_registrada["cliente_nombre"],
            total=float(venta_registrada["total"]),
        )

        return {
            "venta": venta_registrada,
            "pdf_base64": pdf_base64,
            "pdf_filename": f"Boleta_{venta_registrada['numero_boleta']}.pdf",
            "whatsapp_url": whatsapp_url,
        }
