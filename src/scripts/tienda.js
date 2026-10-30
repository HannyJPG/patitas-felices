import { peticionApi, obtenerSesion, guardarSesion, descargarPdfDesdeBase64 } from "./api-client.js";

(() => {
    const gridProductos = document.getElementById("grid-productos");
    if (!gridProductos) return;

    const listaPedido = document.getElementById("lista-pedido");
    const elSubtotal = document.getElementById("resumen-subtotal");
    const elIgv = document.getElementById("resumen-igv");
    const elTotal = document.getElementById("resumen-total");
    const formCheckout = document.getElementById("formulario-checkout");
    const alertaCheckout = document.getElementById("alerta-checkout");
    const btnVaciar = document.getElementById("btn-vaciar-pedido");
    const seccionBoleta = document.getElementById("resultado-boleta");
    const elNumeroBoleta = document.getElementById("boleta-numero");
    const btnDescargarPdf = document.getElementById("btn-descargar-pdf");
    const enlaceWhatsappBoleta = document.getElementById("enlace-whatsapp-boleta");
    const estadoCatalogo = document.getElementById("estado-catalogo");

    // Elementos de identificación del cliente
    const inputNombre = document.getElementById("cliente-nombre");
    const selectTipoDoc = document.getElementById("tipo-documento");
    const inputDocumento = document.getElementById("cliente-documento");
    const badgeDocEstado = document.getElementById("badge-doc-estado");
    const notaDocumento = document.getElementById("nota-documento");
    const avisoRequiereLogin = document.getElementById("aviso-requiere-login");
    const btnLoginDesdeTienda = document.getElementById("btn-login-desde-tienda");
    const btnProcesarVenta = document.getElementById("btn-procesar-venta");

    const carrito = new Map();
    let ultimoPdfBase64 = null;
    let ultimoNombrePdf = "Boleta_Patitas_Felices.pdf";

    function ajustarMascaraDocumento() {
        if (!selectTipoDoc || !inputDocumento || inputDocumento.readOnly) return;
        const tipo = selectTipoDoc.value;
        if (tipo === "DNI") {
            inputDocumento.maxLength = 8;
            inputDocumento.placeholder = "Ingresa los 8 dígitos de tu DNI";
        } else {
            inputDocumento.maxLength = 11;
            inputDocumento.placeholder = "Ingresa los 11 dígitos de tu RUC";
        }
    }

    function actualizarEstadoUsuarioEnFormulario() {
        const sesion = obtenerSesion();
        const u = sesion?.usuario;

        if (!u) {
            if (avisoRequiereLogin) avisoRequiereLogin.classList.remove("d-none");
            if (inputNombre) {
                inputNombre.value = "";
                inputNombre.placeholder = "Inicia sesión para comprar";
            }
            if (inputDocumento) {
                inputDocumento.value = "";
                inputDocumento.placeholder = "Inicia sesión para comprar";
                inputDocumento.readOnly = true;
            }
            if (selectTipoDoc) selectTipoDoc.disabled = true;
            if (btnProcesarVenta) btnProcesarVenta.disabled = true;
            return;
        }

        if (avisoRequiereLogin) avisoRequiereLogin.classList.add("d-none");
        if (btnProcesarVenta) btnProcesarVenta.disabled = false;

        // 1. Nombre bloqueado: siempre el nombre real de la cuenta
        if (inputNombre) {
            inputNombre.value = u.nombre || "Cliente Patitas Felices";
            inputNombre.readOnly = true;
            inputNombre.style.backgroundColor = "#f8fafc";
            inputNombre.style.cursor = "not-allowed";
        }

        // 2. DNI o RUC
        const tieneDoc = Boolean(u.documento && String(u.documento).trim());
        if (tieneDoc) {
            const docVal = String(u.documento).trim();
            const tipoVal = u.tipo_documento || (docVal.length === 11 ? "RUC" : "DNI");
            if (selectTipoDoc) {
                selectTipoDoc.value = tipoVal;
                selectTipoDoc.disabled = true;
            }
            if (inputDocumento) {
                inputDocumento.value = docVal;
                inputDocumento.readOnly = true;
                inputDocumento.style.backgroundColor = "#f8fafc";
                inputDocumento.style.cursor = "not-allowed";
            }
            if (badgeDocEstado) {
                badgeDocEstado.textContent = "Verificado";
                badgeDocEstado.className = "badge bg-success-subtle text-success border border-success-subtle small";
            }
            if (notaDocumento) {
                notaDocumento.textContent = "Identificador único verificado en tu cuenta (no modificable).";
            }
        } else {
            if (selectTipoDoc) selectTipoDoc.disabled = false;
            if (inputDocumento) {
                inputDocumento.readOnly = false;
                inputDocumento.style.backgroundColor = "";
                inputDocumento.style.cursor = "text";
                ajustarMascaraDocumento();
            }
            if (badgeDocEstado) {
                badgeDocEstado.textContent = "Por vincular";
                badgeDocEstado.className = "badge bg-light text-secondary border small";
            }
            if (notaDocumento) {
                notaDocumento.textContent = "Al realizar tu compra, este identificador quedará registrado permanentemente en tu cuenta.";
            }
        }
    }

    inputDocumento?.addEventListener("input", e => {
        if (!inputDocumento.readOnly) {
            e.target.value = e.target.value.replace(/\D/g, "");
        }
    });

    selectTipoDoc?.addEventListener("change", () => {
        ajustarMascaraDocumento();
        inputDocumento?.focus();
    });

    btnLoginDesdeTienda?.addEventListener("click", () => {
        const modalEl = document.getElementById("modalLogin");
        if (modalEl && window.bootstrap?.Modal) {
            window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
    });

    window.addEventListener("storage", actualizarEstadoUsuarioEnFormulario);
    window.addEventListener("sesion_actualizada", actualizarEstadoUsuarioEnFormulario);

    function calcularTotales() {
        let total = 0;
        for (const item of carrito.values()) {
            total += item.precio * item.cantidad;
        }
        const totalRedondeado = Math.round(total * 100) / 100;
        const subtotal = Math.round((totalRedondeado / 1.18) * 100) / 100;
        const igv = Math.round((totalRedondeado - subtotal) * 100) / 100;
        elSubtotal.textContent = `S/ ${subtotal.toFixed(2)}`;
        elIgv.textContent = `S/ ${igv.toFixed(2)}`;
        elTotal.textContent = `S/ ${totalRedondeado.toFixed(2)}`;
    }

    function renderizarCarrito() {
        listaPedido.replaceChildren();
        if (carrito.size === 0) {
            const p = document.createElement("p");
            p.className = "small-note mb-0";
            p.textContent = "Aún no has seleccionado productos del catálogo.";
            listaPedido.append(p);
            calcularTotales();
            return;
        }

        const ul = document.createElement("ul");
        ul.className = "list-unstyled mb-0 d-grid gap-2";
        for (const [, item] of carrito.entries()) {
            const li = document.createElement("li");
            li.className = "d-flex justify-content-between align-items-center p-2 border rounded";
            const info = document.createElement("span");
            info.className = "small";
            info.textContent = `${item.cantidad}x ${item.nombre}`;
            const importe = document.createElement("strong");
            importe.className = "small ms-2";
            importe.textContent = `S/ ${(item.precio * item.cantidad).toFixed(2)}`;
            li.append(info, importe);
            ul.append(li);
        }
        listaPedido.append(ul);
        calcularTotales();
    }

    function vincularBotonesProducto() {
        gridProductos.querySelectorAll("[data-seleccionar-producto]").forEach(boton => {
            boton.addEventListener("click", () => {
                const id = Number(boton.getAttribute("data-seleccionar-producto"));
                const nombre = boton.getAttribute("data-nombre") || "Producto";
                const precio = Number(boton.getAttribute("data-precio") || 0);
                const actual = carrito.get(id) || { producto_id: id, nombre, precio, cantidad: 0 };
                actual.cantidad += 1;
                carrito.set(id, actual);
                seccionBoleta.hidden = true;
                alertaCheckout.hidden = true;
                renderizarCarrito();
            });
        });
    }

    async function sincronizarCatalogoDesdeApi() {
        try {
            const data = await peticionApi("/api/productos");
            if (!Array.isArray(data?.productos)) return;
            for (const prod of data.productos) {
                const badge = document.querySelector(`[data-stock-badge="${prod.id}"]`);
                if (badge) badge.textContent = `Disponibles: ${prod.stock}`;
            }
            estadoCatalogo.textContent = "Stock en tiempo real";
        } catch {
            estadoCatalogo.textContent = "Catálogo disponible";
        }
    }

    async function asegurarSesionCliente() {
        const sesion = obtenerSesion();
        if (sesion?.token) return sesion;
        throw new Error("Debes iniciar sesión con tu cuenta para procesar tu compra.");
    }

    formCheckout.addEventListener("submit", async evento => {
        evento.preventDefault();
        alertaCheckout.hidden = true;
        seccionBoleta.hidden = true;

        if (carrito.size === 0) {
            alertaCheckout.textContent = "Selecciona al menos un producto del catálogo antes de confirmar tu compra.";
            alertaCheckout.hidden = false;
            return;
        }

        const sesion = obtenerSesion();
        if (!sesion?.token) {
            alertaCheckout.textContent = "Debes iniciar sesión o registrarte para completar tu compra.";
            alertaCheckout.hidden = false;
            if (btnLoginDesdeTienda) btnLoginDesdeTienda.click();
            return;
        }

        const clienteNombre = sesion.usuario?.nombre || (inputNombre ? inputNombre.value.trim() : "Cliente");
        const tipoDocumento = selectTipoDoc ? selectTipoDoc.value : "DNI";
        const clienteDocumento = inputDocumento ? inputDocumento.value.trim() : "";
        const metodoPago = document.getElementById("metodo-pago").value;

        if (!clienteDocumento) {
            alertaCheckout.textContent = "Por favor ingresa tu número de documento de identidad.";
            alertaCheckout.hidden = false;
            inputDocumento?.focus();
            return;
        }

        if (tipoDocumento === "DNI" && !/^\d{8}$/.test(clienteDocumento)) {
            alertaCheckout.textContent = "El DNI debe contener exactamente 8 dígitos numéricos.";
            alertaCheckout.hidden = false;
            inputDocumento?.focus();
            return;
        }

        if (tipoDocumento === "RUC" && !/^\d{11}$/.test(clienteDocumento)) {
            alertaCheckout.textContent = "El RUC debe contener exactamente 11 dígitos numéricos.";
            alertaCheckout.hidden = false;
            inputDocumento?.focus();
            return;
        }

        try {
            const respuesta = await peticionApi("/api/tienda/checkout", {
                method: "POST",
                body: JSON.stringify({
                    cliente_nombre: clienteNombre,
                    tipo_documento: tipoDocumento,
                    cliente_documento: clienteDocumento,
                    metodo_pago: metodoPago,
                    items: Array.from(carrito.values()).map(i => ({
                        producto_id: i.producto_id,
                        cantidad: i.cantidad
                    }))
                })
            });

            // Si el usuario no tenía documento en su sesión, plasmarlo y bloquearlo
            if (respuesta.usuario_actualizado) {
                const sActual = obtenerSesion();
                if (sActual && sActual.usuario) {
                    sActual.usuario.documento = respuesta.usuario_actualizado.documento;
                    sActual.usuario.tipo_documento = respuesta.usuario_actualizado.tipo_documento;
                    guardarSesion(sActual);
                    actualizarEstadoUsuarioEnFormulario();
                    window.dispatchEvent(new CustomEvent("sesion_actualizada"));
                }
            }

            ultimoPdfBase64 = respuesta.pdf_base64;
            ultimoNombrePdf = respuesta.pdf_filename || `Boleta_${respuesta.venta.numero_boleta}.pdf`;
            elNumeroBoleta.textContent = respuesta.venta.numero_boleta;
            if (respuesta.whatsapp_url) {
                enlaceWhatsappBoleta.href = respuesta.whatsapp_url;
            }
            seccionBoleta.hidden = false;
            carrito.clear();
            renderizarCarrito();
            await sincronizarCatalogoDesdeApi();
        } catch (error) {
            alertaCheckout.textContent = error.message || "No se pudo completar la compra en este momento.";
            alertaCheckout.hidden = false;
        }
    });

    btnDescargarPdf.addEventListener("click", () => {
        if (ultimoPdfBase64) {
            descargarPdfDesdeBase64(ultimoPdfBase64, ultimoNombrePdf);
        }
    });

    btnVaciar.addEventListener("click", () => {
        carrito.clear();
        alertaCheckout.hidden = true;
        seccionBoleta.hidden = true;
        renderizarCarrito();
    });

    vincularBotonesProducto();
    sincronizarCatalogoDesdeApi();
    actualizarEstadoUsuarioEnFormulario();
})();
