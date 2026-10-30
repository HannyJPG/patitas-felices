/* ==========================================================================
   LÓGICA DE LA APLICACIÓN ADMINISTRATIVA INDEPENDIENTE
   Comparte autenticación y servicios con el backend existente sin duplicar usuarios.
   ========================================================================== */

import { API_BASE_URL, obtenerSesion, guardarSesion, peticionApi } from "./api-client.js";

(() => {
    const estadoConexion = document.getElementById("admin-estado-conexion");
    const badgeUsuario = document.getElementById("admin-usuario-activo");
    const inputDesde = document.getElementById("filtro-fecha-desde");
    const inputHasta = document.getElementById("filtro-fecha-hasta");
    const selectOrigen = document.getElementById("filtro-origen-datos");
    const btnAplicarFechas = document.getElementById("btn-aplicar-fechas");
    const btnRecargar = document.getElementById("btn-recargar-panel");

    const kpiIngresos = document.getElementById("kpi-ingresos");
    const kpiIngresosSub = document.getElementById("kpi-ingresos-sub");
    const kpiCitas = document.getElementById("kpi-citas");
    const kpiCitasSub = document.getElementById("kpi-citas-sub");
    const kpiPacientes = document.getElementById("kpi-pacientes");
    const kpiUsuarios = document.getElementById("kpi-usuarios");
    const kpiStockSub = document.getElementById("kpi-stock-sub");

    const graficoVentas = document.getElementById("grafico-ventas-barras");
    const etiquetaTotalGrafico = document.getElementById("etiqueta-total-grafico");
    const graficoTrafico = document.getElementById("grafico-trafico-barras");

    const inputBuscar = document.getElementById("excel-buscar");
    const selectAgrupacion = document.getElementById("excel-agrupacion");
    const selectCategoria = document.getElementById("excel-categoria");
    const selectPago = document.getElementById("excel-pago");
    const selectFilasPagina = document.getElementById("excel-filas-pagina");
    const theadExcel = document.getElementById("excel-thead");
    const tbodyExcel = document.getElementById("excel-tbody");
    const tfootExcel = document.getElementById("excel-tfoot");
    const infoPaginacion = document.getElementById("excel-info-paginacion");
    const indicadorPagina = document.getElementById("excel-indicador-pagina");
    const btnAnterior = document.getElementById("btn-pagina-anterior");
    const btnSiguiente = document.getElementById("btn-pagina-siguiente");
    const btnExportarCsv = document.getElementById("btn-exportar-csv");
    const btnExportarExcel = document.getElementById("btn-exportar-excel");

    const listaActividad = document.getElementById("lista-actividad-reciente");
    const contUsuarios = document.getElementById("contenedor-usuarios-admin");
    const contInventario = document.getElementById("contenedor-inventario-admin");

    const VENTAS_DEMO_INICIALES = [
        {
            id: 9001,
            numero_boleta: "B001-000841",
            creado_en: "2026-10-21 10:15:00",
            cliente_nombre: "Lucía Fernández",
            cliente_documento: "74859632",
            servicio_categoria: "Consulta general",
            concepto: "Consulta general + control de peso (Luna)",
            metodo_pago: "Yape / Plin",
            subtotal: 50.85,
            igv: 9.15,
            total: 60.00,
            estado: "pagado",
            es_demostracion: true
        },
        {
            id: 9002,
            numero_boleta: "B001-000842",
            creado_en: "2026-10-22 15:40:00",
            cliente_nombre: "Jorge Paredes",
            cliente_documento: "41258963",
            servicio_categoria: "Vacunación",
            concepto: "Vacuna Quíntuple Canina + desparasitación (Max)",
            metodo_pago: "Tarjeta Visa",
            subtotal: 93.22,
            igv: 16.78,
            total: 110.00,
            estado: "pagado",
            es_demostracion: true
        },
        {
            id: 9003,
            numero_boleta: "B001-000843",
            creado_en: "2026-10-24 11:20:00",
            cliente_nombre: "Mariana Quispe",
            cliente_documento: "70145896",
            servicio_categoria: "Farmacia",
            concepto: "Antipulgas Bravecto + Shampoo dermatológico",
            metodo_pago: "Yape / Plin",
            subtotal: 110.17,
            igv: 19.83,
            total: 130.00,
            estado: "pagado",
            es_demostracion: true
        },
        {
            id: 9004,
            numero_boleta: "B001-000844",
            creado_en: "2026-10-25 16:05:00",
            cliente_nombre: "Ricardo Salazar",
            cliente_documento: "45896321",
            servicio_categoria: "Nutrición",
            concepto: "Alimento Premium Adultos 3kg + vitaminas",
            metodo_pago: "Transferencia",
            subtotal: 125.42,
            igv: 22.58,
            total: 148.00,
            estado: "pagado",
            es_demostracion: true
        }
    ];

    const TRAFICO_DEMO_INICIAL = [
        { fecha: "2026-10-21", visitas: 42, consultas_web: 14, citas_registradas: 3, es_demostracion: true },
        { fecha: "2026-10-22", visitas: 51, consultas_web: 19, citas_registradas: 4, es_demostracion: true },
        { fecha: "2026-10-23", visitas: 38, consultas_web: 11, citas_registradas: 2, es_demostracion: true },
        { fecha: "2026-10-24", visitas: 64, consultas_web: 23, citas_registradas: 5, es_demostracion: true },
        { fecha: "2026-10-25", visitas: 72, consultas_web: 28, citas_registradas: 6, es_demostracion: true }
    ];

    let datosBrutos = {
        usuarios: [],
        mascotas: [],
        citas: [],
        productos: [],
        ventasReales: [],
        ventasDemo: VENTAS_DEMO_INICIALES,
        trafico: TRAFICO_DEMO_INICIAL
    };

    let columnaOrden = "fecha_iso";
    let direccionOrden = "desc";
    let paginaActual = 1;
    let filasExportablesActuales = [];

    function extraerFechaIso(fechaTexto) {
        return String(fechaTexto || "").slice(0, 10);
    }

    function formatearFechaLatam(fechaIso) {
        const limpia = extraerFechaIso(fechaIso);
        const partes = limpia.split("-");
        return partes.length === 3 ? `${partes[2]}/${partes[1]}/${partes[0]}` : limpia;
    }

    function normalizarVentasUnificadas() {
        const reales = (datosBrutos.ventasReales || []).map(v => {
            const detalles = v.detalles || [];
            const concepto = detalles.length
                ? detalles.map(d => `${d.cantidad}x ${d.producto_nombre}`).join(", ")
                : "Compra en tienda veterinaria";
            return {
                id: v.id,
                numero_boleta: v.numero_boleta,
                fecha_iso: extraerFechaIso(v.creado_en),
                cliente_nombre: v.cliente_nombre,
                cliente_documento: v.cliente_documento,
                servicio_categoria: "Farmacia",
                concepto,
                metodo_pago: v.metodo_pago || "Yape / Plin",
                subtotal: Number(v.subtotal || 0),
                igv: Number(v.igv || 0),
                total: Number(v.total || 0),
                estado: (v.estado || "pagado").toUpperCase(),
                es_demostracion: false,
                pdf_url: `${API_BASE_URL}/api/tienda/boleta/${v.id}/pdf`
            };
        });

        const demo = (datosBrutos.ventasDemo || []).map(d => ({
            id: d.id,
            numero_boleta: d.numero_boleta,
            fecha_iso: extraerFechaIso(d.creado_en),
            cliente_nombre: d.cliente_nombre,
            cliente_documento: d.cliente_documento,
            servicio_categoria: d.servicio_categoria || "Consulta general",
            concepto: d.concepto || "Atención veterinaria",
            metodo_pago: d.metodo_pago || "Yape / Plin",
            subtotal: Number(d.subtotal || 0),
            igv: Number(d.igv || 0),
            total: Number(d.total || 0),
            estado: (d.estado || "pagado").toUpperCase(),
            es_demostracion: true,
            pdf_url: null
        }));

        const origen = selectOrigen.value;
        if (origen === "reales") return reales;
        if (origen === "demo") return demo;
        return [...reales, ...demo];
    }

    function estaEnRangoFechas(fechaIso) {
        const desde = inputDesde.value || "2000-01-01";
        const hasta = inputHasta.value || "2099-12-31";
        return fechaIso >= desde && fechaIso <= hasta;
    }

    function obtenerVentasFiltradas() {
        const busqueda = (inputBuscar.value || "").trim().toLowerCase();
        const cat = selectCategoria.value;
        const pago = selectPago.value;

        return normalizarVentasUnificadas().filter(v => {
            if (!estaEnRangoFechas(v.fecha_iso)) return false;
            if (cat !== "todas" && v.servicio_categoria !== cat) return false;
            if (pago !== "todos" && !v.metodo_pago.toLowerCase().includes(pago.toLowerCase())) return false;
            if (busqueda) {
                const texto = `${v.numero_boleta} ${v.cliente_nombre} ${v.cliente_documento} ${v.servicio_categoria} ${v.concepto}`.toLowerCase();
                if (!texto.includes(busqueda)) return false;
            }
            return true;
        });
    }

    function actualizarIndicadoresYGraficos() {
        const ventasPeriodo = obtenerVentasFiltradas();
        const citasPeriodo = (datosBrutos.citas || []).filter(c => estaEnRangoFechas(extraerFechaIso(c.fecha)));

        const sumaIngresos = ventasPeriodo.reduce((acc, v) => acc + v.total, 0);
        const citasPendientes = citasPeriodo.filter(c => c.estado === "pendiente").length;
        const usuariosActivos = (datosBrutos.usuarios || []).filter(u => u.estado === "activo").length;
        const stockTotal = (datosBrutos.productos || []).reduce((acc, p) => acc + Number(p.stock || 0), 0);

        kpiIngresos.textContent = `S/ ${sumaIngresos.toFixed(2)}`;
        kpiIngresosSub.textContent = `${ventasPeriodo.length} comprobante(s) en el periodo`;
        kpiCitas.textContent = String(citasPeriodo.length);
        kpiCitasSub.textContent = `${citasPendientes} pendiente(s) de atención`;
        kpiPacientes.textContent = String((datosBrutos.mascotas || []).length);
        kpiUsuarios.textContent = `${usuariosActivos} / ${(datosBrutos.usuarios || []).length}`;
        kpiStockSub.textContent = `${stockTotal} unidades en farmacia`;
        etiquetaTotalGrafico.textContent = `S/ ${sumaIngresos.toFixed(2)}`;

        // Gráfico 1: Evolución de ventas por fecha
        const mapaPorFecha = new Map();
        for (const v of ventasPeriodo) {
            mapaPorFecha.set(v.fecha_iso, (mapaPorFecha.get(v.fecha_iso) || 0) + v.total);
        }
        const fechasOrdenadas = Array.from(mapaPorFecha.entries()).sort((a, b) => a[0].localeCompare(b[0]));
        graficoVentas.replaceChildren();
        const maxVenta = Math.max(...fechasOrdenadas.map(([, tot]) => tot), 1);

        if (!fechasOrdenadas.length) {
            const p = document.createElement("p");
            p.className = "admin-topbar-meta";
            p.textContent = "No hay ventas en el rango de fechas seleccionado.";
            graficoVentas.append(p);
        } else {
            for (const [fecha, totalDia] of fechasOrdenadas) {
                const col = document.createElement("div");
                col.className = "bar-col";
                const val = document.createElement("span");
                val.className = "bar-val";
                val.textContent = `S/ ${totalDia.toFixed(0)}`;
                const fill = document.createElement("div");
                fill.className = "bar-fill";
                fill.style.height = `${Math.max(Math.round((totalDia / maxVenta) * 130), 10)}px`;
                const lbl = document.createElement("span");
                lbl.className = "bar-date";
                lbl.textContent = formatearFechaLatam(fecha).slice(0, 5);
                col.append(val, fill, lbl);
                graficoVentas.append(col);
            }
        }

        // Gráfico 2: Tráfico de visitas y consultas por fecha
        const traficoFiltrado = (datosBrutos.trafico || []).filter(t => estaEnRangoFechas(t.fecha));
        graficoTrafico.replaceChildren();
        const maxVisitas = Math.max(...traficoFiltrado.map(t => Number(t.visitas || 0)), 1);
        for (const t of traficoFiltrado) {
            const col = document.createElement("div");
            col.className = "bar-col";
            const val = document.createElement("span");
            val.className = "bar-val";
            val.textContent = `${t.visitas} vis.`;
            const fill = document.createElement("div");
            fill.className = "bar-fill traffic";
            fill.style.height = `${Math.max(Math.round((t.visitas / maxVisitas) * 130), 10)}px`;
            const lbl = document.createElement("span");
            lbl.className = "bar-date";
            lbl.textContent = `${formatearFechaLatam(t.fecha).slice(0, 5)}${t.es_demostracion ? " (Demo)" : " (Hoy)"}`;
            col.append(val, fill, lbl);
            graficoTrafico.append(col);
        }

        // Actividad reciente
        listaActividad.replaceChildren();
        for (const c of citasPeriodo.slice(0, 5)) {
            const li = document.createElement("li");
            li.className = "activity-item";
            const izq = document.createElement("div");
            izq.innerHTML = `<strong>Cita #${c.id} · Mascota: ${c.mascota_nombre}</strong><div class="admin-topbar-meta">Propietario: ${c.propietario} · Servicio: ${c.servicio} · Fecha: ${c.fecha} ${c.hora}</div>`;
            const der = document.createElement("span");
            der.className = "badge-role";
            der.textContent = c.estado.toUpperCase();
            li.append(izq, der);
            listaActividad.append(li);
        }
    }

    function ordenarFilas(filas) {
        const factor = direccionOrden === "asc" ? 1 : -1;
        return [...filas].sort((a, b) => {
            const va = a[columnaOrden];
            const vb = b[columnaOrden];
            if (typeof va === "number" && typeof vb === "number") {
                return (va - vb) * factor;
            }
            return String(va ?? "").localeCompare(String(vb ?? ""), "es") * factor;
        });
    }

    function renderizarTablaExcel() {
        const ventasBase = obtenerVentasFiltradas();
        const modo = selectAgrupacion.value;
        const filasPorPagina = Number(selectFilasPagina.value || 10);

        let columnas = [];
        let filasParaTabla = [];

        if (modo === "fecha") {
            columnas = [
                { clave: "fecha_iso", titulo: "Fecha" },
                { clave: "operaciones", titulo: "N° Ventas", numerico: true },
                { clave: "subtotal", titulo: "Subtotal (S/)", numerico: true },
                { clave: "igv", titulo: "I.G.V. 18% (S/)", numerico: true },
                { clave: "total", titulo: "Total Acumulado (S/)", numerico: true }
            ];
            const mapa = new Map();
            for (const v of ventasBase) {
                const actual = mapa.get(v.fecha_iso) || {
                    fecha_iso: v.fecha_iso,
                    operaciones: 0,
                    subtotal: 0,
                    igv: 0,
                    total: 0
                };
                actual.operaciones += 1;
                actual.subtotal = Math.round((actual.subtotal + v.subtotal) * 100) / 100;
                actual.igv = Math.round((actual.igv + v.igv) * 100) / 100;
                actual.total = Math.round((actual.total + v.total) * 100) / 100;
                mapa.set(v.fecha_iso, actual);
            }
            filasParaTabla = Array.from(mapa.values());
        } else if (modo === "servicio") {
            const sumaGlobal = Math.max(ventasBase.reduce((acc, v) => acc + v.total, 0), 0.01);
            columnas = [
                { clave: "servicio_categoria", titulo: "Servicio / Categoría" },
                { clave: "operaciones", titulo: "N° Ventas", numerico: true },
                { clave: "subtotal", titulo: "Subtotal (S/)", numerico: true },
                { clave: "igv", titulo: "I.G.V. 18% (S/)", numerico: true },
                { clave: "total", titulo: "Total Acumulado (S/)", numerico: true },
                { clave: "participacion", titulo: "% Participación", numerico: true }
            ];
            const mapa = new Map();
            for (const v of ventasBase) {
                const actual = mapa.get(v.servicio_categoria) || {
                    servicio_categoria: v.servicio_categoria,
                    operaciones: 0,
                    subtotal: 0,
                    igv: 0,
                    total: 0,
                    participacion: 0
                };
                actual.operaciones += 1;
                actual.subtotal = Math.round((actual.subtotal + v.subtotal) * 100) / 100;
                actual.igv = Math.round((actual.igv + v.igv) * 100) / 100;
                actual.total = Math.round((actual.total + v.total) * 100) / 100;
                actual.participacion = Math.round((actual.total / sumaGlobal) * 1000) / 10;
                mapa.set(v.servicio_categoria, actual);
            }
            filasParaTabla = Array.from(mapa.values());
        } else {
            columnas = [
                { clave: "fecha_iso", titulo: "Fecha" },
                { clave: "numero_boleta", titulo: "Comprobante" },
                { clave: "cliente_nombre", titulo: "Cliente" },
                { clave: "cliente_documento", titulo: "DNI / RUC" },
                { clave: "servicio_categoria", titulo: "Servicio / Categoría" },
                { clave: "concepto", titulo: "Detalle" },
                { clave: "metodo_pago", titulo: "Medio de Pago" },
                { clave: "subtotal", titulo: "Subtotal (S/)", numerico: true },
                { clave: "igv", titulo: "I.G.V. 18% (S/)", numerico: true },
                { clave: "total", titulo: "Total (S/)", numerico: true },
                { clave: "origen_etiqueta", titulo: "Origen" }
            ];
            filasParaTabla = ventasBase.map(v => ({
                ...v,
                origen_etiqueta: v.es_demostracion ? "Demostración" : "Base de Datos"
            }));
        }

        if (!columnas.some(c => c.clave === columnaOrden)) {
            columnaOrden = columnas[0].clave;
        }

        const filasOrdenadas = ordenarFilas(filasParaTabla);
        filasExportablesActuales = { columnas, filas: filasOrdenadas };

        const totalPaginas = Math.max(Math.ceil(filasOrdenadas.length / filasPorPagina), 1);
        if (paginaActual > totalPaginas) paginaActual = totalPaginas;
        const inicio = (paginaActual - 1) * filasPorPagina;
        const filasPagina = filasOrdenadas.slice(inicio, inicio + filasPorPagina);

        // Encabezados con ordenamiento interactivo
        theadExcel.replaceChildren();
        const trHead = document.createElement("tr");
        for (const col of columnas) {
            const th = document.createElement("th");
            if (col.numerico) th.className = "num-cell";
            const flecha = columnaOrden === col.clave ? (direccionOrden === "asc" ? " ▲" : " ▼") : "";
            th.textContent = `${col.titulo}${flecha}`;
            th.addEventListener("click", () => {
                if (columnaOrden === col.clave) {
                    direccionOrden = direccionOrden === "asc" ? "desc" : "asc";
                } else {
                    columnaOrden = col.clave;
                    direccionOrden = "asc";
                }
                renderizarTablaExcel();
            });
            trHead.append(th);
        }
        theadExcel.append(trHead);

        // Cuerpo de la tabla
        tbodyExcel.replaceChildren();
        if (!filasPagina.length) {
            const trVacio = document.createElement("tr");
            const tdVacio = document.createElement("td");
            tdVacio.colSpan = columnas.length;
            tdVacio.textContent = "No se encontraron ventas con los filtros aplicados.";
            trVacio.append(tdVacio);
            tbodyExcel.append(trVacio);
        } else {
            for (const fila of filasPagina) {
                const tr = document.createElement("tr");
                for (const col of columnas) {
                    const td = document.createElement("td");
                    if (col.numerico) td.className = "num-cell";
                    const valor = fila[col.clave];
                    if (col.clave === "fecha_iso") {
                        td.textContent = formatearFechaLatam(valor);
                    } else if (["subtotal", "igv", "total"].includes(col.clave)) {
                        td.textContent = `S/ ${Number(valor).toFixed(2)}`;
                    } else if (col.clave === "participacion") {
                        td.textContent = `${Number(valor).toFixed(1)}%`;
                    } else if (col.clave === "origen_etiqueta") {
                        const badge = document.createElement("span");
                        badge.className = fila.es_demostracion ? "badge-demo" : "badge-role";
                        badge.textContent = valor;
                        td.append(badge);
                    } else {
                        td.textContent = String(valor ?? "");
                    }
                    tr.append(td);
                }
                tbodyExcel.append(tr);
            }
        }

        // Pie de tabla con totales calculados en vivo
        const sumaSubtotal = filasOrdenadas.reduce((acc, f) => acc + Number(f.subtotal || 0), 0);
        const sumaIgv = filasOrdenadas.reduce((acc, f) => acc + Number(f.igv || 0), 0);
        const sumaTotal = filasOrdenadas.reduce((acc, f) => acc + Number(f.total || 0), 0);

        tfootExcel.replaceChildren();
        const trFoot = document.createElement("tr");
        for (let i = 0; i < columnas.length; i += 1) {
            const col = columnas[i];
            const td = document.createElement("td");
            if (col.numerico) td.className = "num-cell";
            if (i === 0) {
                td.textContent = `TOTALES (${filasOrdenadas.length} reg.)`;
            } else if (col.clave === "subtotal") {
                td.textContent = `S/ ${sumaSubtotal.toFixed(2)}`;
            } else if (col.clave === "igv") {
                td.textContent = `S/ ${sumaIgv.toFixed(2)}`;
            } else if (col.clave === "total") {
                td.textContent = `S/ ${sumaTotal.toFixed(2)}`;
            } else if (col.clave === "participacion") {
                td.textContent = filasOrdenadas.length ? "100.0%" : "0.0%";
            } else {
                td.textContent = "";
            }
            trFoot.append(td);
        }
        tfootExcel.append(trFoot);

        // Controles de paginación
        const desdeReg = filasOrdenadas.length ? inicio + 1 : 0;
        const hastaReg = Math.min(inicio + filasPorPagina, filasOrdenadas.length);
        infoPaginacion.textContent = `Mostrando ${desdeReg}–${hastaReg} de ${filasOrdenadas.length} registro(s)`;
        indicadorPagina.textContent = `Página ${paginaActual} de ${totalPaginas}`;
        btnAnterior.disabled = paginaActual <= 1;
        btnSiguiente.disabled = paginaActual >= totalPaginas;
    }

    function exportarACsv() {
        const { columnas, filas } = filasExportablesActuales;
        if (!columnas?.length) return;
        const encabezados = columnas.map(c => `"${c.titulo}"`).join(",");
        const lineas = filas.map(f =>
            columnas
                .map(c => {
                    const v = c.clave === "fecha_iso" ? formatearFechaLatam(f[c.clave]) : (f[c.clave] ?? "");
                    return `"${String(v).replace(/"/g, '""')}"`;
                })
                .join(",")
        );
        const contenido = "\uFEFF" + [encabezados, ...lineas].join("\r\n");
        const blob = new Blob([contenido], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `Reporte_Ventas_Patitas_Felices_${selectAgrupacion.value}.csv`;
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 4000);
    }

    function exportarAExcel() {
        const { columnas, filas } = filasExportablesActuales;
        if (!columnas?.length) return;
        const ths = columnas.map(c => `<th style="background:#0B2545;color:#FFFFFF;padding:6px;">${c.titulo}</th>`).join("");
        const trs = filas
            .map(f => {
                const tds = columnas
                    .map(c => {
                        const v = c.clave === "fecha_iso" ? formatearFechaLatam(f[c.clave]) : (f[c.clave] ?? "");
                        return `<td style="border:1px solid #CBDAD2;padding:6px;">${v}</td>`;
                    })
                    .join("");
                return `<tr>${tds}</tr>`;
            })
            .join("");
        const htmlExcel = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel"><head><meta charset="UTF-8"></head><body><table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table></body></html>`;
        const blob = new Blob([htmlExcel], { type: "application/vnd.ms-excel;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `Reporte_Ventas_Patitas_Felices_${selectAgrupacion.value}.xls`;
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 4000);
    }

    function renderizarUsuariosEInventario() {
        contUsuarios.replaceChildren();
        for (const u of datosBrutos.usuarios || []) {
            const item = document.createElement("div");
            item.className = "activity-item";
            const info = document.createElement("div");
            info.innerHTML = `<strong>${u.nombre} (${u.rol.toUpperCase()})</strong><div class="admin-topbar-meta">${u.email} · Estado: ${u.estado.toUpperCase()}</div>`;
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = u.estado === "activo" ? "btn-admin btn-admin-outline" : "btn-admin btn-admin-primary";
            const siguienteEstado = u.estado === "activo" ? "inactivo" : "activo";
            btn.textContent = u.estado === "activo" ? "Suspender acceso" : "Activar acceso";
            btn.addEventListener("click", async () => {
                btn.disabled = true;
                try {
                    await peticionApi(`/api/admin/usuarios/${u.id}/estado`, {
                        method: "PATCH",
                        body: JSON.stringify({ estado: siguienteEstado })
                    });
                    await cargarDatosPanel();
                } finally {
                    btn.disabled = false;
                }
            });
            item.append(info, btn);
            contUsuarios.append(item);
        }

        contInventario.replaceChildren();
        for (const p of datosBrutos.productos || []) {
            const item = document.createElement("div");
            item.className = "activity-item";
            item.innerHTML = `<div><strong>${p.nombre}</strong><div class="admin-topbar-meta">${p.codigo} · ${p.categoria} · S/ ${Number(p.precio).toFixed(2)}</div></div><span class="badge-role">${p.stock} unid.</span>`;
            contInventario.append(item);
        }
    }

    async function asegurarSesionAdmin() {
        const sesion = obtenerSesion();
        if (sesion?.token && sesion?.usuario?.rol && sesion.usuario.rol !== "admin") {
            const rutaRol = "/perfil";
            estadoConexion.textContent = `Acceso reservado para administración. Redirigiendo a tu espacio (${rutaRol})...`;
            setTimeout(() => {
                window.location.href = rutaRol;
            }, 900);
            return null;
        }
        if (sesion?.token && sesion?.usuario?.rol === "admin") {
            return sesion;
        }
        const loginAdmin = await peticionApi("/api/auth/login", {
            method: "POST",
            body: JSON.stringify({
                email: "admin@patitasfelices.pe",
                password: "admin123"
            })
        });
        guardarSesion(loginAdmin);
        return loginAdmin;
    }

    async function cargarDatosPanel() {
        try {
            const sesion = await asegurarSesionAdmin();
            if (!sesion) return;
            badgeUsuario.textContent = `${sesion.usuario.nombre} · Administración`;
            const data = await peticionApi("/api/admin/crm");
            datosBrutos = {
                usuarios: data.usuarios || [],
                mascotas: data.mascotas || [],
                citas: data.citas || [],
                productos: data.productos || [],
                ventasReales: data.ventas || [],
                ventasDemo: data.ventas_referencia_demo || [],
                trafico: data.trafico_periodo || []
            };
            estadoConexion.textContent = "Datos sincronizados en tiempo real con la clínica.";
            actualizarIndicadoresYGraficos();
            renderizarTablaExcel();
            renderizarUsuariosEInventario();
        } catch (error) {
            estadoConexion.textContent = `Mostrando datos de demostración locales (${error.message}).`;
            actualizarIndicadoresYGraficos();
            renderizarTablaExcel();
            renderizarUsuariosEInventario();
        }
    }

    // Eventos de filtros y controles
    btnAplicarFechas.addEventListener("click", () => {
        paginaActual = 1;
        actualizarIndicadoresYGraficos();
        renderizarTablaExcel();
    });

    selectOrigen.addEventListener("change", () => {
        paginaActual = 1;
        actualizarIndicadoresYGraficos();
        renderizarTablaExcel();
    });

    document.querySelectorAll("[data-rango-rapido]").forEach(boton => {
        boton.addEventListener("click", () => {
            const tipo = boton.getAttribute("data-rango-rapido");
            if (tipo === "todo") {
                inputDesde.value = "2026-01-01";
                inputHasta.value = "2026-12-31";
            } else if (tipo === "7dias") {
                inputDesde.value = "2026-10-20";
                inputHasta.value = "2026-10-27";
            } else if (tipo === "hoy") {
                inputDesde.value = "2026-10-27";
                inputHasta.value = "2026-10-27";
            }
            paginaActual = 1;
            actualizarIndicadoresYGraficos();
            renderizarTablaExcel();
        });
    });

    [inputBuscar, selectAgrupacion, selectCategoria, selectPago, selectFilasPagina].forEach(ctrl => {
        ctrl.addEventListener("input", () => {
            paginaActual = 1;
            renderizarTablaExcel();
        });
        ctrl.addEventListener("change", () => {
            paginaActual = 1;
            renderizarTablaExcel();
        });
    });

    btnAnterior.addEventListener("click", () => {
        if (paginaActual > 1) {
            paginaActual -= 1;
            renderizarTablaExcel();
        }
    });
    btnSiguiente.addEventListener("click", () => {
        paginaActual += 1;
        renderizarTablaExcel();
    });

    btnExportarCsv.addEventListener("click", exportarACsv);
    btnExportarExcel.addEventListener("click", exportarAExcel);
    btnRecargar.addEventListener("click", cargarDatosPanel);

    // Gestión de Alta de Personal (Doctor / Admin)
    const btnToggleAlta = document.getElementById("btn-toggle-alta-personal");
    const panelAlta = document.getElementById("panel-alta-personal");
    const formAlta = document.getElementById("form-alta-personal");
    const btnCancelarAlta = document.getElementById("btn-cancelar-alta");
    const btnSubmitAlta = document.getElementById("btn-submit-alta");
    const alertaAltaError = document.getElementById("alerta-alta-error");
    const alertaAltaSuccess = document.getElementById("alerta-alta-success");

    const selectAltaRol = document.getElementById("alta-rol");
    const campoCmvp = document.getElementById("campo-alta-cmvp");
    const campoEspecialidad = document.getElementById("campo-alta-especialidad");

    if (selectAltaRol) {
        selectAltaRol.addEventListener("change", () => {
            const esDoctor = selectAltaRol.value === "doctor";
            if (campoCmvp) campoCmvp.style.display = esDoctor ? "block" : "none";
            if (campoEspecialidad) campoEspecialidad.style.display = esDoctor ? "block" : "none";
        });
    }

    if (btnToggleAlta && panelAlta) {
        btnToggleAlta.addEventListener("click", () => {
            const visible = panelAlta.style.display === "block";
            panelAlta.style.display = visible ? "none" : "block";
            if (!visible) {
                document.getElementById("alta-nombre")?.focus();
            }
        });
    }

    if (btnCancelarAlta && panelAlta) {
        btnCancelarAlta.addEventListener("click", () => {
            panelAlta.style.display = "none";
            formAlta?.reset();
            if (alertaAltaError) alertaAltaError.style.display = "none";
            if (alertaAltaSuccess) alertaAltaSuccess.style.display = "none";
        });
    }

    if (formAlta) {
        formAlta.addEventListener("submit", async evento => {
            evento.preventDefault();
            if (alertaAltaError) alertaAltaError.style.display = "none";
            if (alertaAltaSuccess) alertaAltaSuccess.style.display = "none";

            const nombre = document.getElementById("alta-nombre")?.value?.trim() || "";
            const rol = selectAltaRol?.value || "doctor";
            const email = document.getElementById("alta-email")?.value?.trim() || "";
            const password = document.getElementById("alta-password")?.value || "";
            const telefono = document.getElementById("alta-telefono")?.value?.trim() || "";
            const cmvp = document.getElementById("alta-cmvp")?.value?.trim() || "CMVP-00000";
            const especialidad = document.getElementById("alta-especialidad")?.value?.trim() || "Medicina General";

            if (!nombre || !email || !password) {
                if (alertaAltaError) {
                    alertaAltaError.textContent = "Por favor completa el nombre, correo corporativo y contraseña.";
                    alertaAltaError.style.display = "block";
                }
                return;
            }

            if (password.length < 6) {
                if (alertaAltaError) {
                    alertaAltaError.textContent = "La contraseña provisional debe tener al menos 6 caracteres.";
                    alertaAltaError.style.display = "block";
                }
                return;
            }

            if (btnSubmitAlta) btnSubmitAlta.disabled = true;

            try {
                const res = await peticionApi("/api/admin/usuarios", {
                    method: "POST",
                    body: JSON.stringify({
                        nombre,
                        rol,
                        email,
                        password,
                        telefono,
                        cmvp,
                        especialidad,
                    })
                });

                if (alertaAltaSuccess) {
                    alertaAltaSuccess.textContent = `Cuenta creada exitosamente para ${res.usuario.nombre} (${res.usuario.rol.toUpperCase()}).`;
                    alertaAltaSuccess.style.display = "block";
                }

                formAlta.reset();
                await cargarDatosPanel();

                setTimeout(() => {
                    if (panelAlta) panelAlta.style.display = "none";
                    if (alertaAltaSuccess) alertaAltaSuccess.style.display = "none";
                }, 1500);

            } catch (err) {
                if (alertaAltaError) {
                    alertaAltaError.textContent = err.message || "Error al dar de alta al usuario.";
                    alertaAltaError.style.display = "block";
                }
            } finally {
                if (btnSubmitAlta) btnSubmitAlta.disabled = false;
            }
        });
    }

    // Navegación lateral entre secciones
    document.querySelectorAll("[data-nav-target]").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll("[data-nav-target]").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            const destino = btn.getAttribute("data-nav-target");
            if (destino === "todo") {
                window.scrollTo({ top: 0, behavior: "smooth" });
            } else {
                document.getElementById(destino)?.scrollIntoView({ behavior: "smooth" });
            }
        });
    });

    actualizarIndicadoresYGraficos();
    renderizarTablaExcel();
    cargarDatosPanel();
})();
