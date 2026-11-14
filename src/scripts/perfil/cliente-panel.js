import {
    abrirPdfBoletaAutenticada,
    guardarSesion,
    obtenerSesion,
    peticionApi,
} from "../api-client.js";
import { escapeHtml } from "../ui-utils.js";

export function crearControladorCliente({ mostrarAlertaGlobal, recargarPerfil }) {
    const formVincularDoc = document.getElementById("form-vincular-doc-perfil");
    const selectTipoDoc = document.getElementById("perfil-select-tipo-doc");
    const inputNumDoc = document.getElementById("perfil-input-num-doc");
    const btnCancelarVincularDoc = document.getElementById("btn-cancelar-vincular-doc");
    const formCambiarPassword = document.getElementById("form-cambiar-password");
    const alertaPassword = document.getElementById("alerta-cambio-password");

    const contenedorListaMascotas = document.getElementById("contenedor-lista-mascotas");
    const contenedorMisSolicitudes = document.getElementById("contenedor-mis-solicitudes");
    const btnToggleAltaMascota = document.getElementById("btn-toggle-alta-mascota");
    const wrapAltaMascota = document.getElementById("wrap-alta-mascota");
    const formAltaMascota = document.getElementById("form-alta-mascota");
    const btnCancelarAltaMascota = document.getElementById("btn-cancelar-alta-mascota");
    const alertaAltaMascota = document.getElementById("alerta-alta-mascota");

    const modalSolicitudEl = document.getElementById("modalSolicitudMascota");
    const modalSolicitudTitulo = document.getElementById("modalSolicitudTitulo");
    const formSolicitudMascota = document.getElementById("form-solicitud-mascota");
    const inputSolicitudMascotaId = document.getElementById("solicitud-input-mascota-id");
    const inputSolicitudTipo = document.getElementById("solicitud-input-tipo");
    const inputSolicitudMotivo = document.getElementById("solicitud-input-motivo");
    const wrapCamposEdicion = document.getElementById("wrap-campos-edicion-mascota");
    const alertaModalSolicitud = document.getElementById("alerta-solicitud-modal");
    const editNombre = document.getElementById("edit-mascota-nombre");
    const editEspecie = document.getElementById("edit-mascota-especie");
    const editRaza = document.getElementById("edit-mascota-raza");
    const editEdad = document.getElementById("edit-mascota-edad");
    const editPeso = document.getElementById("edit-mascota-peso");
    const editResumen = document.getElementById("edit-mascota-resumen");

    const contenedorMisCompras = document.getElementById("contenedor-mis-compras");
    const btnMockAgregarTarjeta = document.getElementById("btn-mock-agregar-tarjeta");
    const contenedorMisCitas = document.getElementById("contenedor-mis-citas");

    let modalSolicitudInstance = null;

    selectTipoDoc?.addEventListener("change", () => {
        if (!inputNumDoc) return;
        const tipo = selectTipoDoc.value;
        if (tipo === "DNI") {
            inputNumDoc.maxLength = 8;
            inputNumDoc.placeholder = "Ej: 74859632 (8 dígitos)";
        } else {
            inputNumDoc.maxLength = 11;
            inputNumDoc.placeholder = "Ej: 20123456789 (11 dígitos)";
        }
    });

    inputNumDoc?.addEventListener("input", e => {
        e.target.value = e.target.value.replace(/\D/g, "");
    });

    btnCancelarVincularDoc?.addEventListener("click", () => {
        formVincularDoc?.classList.add("d-none");
        formVincularDoc?.reset();
    });

    formVincularDoc?.addEventListener("submit", async ev => {
        ev.preventDefault();
        const tipo = selectTipoDoc.value;
        const doc = inputNumDoc.value.trim();

        if (tipo === "DNI" && !/^\d{8}$/.test(doc)) {
            alert("El DNI debe tener exactamente 8 dígitos numéricos.");
            inputNumDoc.focus();
            return;
        }
        if (tipo === "RUC" && !/^\d{11}$/.test(doc)) {
            alert("El RUC debe tener exactamente 11 dígitos numéricos.");
            inputNumDoc.focus();
            return;
        }

        try {
            await peticionApi("/api/cliente/documento", {
                method: "POST",
                body: JSON.stringify({ tipo_documento: tipo, documento: doc }),
            });
            const s = obtenerSesion();
            if (s?.usuario) {
                s.usuario.documento = doc;
                s.usuario.tipo_documento = tipo;
                guardarSesion(s);
            }
            mostrarAlertaGlobal(`Identificación ${tipo} ${doc} vinculada exitosamente.`, "success");
            await recargarPerfil();
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    });

    formCambiarPassword?.addEventListener("submit", async ev => {
        ev.preventDefault();
        alertaPassword?.classList.add("d-none");

        const actual = document.getElementById("input-pass-actual").value;
        const nueva = document.getElementById("input-pass-nueva").value;
        const confirmar = document.getElementById("input-pass-confirmar").value;

        if (nueva.length < 6) {
            alertaPassword.textContent = "La nueva contraseña debe tener al menos 6 caracteres.";
            alertaPassword.classList.remove("d-none");
            return;
        }
        if (nueva !== confirmar) {
            alertaPassword.textContent = "Las nuevas contraseñas no coinciden.";
            alertaPassword.classList.remove("d-none");
            return;
        }

        try {
            await peticionApi("/api/auth/cambiar-password", {
                method: "POST",
                body: JSON.stringify({ password_actual: actual, password_nueva: nueva }),
            });
            formCambiarPassword.reset();
            mostrarAlertaGlobal("Tu contraseña ha sido actualizada con éxito.", "success");
        } catch (err) {
            alertaPassword.textContent = err.message || "No se pudo cambiar la contraseña.";
            alertaPassword.classList.remove("d-none");
        }
    });

    btnToggleAltaMascota?.addEventListener("click", () => {
        const visible = !wrapAltaMascota?.classList.contains("d-none");
        if (visible) {
            wrapAltaMascota?.classList.add("d-none");
        } else {
            wrapAltaMascota?.classList.remove("d-none");
            document.getElementById("alta-mascota-nombre")?.focus();
        }
    });

    btnCancelarAltaMascota?.addEventListener("click", () => {
        wrapAltaMascota?.classList.add("d-none");
        formAltaMascota?.reset();
        alertaAltaMascota?.classList.add("d-none");
    });

    formAltaMascota?.addEventListener("submit", async ev => {
        ev.preventDefault();
        alertaAltaMascota?.classList.add("d-none");

        const nombre = document.getElementById("alta-mascota-nombre").value.trim();
        const especie = document.getElementById("alta-mascota-especie").value;
        const raza = document.getElementById("alta-mascota-raza").value.trim() || "Mestizo";
        const sexo = document.getElementById("alta-mascota-sexo").value;
        const edad = parseInt(document.getElementById("alta-mascota-edad").value || "1", 10);
        const peso_kg = parseFloat(document.getElementById("alta-mascota-peso").value || "5.0");
        const historial_resumen = document.getElementById("alta-mascota-resumen").value.trim();

        if (!nombre) {
            alertaAltaMascota.textContent = "Por favor indica el nombre de la mascota.";
            alertaAltaMascota.classList.remove("d-none");
            return;
        }

        try {
            await peticionApi("/api/cliente/mascotas", {
                method: "POST",
                body: JSON.stringify({ nombre, especie, raza, sexo, edad, peso_kg, historial_resumen }),
            });
            formAltaMascota.reset();
            wrapAltaMascota?.classList.add("d-none");
            mostrarAlertaGlobal(`¡${nombre} ha sido registrado(a) exitosamente!`, "success");
            await cargarMisMascotas();
        } catch (err) {
            alertaAltaMascota.textContent = err.message || "Error al registrar la mascota.";
            alertaAltaMascota.classList.remove("d-none");
        }
    });

    async function cargarMisSolicitudes() {
        if (!contenedorMisSolicitudes) return;
        try {
            const data = await peticionApi("/api/cliente/solicitudes");
            const solicitudes = Array.isArray(data?.solicitudes) ? data.solicitudes : [];

            if (!solicitudes.length) {
                contenedorMisSolicitudes.innerHTML = "<p class='small text-muted mb-0'>No hay solicitudes registradas en tus mascotas.</p>";
                return;
            }

            const ul = document.createElement("ul");
            ul.className = "list-unstyled mb-0 d-grid gap-2";

            for (const s of solicitudes) {
                const li = document.createElement("li");
                li.className = "p-2 border rounded bg-white d-flex justify-content-between align-items-start gap-2";

                const info = document.createElement("div");
                const badgeEstado = s.estado === "aprobada" ? "bg-success" : s.estado === "rechazada" ? "bg-danger" : "bg-warning text-dark";

                info.innerHTML = `
                    <div class="d-flex align-items-center gap-2 mb-1">
                        <strong class="small text-dark">${s.tipo === "editar" ? "Modificación de datos" : "Baja de mascota"}</strong>
                        <span class="badge ${badgeEstado} small" style="font-size: 0.68rem;">${escapeHtml((s.estado || "").toUpperCase())}</span>
                    </div>
                    <p class="small text-muted mb-0"><strong>Mascota:</strong> ${escapeHtml(s.mascota_nombre || "Paciente")} · <strong>Motivo:</strong> ${escapeHtml(s.motivo)}</p>
                `;
                li.append(info);
                ul.append(li);
            }
            contenedorMisSolicitudes.replaceChildren(ul);
        } catch {
        }
    }

    function abrirModalSolicitud(tipo, mascota) {
        if (!modalSolicitudEl) return;
        alertaModalSolicitud?.classList.add("d-none");
        inputSolicitudMascotaId.value = mascota.id;
        inputSolicitudTipo.value = tipo;
        inputSolicitudMotivo.value = "";

        if (tipo === "editar") {
            modalSolicitudTitulo.textContent = `Solicitar edición de ${mascota.nombre}`;
            wrapCamposEdicion?.classList.remove("d-none");
            if (editNombre) editNombre.value = mascota.nombre || "";
            if (editEspecie) editEspecie.value = mascota.especie || "Perro";
            if (editRaza) editRaza.value = mascota.raza || "";
            if (editEdad) editEdad.value = mascota.edad || 1;
            if (editPeso) editPeso.value = mascota.peso_kg || 5.0;
            if (editResumen) editResumen.value = mascota.historial_resumen || "";
        } else {
            modalSolicitudTitulo.textContent = `Solicitar baja de ${mascota.nombre}`;
            wrapCamposEdicion?.classList.add("d-none");
        }

        if (window.bootstrap?.Modal) {
            modalSolicitudInstance = window.bootstrap.Modal.getOrCreateInstance(modalSolicitudEl);
            modalSolicitudInstance.show();
        }
    }

    formSolicitudMascota?.addEventListener("submit", async ev => {
        ev.preventDefault();
        alertaModalSolicitud?.classList.add("d-none");

        const mascotaId = inputSolicitudMascotaId.value;
        const tipo = inputSolicitudTipo.value;
        const motivo = inputSolicitudMotivo.value.trim();

        if (motivo.length < 5) {
            alertaModalSolicitud.textContent = "Por favor explica el motivo o justificación de esta decisión (mínimo 5 caracteres).";
            alertaModalSolicitud.classList.remove("d-none");
            inputSolicitudMotivo.focus();
            return;
        }

        let datos_nuevos = null;
        if (tipo === "editar") {
            datos_nuevos = {
                nombre: editNombre?.value.trim(),
                especie: editEspecie?.value,
                raza: editRaza?.value.trim(),
                edad: parseInt(editEdad?.value || "1", 10),
                peso_kg: parseFloat(editPeso?.value || "5.0"),
                historial_resumen: editResumen?.value.trim(),
            };
        }

        try {
            await peticionApi(`/api/cliente/mascotas/${mascotaId}/solicitar-cambio`, {
                method: "POST",
                body: JSON.stringify({ tipo, motivo, datos_nuevos }),
            });
            modalSolicitudInstance?.hide();
            mostrarAlertaGlobal("Tu solicitud ha sido enviada al administrador para su evaluación.", "success");
            await cargarMisMascotas();
        } catch (err) {
            alertaModalSolicitud.textContent = err.message || "Error al enviar la solicitud.";
            alertaModalSolicitud.classList.remove("d-none");
        }
    });

    async function cargarMisMascotas() {
        if (!contenedorListaMascotas) return;
        contenedorListaMascotas.replaceChildren();

        try {
            const data = await peticionApi("/api/cliente/mis-mascotas");
            const mascotas = Array.isArray(data?.mascotas) ? data.mascotas : [];

            if (!mascotas.length) {
                const p = document.createElement("p");
                p.className = "small text-muted mb-0";
                p.textContent = "No tienes mascotas registradas aún. Presiona '+ Añadir mascota' para registrar a tu compañero.";
                contenedorListaMascotas.append(p);
            } else {
                for (const m of mascotas) {
                    const card = document.createElement("article");
                    card.className = "p-3 rounded border bg-light position-relative";

                    const headerRow = document.createElement("div");
                    headerRow.className = "d-flex justify-content-between align-items-start mb-2 gap-2";

                    const titulo = document.createElement("h3");
                    titulo.className = "h6 fw-bold mb-0 text-dark";
                    titulo.textContent = `${m.nombre} · ${m.especie} (${m.raza || "Mestizo"})`;

                    const accionesWrap = document.createElement("div");
                    accionesWrap.className = "d-flex gap-2";

                    const btnEditar = document.createElement("button");
                    btnEditar.type = "button";
                    btnEditar.className = "btn btn-outline-secondary btn-sm py-0 px-2";
                    btnEditar.style.fontSize = "0.75rem";
                    btnEditar.textContent = "Solicitar edición";
                    btnEditar.addEventListener("click", () => abrirModalSolicitud("editar", m));

                    const btnBaja = document.createElement("button");
                    btnBaja.type = "button";
                    btnBaja.className = "btn btn-outline-danger btn-sm py-0 px-2";
                    btnBaja.style.fontSize = "0.75rem";
                    btnBaja.textContent = "Solicitar baja";
                    btnBaja.addEventListener("click", () => abrirModalSolicitud("eliminar", m));

                    accionesWrap.append(btnEditar, btnBaja);
                    headerRow.append(titulo, accionesWrap);

                    const meta = document.createElement("p");
                    meta.className = "small text-muted mb-1";
                    meta.textContent = `Edad: ${m.edad} año(s) · Peso: ${m.peso_kg} kg · Sexo: ${m.sexo === "M" ? "Macho" : "Hembra"}`;

                    const notas = document.createElement("p");
                    notas.className = "small mb-0 text-secondary";
                    notas.textContent = m.historial_resumen || "Sin observaciones clínicas registradas.";

                    card.append(headerRow, meta, notas);
                    contenedorListaMascotas.append(card);
                }
            }

            cargarMisSolicitudes();
        } catch (err) {
            contenedorListaMascotas.replaceChildren();
            const pErr = document.createElement("p");
            pErr.className = "small text-danger mb-0";
            pErr.textContent = `Error al cargar mascotas: ${err.message}`;
            contenedorListaMascotas.append(pErr);
        }
    }

    async function cargarMisCompras() {
        if (!contenedorMisCompras) return;
        contenedorMisCompras.replaceChildren();

        try {
            const data = await peticionApi("/api/cliente/mis-compras");
            const compras = Array.isArray(data?.compras) ? data.compras : [];

            if (!compras.length) {
                const p = document.createElement("p");
                p.className = "small text-muted mb-0";
                p.textContent = "No tienes compras registradas en la tienda aún.";
                contenedorMisCompras.append(p);
                return;
            }

            const tableWrap = document.createElement("div");
            tableWrap.className = "table-responsive";

            const table = document.createElement("table");
            table.className = "table table-hover align-middle small mb-0";
            table.innerHTML = `
                <thead class="table-light">
                    <tr>
                        <th>N° Boleta</th>
                        <th>Fecha</th>
                        <th>Productos</th>
                        <th>Total</th>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody id="tbody-mis-compras"></tbody>
            `;

            const tbody = table.querySelector("#tbody-mis-compras");

            for (const c of compras) {
                const tr = document.createElement("tr");
                const resumenItems = (c.detalles || []).map(d => `${d.cantidad}x ${d.producto_nombre}`).join(", ") || "Productos de farmacia";

                tr.innerHTML = `
                    <td><strong>${escapeHtml(c.numero_boleta)}</strong></td>
                    <td class="text-muted">${escapeHtml((c.creado_en || "").substring(0, 10))}</td>
                    <td class="text-secondary">${escapeHtml(resumenItems)}</td>
                    <td><strong>S/ ${parseFloat(c.total).toFixed(2)}</strong></td>
                    <td>
                        <div class="d-flex gap-1">
                            <button type="button" data-pdf-boleta-id="${escapeHtml(c.id)}" class="btn btn-outline-success btn-sm py-0 px-2" style="font-size: 0.75rem;">
                                PDF
                            </button>
                        </div>
                    </td>
                `;
                tbody.append(tr);
            }

            tableWrap.append(table);
            contenedorMisCompras.append(tableWrap);
            contenedorMisCompras.querySelectorAll("[data-pdf-boleta-id]").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const ventaId = btn.getAttribute("data-pdf-boleta-id");
                    if (!ventaId) return;
                    try {
                        await abrirPdfBoletaAutenticada(ventaId);
                    } catch (err) {
                        mostrarAlertaGlobal(err.message, "danger");
                    }
                });
            });
        } catch (err) {
            contenedorMisCompras.innerHTML = `<p class="small text-danger mb-0">Error al cargar compras: ${escapeHtml(err.message)}</p>`;
        }
    }

    btnMockAgregarTarjeta?.addEventListener("click", () => {
        alert("En este entorno demostrativo no se procesan tarjetas reales. Tus compras en Patitas Felices generan boleta inmediata y se coordinan en caja o vía Yape/Plin.");
    });

    async function cargarMisCitas() {
        if (!contenedorMisCitas) return;
        contenedorMisCitas.replaceChildren();

        try {
            const data = await peticionApi("/api/cliente/mis-citas");
            const citas = Array.isArray(data?.citas) ? data.citas : [];

            if (!citas.length) {
                contenedorMisCitas.innerHTML = "<p class='small text-muted mb-0'>No tienes citas médicas programadas.</p>";
                return;
            }

            for (const c of citas) {
                const card = document.createElement("article");
                card.className = "p-3 rounded border bg-light mb-2";
                const badgeClase = c.estado === "confirmada" ? "bg-primary" : c.estado === "atendida" ? "bg-success" : c.estado === "cancelada" ? "bg-danger" : "bg-warning text-dark";

                card.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <strong class="text-dark small">${escapeHtml(c.mascota_nombre)} · ${escapeHtml(c.servicio)}</strong>
                        <span class="badge ${badgeClase} small" style="font-size: 0.7rem;">${escapeHtml((c.estado || "pendiente").toUpperCase())}</span>
                    </div>
                    <p class="small text-muted mb-1">Fecha: ${escapeHtml(c.fecha)} a las ${escapeHtml(c.hora)} (Lima)</p>
                    <p class="small text-secondary mb-1"><strong>Motivo:</strong> ${escapeHtml(c.motivo)}</p>
                    ${c.diagnostico ? `<p class="small border-top pt-2 mb-0 text-dark"><strong>Evaluación médica:</strong> ${escapeHtml(c.diagnostico)} — <strong>Tratamiento:</strong> ${escapeHtml(c.tratamiento || "Sin indicaciones")}</p>` : ""}
                `;
                contenedorMisCitas.append(card);
            }
        } catch (err) {
            contenedorMisCitas.innerHTML = `<p class="small text-danger mb-0">Error: ${escapeHtml(err.message)}</p>`;
        }
    }

    return {
        cargarMisMascotas,
        cargarMisCompras,
        cargarMisCitas,
    };
}
