"""Repositorio de Tienda, Productos, Facturación y CRM Financiero (dbo.productos, dbo.Factura, dbo.Pago, dbo.detalle_ventas)."""
from __future__ import annotations

import secrets
from typing import Any, Dict, List, Optional

from ..sqlserver_schema import ErrorConsultaSQLServer, SQLServerConnection, sql_lit
from .shared import separar_nombres_apellidos


class TiendaRepositoryMixin:
    """Operaciones SQL Server de catálogo, stock atómico, emisión de boletas y resumen financiero."""

    conn: SQLServerConnection

    # --- Catálogo de productos, stock y consultas de compras ---
    def listar_compras_usuario(self, usuario_id: int) -> List[Dict[str, Any]]:
        owner_id = self._owner_id_for_user(usuario_id, create=False)
        if owner_id is None:
            return []
        return self._query_facturas(
            f"WHERE f.id_dueno = {owner_id} AND f.Id_cita IS NULL ORDER BY f.id_factura DESC"
        )

    def listar_productos(self, solo_activos: bool = True) -> List[Dict[str, Any]]:
        where_clause = "WHERE activo = 1 " if solo_activos else ""
        return self.conn.query_json(
            f"""
            SELECT id, codigo, nombre, categoria, descripcion,
                   CAST(precio AS FLOAT) AS precio, stock, CAST(activo AS INT) AS activo
            FROM dbo.productos
            {where_clause}ORDER BY id ASC
            """
        )

    def obtener_producto(self, producto_id: int) -> Optional[Dict[str, Any]]:
        return self.conn.query_one(
            f"""
            SELECT TOP 1 id, codigo, nombre, categoria, descripcion,
                         CAST(precio AS FLOAT) AS precio, stock, CAST(activo AS INT) AS activo
            FROM dbo.productos
            WHERE id = {int(producto_id)}
            """
        )

    def descontar_stock_producto(self, producto_id: int, cantidad: int) -> bool:
        updated = self.conn.scalar(
            f"""
            UPDATE dbo.productos
            SET stock = stock - {int(cantidad)}
            OUTPUT INSERTED.id
            WHERE id = {int(producto_id)} AND stock >= {int(cantidad)}
            """
        )
        return bool(updated.strip())

    def registrar_venta_y_detalles(
        self, cabecera: Dict[str, Any], detalles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        raw_uid = cabecera.get("usuario_id")
        uid = int(raw_uid) if raw_uid is not None else None
        owner_id = self._owner_id_for_user(uid) if uid is not None else None
        doc_cliente = str(cabecera.get("cliente_documento") or "").strip()
        nombre_cliente = str(cabecera.get("cliente_nombre") or "Cliente Patitas Felices").strip()
        if owner_id is None:
            existing_dueno = (
                self.conn.query_one(
                    f"SELECT TOP 1 id_dueno, usuario_id FROM dbo.Dueno WHERE dni = {sql_lit(doc_cliente)}"
                )
                if doc_cliente and doc_cliente != "00000000"
                else None
            )
            if existing_dueno and existing_dueno.get("usuario_id") is None:
                owner_id = int(existing_dueno["id_dueno"])
            else:
                nombres_guest, apellidos_guest = separar_nombres_apellidos(
                    nombre_cliente, default_nombre="Cliente"
                )
                dni_guest = (
                    doc_cliente
                    if (doc_cliente and doc_cliente != "00000000" and not existing_dueno)
                    else f"EXT{secrets.token_hex(4).upper()}"
                )
                tipo_guest = "RUC" if len(doc_cliente) == 11 else "DNI"
                owner_id = int(
                    self.conn.scalar(
                        f"""
                        INSERT INTO dbo.Dueno (usuario_id, dni, tipo_documento, nombres, apellidos, telefono)
                        OUTPUT INSERTED.id_dueno
                        VALUES (NULL, {sql_lit(dni_guest)}, {sql_lit(tipo_guest)}, {sql_lit(nombres_guest)}, {sql_lit(apellidos_guest)}, '')
                        """
                    )
                )
        update_dueno_flag = 0
        update_dueno_dni = ""
        update_dueno_tipo = "DNI"
        if owner_id is not None and doc_cliente and doc_cliente != "00000000":
            current_dueno = self.conn.query_one(
                f"SELECT TOP 1 dni FROM dbo.Dueno WHERE id_dueno = {owner_id}"
            )
            if current_dueno and (
                str(current_dueno["dni"]).startswith("CLI")
                or str(current_dueno["dni"]).startswith("EXT")
            ):
                dup_dni = self.conn.query_one(
                    "SELECT TOP 1 1 AS ok FROM dbo.Dueno WHERE dni = @dni AND id_dueno <> @oid",
                    params={"dni": doc_cliente, "oid": int(owner_id)},
                )
                if not dup_dni:
                    update_dueno_flag = 1
                    update_dueno_dni = doc_cliente
                    update_dueno_tipo = "RUC" if len(doc_cliente) == 11 else "DNI"

        number_text = str(cabecera["numero_boleta"])
        series, _, suffix = number_text.partition("-")
        series = series or "B001"
        number = int(suffix or "1")
        if self.conn.query_one(
            f"SELECT TOP 1 1 AS ok FROM dbo.Factura WHERE serie = {sql_lit(series)} AND numero = {number}"
        ):
            raise ValueError(f"El numero de boleta {number_text} ya existe.")

        estado_cap = str(cabecera.get("estado", "pagado")).capitalize()
        metodo_pago = str(cabecera.get("metodo_pago", "Tarjeta / Yape"))
        descontar_stock = bool(cabecera.get("descontar_stock", False))
        stock_sql_lines = []
        detalles_sql_lines = []
        for detail in detalles:
            pid = int(detail["producto_id"])
            qty = int(detail["cantidad"])
            if descontar_stock:
                stock_sql_lines.append(
                    f"UPDATE dbo.productos SET stock = stock - {qty} "
                    f"WHERE id = {pid} AND activo = 1 AND stock >= {qty};\n"
                    f"                        IF @@ROWCOUNT = 0 BEGIN ROLLBACK TRANSACTION; THROW 50003, N'STOCK_INSUFICIENTE', 1; END;"
                )
            detalles_sql_lines.append(
                "INSERT INTO dbo.detalle_ventas (id_factura, producto_id, cantidad, precio_unitario, subtotal) "
                f"VALUES (@invoice_id, {pid}, {qty}, "
                f"{float(detail['precio_unitario'])}, {float(detail['subtotal'])});"
            )
        stock_block = "\n                        ".join(stock_sql_lines)
        detalles_block = "\n                        ".join(detalles_sql_lines)
        try:
            invoice_id = int(
                self.conn.scalar(
                    """
                    SET XACT_ABORT ON;
                    BEGIN TRY
                        BEGIN TRANSACTION;
                        IF @update_dueno = 1
                        BEGIN
                            UPDATE dbo.Dueno
                            SET dni = @new_dni, tipo_documento = @new_tipo_doc
                            WHERE id_dueno = @owner_id;
                        END;

                        IF EXISTS (
                            SELECT 1 FROM dbo.Factura WITH (UPDLOCK, HOLDLOCK)
                            WHERE serie = @series AND numero = @number
                        )
                        BEGIN
                            ROLLBACK TRANSACTION;
                            THROW 50002, N'BOLETA_DUPLICADA', 1;
                        END;

                        """
                    + stock_block
                    + """

                        INSERT INTO dbo.Factura (id_dueno, tipo, serie, numero, subtotal, igv, total, estado)
                        VALUES (@owner_id, 'Boleta', @series, @number, @subtotal, @igv, @total, @estado_cap);
                        DECLARE @invoice_id INT = CAST(SCOPE_IDENTITY() AS INT);

                        """
                    + detalles_block
                    + """

                        INSERT INTO dbo.Pago (id_factura, metodo_pago, monto, estado)
                        VALUES (@invoice_id, @metodo_pago, @total, @estado_cap);

                        COMMIT TRANSACTION;
                        SELECT CAST(@invoice_id AS VARCHAR(20)) AS id;
                    END TRY
                    BEGIN CATCH
                        IF @@TRANCOUNT > 0
                            ROLLBACK TRANSACTION;
                        THROW;
                    END CATCH
                    """,
                    params={
                        "owner_id": owner_id,
                        "update_dueno": update_dueno_flag,
                        "new_dni": update_dueno_dni,
                        "new_tipo_doc": update_dueno_tipo,
                        "series": series,
                        "number": number,
                        "subtotal": float(cabecera["subtotal"]),
                        "igv": float(cabecera["igv"]),
                        "total": float(cabecera["total"]),
                        "estado_cap": estado_cap,
                        "metodo_pago": metodo_pago,
                    },
                )
            )
        except ErrorConsultaSQLServer as exc:
            if getattr(exc, "native_err", 0) == 50002 or "BOLETA_DUPLICADA" in str(exc):
                raise ValueError(f"El numero de boleta {number_text} ya existe.") from exc
            if getattr(exc, "native_err", 0) == 50003 or "STOCK_INSUFICIENTE" in str(exc):
                raise ValueError("Stock insuficiente o producto no disponible para completar la venta.") from exc
            raise
        return self._factura_row(invoice_id) or {"id": invoice_id}

    def _query_facturas(self, where_order_sql: str) -> List[Dict[str, Any]]:
        facturas = self.conn.query_json(
            f"""
            SELECT
                f.id_factura,
                f.id_factura AS id,
                f.Id_cita,
                f.id_dueno,
                d.usuario_id,
                f.tipo,
                f.serie,
                f.numero,
                (f.serie + '-' + RIGHT('000000' + CAST(f.numero AS VARCHAR(10)), 6)) AS numero_boleta,
                COALESCE(u.nombre, LTRIM(RTRIM(d.nombres + ' ' + d.apellidos)), 'Cliente Patitas Felices') AS cliente_nombre,
                COALESCE(CASE WHEN d.dni LIKE 'CLI%' OR d.dni LIKE 'EXT%' THEN NULL ELSE d.dni END, '00000000') AS cliente_documento,
                CONVERT(VARCHAR(19), f.fecha_emision, 120) AS fecha_emision,
                CONVERT(VARCHAR(19), f.fecha_emision, 120) AS creado_en,
                CAST(f.subtotal AS FLOAT) AS subtotal,
                CAST(f.igv AS FLOAT) AS igv,
                CAST(f.total AS FLOAT) AS total,
                COALESCE(pg.metodo_pago, 'Tarjeta / Yape') AS metodo_pago,
                f.estado,
                f.pdf_url
            FROM dbo.Factura f
            LEFT JOIN dbo.Dueno d ON d.id_dueno = f.id_dueno
            LEFT JOIN dbo.usuarios u ON u.id = d.usuario_id
            LEFT JOIN dbo.Pago pg ON pg.id_pago = (
                SELECT MAX(p2.id_pago) FROM dbo.Pago p2 WHERE p2.id_factura = f.id_factura
            )
            {where_order_sql}
            """
        )
        if not facturas:
            return []
        inv_ids = [int(f["id_factura"]) for f in facturas]
        ids_csv = ",".join(str(i) for i in inv_ids)
        detalles_rows = self.conn.query_json(
            f"""
            SELECT
                dv.id,
                dv.id_factura,
                dv.producto_id,
                pr.nombre AS producto_nombre,
                dv.cantidad,
                CAST(dv.precio_unitario AS FLOAT) AS precio_unitario,
                CAST(dv.subtotal AS FLOAT) AS subtotal
            FROM dbo.detalle_ventas dv
            JOIN dbo.productos pr ON pr.id = dv.producto_id
            WHERE dv.id_factura IN ({ids_csv})
            ORDER BY dv.id
            """
        )
        detalles_map: Dict[int, List[Dict[str, Any]]] = {iid: [] for iid in inv_ids}
        for d in detalles_rows:
            det_dict = dict(d)
            detalles_map[int(det_dict["id_factura"])].append(det_dict)
        for f in facturas:
            f["detalles"] = detalles_map.get(int(f["id_factura"]), [])
        return facturas

    def _factura_row(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        items = self._query_facturas(f"WHERE f.id_factura = {int(invoice_id)}")
        return items[0] if items else None

    def obtener_venta_por_id(self, venta_id: int) -> Optional[Dict[str, Any]]:
        return self._factura_row(int(venta_id))

    def obtener_siguiente_numero_boleta(self, serie: str = "B001") -> int:
        siguiente = self.conn.scalar(
            "SELECT CAST(ISNULL(MAX(numero), 0) + 1 AS VARCHAR(20)) FROM dbo.Factura WHERE serie = @serie",
            params={"serie": str(serie or "B001").strip()},
        )
        return int(siguiente) if siguiente.strip().isdigit() else 1

    def obtener_resumen_crm(self) -> Dict[str, Any]:
        """Calcula indicadores clave del CRM mediante agregación SQL directa sin cargar todas las filas."""
        fila = self.conn.query_one(
            """
            SELECT
                (SELECT COUNT(*) FROM dbo.usuarios) AS total_usuarios,
                (SELECT COUNT(*) FROM dbo.usuarios WHERE LOWER(estado) = 'activo') AS usuarios_activos,
                (SELECT COUNT(*) FROM dbo.Veterinario) AS total_veterinarios,
                (SELECT COUNT(*) FROM dbo.Paciente WHERE estado <> 'Eliminado') AS total_pacientes,
                (SELECT COUNT(*) FROM dbo.Cita) AS total_citas,
                (SELECT COUNT(*) FROM dbo.Cita WHERE LOWER(estado) = 'pendiente') AS citas_pendientes,
                (SELECT COUNT(*) FROM dbo.Factura) AS total_ventas,
                (SELECT CAST(ISNULL(SUM(total), 0) AS FLOAT) FROM dbo.Factura) AS ingresos_totales,
                (SELECT ISNULL(SUM(stock), 0) FROM dbo.productos WHERE activo = 1) AS stock_total_unidades
            """
        ) or {}
        return {
            "total_usuarios": int(fila.get("total_usuarios") or 0),
            "usuarios_activos": int(fila.get("usuarios_activos") or 0),
            "total_veterinarios": int(fila.get("total_veterinarios") or 0),
            "total_pacientes": int(fila.get("total_pacientes") or 0),
            "total_citas": int(fila.get("total_citas") or 0),
            "citas_pendientes": int(fila.get("citas_pendientes") or 0),
            "total_ventas": int(fila.get("total_ventas") or 0),
            "ingresos_totales": round(float(fila.get("ingresos_totales") or 0.0), 2),
            "stock_total_unidades": int(fila.get("stock_total_unidades") or 0),
        }

    def listar_ventas_paginadas(
        self, page: int = 1, page_size: int = 25
    ) -> Dict[str, Any]:
        pagina = max(1, int(page))
        tamano = max(1, min(200, int(page_size)))
        offset = (pagina - 1) * tamano
        total_str = self.conn.scalar("SELECT CAST(COUNT(*) AS VARCHAR(20)) FROM dbo.Factura")
        total = int(total_str) if total_str.strip().isdigit() else 0
        items = self._query_facturas(
            f"ORDER BY f.id_factura DESC OFFSET {offset} ROWS FETCH NEXT {tamano} ROWS ONLY"
        )
        return {
            "items": items,
            "page": pagina,
            "page_size": tamano,
            "total": total,
            "total_pages": max(1, (total + tamano - 1) // tamano),
        }

    def listar_ventas(self) -> List[Dict[str, Any]]:
        return self._query_facturas("ORDER BY f.id_factura DESC")
