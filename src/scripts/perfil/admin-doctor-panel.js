import { abrirPdfBoletaAutenticada, peticionApi } from "../api-client.js";
import { esModoDemoActivo, escapeHtml } from "../ui-utils.js";

export function crearControladorDoctorYAdmin({ mostrarAlertaGlobal, badgeContadorSolicitudes }) {
    const contenedorAgendaDoctor = document.getElementById("contenedor-agenda-doctor");
    const wrapAtencionDoctor = document.getElementById("wrap-atencion-doctor");
    const formAtencionDoctor = document.getElementById("form-atencion-doctor");
    const inputAtencionCitaId = document.getElementById("doctor-input-cita-id");
    const infoPacienteAtencion = document.getElementById("doctor-info-paciente");
    const inputDiagnostico = document.getElementById("doctor-input-diagnostico");
    const inputTratamiento = document.getElementById("doctor-input-tratamiento");
    const btnCancelarAtencion = document.getElementById("btn-cancelar-atencion");
    const contenedorFarmaciaDoctor = document.getElementById("contenedor-farmacia-doctor");

    const contenedorCrmAdmin = document.getElementById("contenedor-crm-admin");
    const contenedorSolicitudesAdmin = document.getElementById("contenedor-solicitudes-admin");
    const formAltaPersonal = document.getElementById("form-alta-personal");
    const alertaAltaPersonal = document.getElementById("alerta-alta-personal");
    const contenedorPersonalAdmin = document.getElementById("contenedor-personal-admin");
    const badgeTotalPersonal = document.getElementById("badge-total-personal");
    const contenedorUsuariosAdmin = document.getElementById("contenedor-usuarios-admin");
    const contenedorVisorTablas = document.getElementById("contenedor-visor-tablas-resumen");

    async function cargarAgendaDoctor() {
        if (!contenedorAgendaDoctor) return;
        contenedorAgendaDoctor.replaceChildren();

        try {
            const data = await peticionApi("/api/doctor/agenda");
            const citas = Array.isArray(data?.citas) ? data.citas : [];
            const metaDoc = document.getElementById("agenda-doctor-meta");
            if (metaDoc && data?.perfil_profesional) {
                const p = data.perfil_profesional;
                metaDoc.textContent = `${p.nombre || ""} · ${p.colegiatura || "Sin CMVP"} · ${p.especialidad || "Medicina General"}`;
            }

            if (!citas.length) {
                contenedorAgendaDoctor.innerHTML = "<p class='small text-muted mb-0'>No hay citas pendientes en la agenda.</p>";
                return;
            }

            for (const c of citas) {
                const card = document.createElement("article");
                card.className = "p-3 rounded border bg-light mb-3";
                const badgeClase = c.estado === "confirmada" ? "bg-primary" : c.estado === "atendida" ? "bg-success" : "bg-warning text-dark";

                card.innerHTML = `
                    <div class="d-flex flex-wrap justify-content-between align-items-center mb-2 gap-2">
                        <div>
                            <strong class="text-dark">Paciente: ${escapeHtml(c.mascota_nombre)}</strong>
                            <small class="text-muted d-block">Propietario: ${escapeHtml(c.propietario)} (${escapeHtml(c.telefono)})</small>
                        </div>
                        <span class="badge ${badgeClase}">${escapeHtml((c.estado || "pendiente").toUpperCase())}</span>
                    </div>
                    <p class="small mb-1"><strong>Servicio:</strong> ${escapeHtml(c.servicio)} · <strong>Fecha:</strong> ${escapeHtml(c.fecha)} (${escapeHtml(c.hora)})</p>
                    <p class="small text-muted mb-2"><strong>Motivo:</strong> ${escapeHtml(c.motivo)}</p>
                    <div class="d-flex gap-2">
                        ${c.estado === "pendiente" ? `<button type="button" class="btn btn-outline-primary btn-sm py-0 px-2 btn-confirmar-cita" data-id="${Number(c.id)}">Confirmar cita</button>` : ""}
                        ${c.estado !== "atendida" ? `<button type="button" class="btn btn-success btn-sm py-0 px-2 btn-atender-cita" data-id="${Number(c.id)}" data-paciente="${escapeHtml(c.mascota_nombre)}">Atender paciente</button>` : ""}
                        ${c.estado !== "cancelada" && c.estado !== "atendida" ? `<button type="button" class="btn btn-outline-danger btn-sm py-0 px-2 btn-cancelar-cita" data-id="${Number(c.id)}">Cancelar</button>` : ""}
                    </div>
                    ${c.diagnostico ? `<div class="mt-2 pt-2 border-top small text-dark"><strong>Diagnóstico:</strong> ${escapeHtml(c.diagnostico)}<br><strong>Tratamiento:</strong> ${escapeHtml(c.tratamiento)}</div>` : ""}
                `;

                card.querySelector(".btn-confirmar-cita")?.addEventListener("click", async () => {
                    try {
                        await peticionApi(`/api/doctor/citas/${c.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({
                                estado: "confirmada",
                                diagnostico: c.diagnostico || "",
                                tratamiento: c.tratamiento || "",
                            }),
                        });
                        await cargarAgendaDoctor();
                    } catch (err) {
                        mostrarAlertaGlobal(err.message || "No se pudo confirmar la cita.", "danger");
                    }
                });

                card.querySelector(".btn-cancelar-cita")?.addEventListener("click", async () => {
                    if (!confirm("¿Deseas cancelar esta cita?")) return;
                    try {
                        await peticionApi(`/api/doctor/citas/${c.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({
                                estado: "cancelada",
                                diagnostico: c.diagnostico || "",
                                tratamiento: c.tratamiento || "",
                            }),
                        });
                        await cargarAgendaDoctor();
                    } catch (err) {
                        mostrarAlertaGlobal(err.message || "No se pudo cancelar la cita.", "danger");
                    }
                });

                card.querySelector(".btn-atender-cita")?.addEventListener("click", () => {
                    inputAtencionCitaId.value = c.id;
                    infoPacienteAtencion.textContent = `Atendiendo a: ${c.mascota_nombre} (${c.servicio} - Propietario: ${c.propietario})`;
                    wrapAtencionDoctor?.classList.remove("d-none");
                    inputDiagnostico?.focus();
                });

                contenedorAgendaDoctor.append(card);
            }
        } catch (err) {
            contenedorAgendaDoctor.innerHTML = `<p class="small text-danger mb-0">Error: ${escapeHtml(err.message)}</p>`;
        }
    }

    btnCancelarAtencion?.addEventListener("click", () => {
        wrapAtencionDoctor?.classList.add("d-none");
        formAtencionDoctor?.reset();
    });

    formAtencionDoctor?.addEventListener("submit", async ev => {
        ev.preventDefault();
        const citaId = inputAtencionCitaId.value;
        const diagnostico = inputDiagnostico.value.trim();
        const tratamiento = inputTratamiento.value.trim();

        if (!diagnostico) {
            alert("Por favor ingresa el diagnóstico médico.");
            return;
        }

        try {
            await peticionApi(`/api/doctor/citas/${citaId}`, {
                method: "PATCH",
                body: JSON.stringify({ estado: "atendida", diagnostico, tratamiento }),
            });
            wrapAtencionDoctor?.classList.add("d-none");
            formAtencionDoctor.reset();
            mostrarAlertaGlobal(`La atención de la cita #${citaId} ha sido registrada.`, "success");
            await cargarAgendaDoctor();
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    });

    async function cargarFarmaciaDoctor() {
        if (!contenedorFarmaciaDoctor) return;
        contenedorFarmaciaDoctor.replaceChildren();

        try {
            const data = await peticionApi("/api/productos");
            const prods = Array.isArray(data?.productos) ? data.productos : [];

            const tableWrap = document.createElement("div");
            tableWrap.className = "table-responsive";
            tableWrap.innerHTML = `
                <table class="table table-hover align-middle small mb-0">
                    <thead class="table-light">
                        <tr>
                            <th>Código</th>
                            <th>Producto</th>
                            <th>Categoría</th>
                            <th>Precio</th>
                            <th>Stock</th>
                        </tr>
                    </thead>
                    <tbody id="tbody-farmacia"></tbody>
                </table>
            `;
            const tbody = tableWrap.querySelector("#tbody-farmacia");
            for (const p of prods) {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><code>${escapeHtml(p.codigo)}</code></td>
                    <td><strong>${escapeHtml(p.nombre)}</strong></td>
                    <td>${escapeHtml(p.categoria)}</td>
                    <td>S/ ${parseFloat(p.precio).toFixed(2)}</td>
                    <td><span class="badge ${p.stock > 5 ? "bg-success" : "bg-warning text-dark"}">${escapeHtml(p.stock)} unid.</span></td>
                `;
                tbody.append(tr);
            }
            contenedorFarmaciaDoctor.append(tableWrap);
        } catch (err) {
            contenedorFarmaciaDoctor.innerHTML = `<p class="small text-danger mb-0">Error: ${escapeHtml(err.message)}</p>`;
        }
    }

    async function cargarCRMAdmin() {
        if (!contenedorCrmAdmin) return;
        contenedorCrmAdmin.replaceChildren();

        try {
            const demoParam = esModoDemoActivo() ? "1" : "0";
            const data = await peticionApi(`/api/admin/crm?demo=${demoParam}&page=1&page_size=25`);
            const resumen = data.resumen || {};
            const ventasReales = Array.isArray(data.ventas) ? data.ventas : [];
            const ventasDemo = Array.isArray(data.ventas_referencia_demo) ? data.ventas_referencia_demo : [];
            const ultimas = Array.isArray(data.ultimas_ventas) && data.ultimas_ventas.length > 0
                ? data.ultimas_ventas
                : (ventasReales.length > 0 ? ventasReales : ventasDemo);

            const ingresosCalc = ultimas.reduce((acc, v) => acc + parseFloat(v.total || 0), 0);
            const balance = data.balance_financiero || {
                ingresos_totales: resumen.ingresos_totales || ingresosCalc,
                total_transacciones: resumen.total_ventas || ultimas.length,
                ticket_promedio: ultimas.length > 0 ? (ingresosCalc / ultimas.length) : 0,
                modo_demostracion: ventasReales.length === 0 && ventasDemo.length > 0,
            };

            const metricsWrap = document.createElement("div");
            metricsWrap.className = "row g-3 mb-4";
            metricsWrap.innerHTML = `
                <div class="col-12 col-sm-6 col-lg-4">
                    <div class="p-3 border rounded bg-light h-100">
                        <small class="text-muted d-block">Ingresos Totales ${balance.modo_demostracion ? '<span class="badge bg-secondary-subtle text-secondary border ms-1">Demo</span>' : ""}</small>
                        <h3 class="h4 fw-bold text-dark mb-0">S/ ${parseFloat(balance.ingresos_totales || 0).toFixed(2)}</h3>
                    </div>
                </div>
                <div class="col-12 col-sm-6 col-lg-4">
                    <div class="p-3 border rounded bg-light h-100">
                        <small class="text-muted d-block">Ventas Registradas</small>
                        <h3 class="h4 fw-bold text-dark mb-0">${balance.total_transacciones || 0}</h3>
                    </div>
                </div>
                <div class="col-12 col-sm-6 col-lg-4">
                    <div class="p-3 border rounded bg-light h-100">
                        <small class="text-muted d-block">Ticket Promedio</small>
                        <h3 class="h4 fw-bold text-dark mb-0">S/ ${parseFloat(balance.ticket_promedio || 0).toFixed(2)}</h3>
                    </div>
                </div>
                <div class="col-12 col-sm-4">
                    <div class="p-3 border rounded bg-white h-100">
                        <small class="text-muted d-block">Pacientes y Mascotas</small>
                        <h3 class="h5 fw-bold text-dark mb-0">${resumen.total_pacientes ?? 0} registrados</h3>
                    </div>
                </div>
                <div class="col-12 col-sm-4">
                    <div class="p-3 border rounded bg-white h-100">
                        <small class="text-muted d-block">Citas Clínicas</small>
                        <h3 class="h5 fw-bold text-dark mb-0">${resumen.total_citas ?? 0} <span class="small fw-normal text-muted">(${resumen.citas_pendientes ?? 0} pend.)</span></h3>
                    </div>
                </div>
                <div class="col-12 col-sm-4">
                    <div class="p-3 border rounded bg-white h-100">
                        <small class="text-muted d-block">Stock Farmacia</small>
                        <h3 class="h5 fw-bold text-dark mb-0">${resumen.stock_total_unidades ?? 0} unid.</h3>
                    </div>
                </div>
            `;

            contenedorCrmAdmin.append(metricsWrap);

            const h4 = document.createElement("h4");
            h4.className = "h6 fw-bold mb-2 text-dark";
            h4.textContent = "Últimas transacciones comerciales y boletas";
            contenedorCrmAdmin.append(h4);

            const tableWrap = document.createElement("div");
            tableWrap.className = "table-responsive mb-4";
            tableWrap.innerHTML = `
                <table class="table table-hover align-middle small mb-0">
                    <thead class="table-light">
                        <tr>
                            <th>N° Boleta</th>
                            <th>Cliente</th>
                            <th>Concepto / Detalle</th>
                            <th>Documento</th>
                            <th>Medio de Pago</th>
                            <th>Total</th>
                            <th>Comprobante</th>
                        </tr>
                    </thead>
                    <tbody id="tbody-crm-ventas"></tbody>
                </table>
            `;
            const tbody = tableWrap.querySelector("#tbody-crm-ventas");
            for (const v of ultimas) {
                const tr = document.createElement("tr");
                const detalleTexto = v.concepto
                    || (Array.isArray(v.detalles) && v.detalles.length
                        ? v.detalles.map(d => `${d.cantidad}x ${d.producto_nombre}`).join(", ")
                        : "Venta de farmacia / tienda");
                const esDemo = Boolean(v.es_demostracion);
                tr.innerHTML = `
                    <td><strong>${escapeHtml(v.numero_boleta)}</strong></td>
                    <td>${escapeHtml(v.cliente_nombre)}</td>
                    <td class="text-secondary">${escapeHtml(detalleTexto)}</td>
                    <td><code>${escapeHtml(v.cliente_documento || "-")}</code></td>
                    <td><span class="badge bg-light text-dark border">${escapeHtml(v.metodo_pago || "Yape / Tarjeta")}</span></td>
                    <td><strong>S/ ${parseFloat(v.total || 0).toFixed(2)}</strong></td>
                    <td>
                        ${esDemo
                            ? '<span class="badge bg-secondary-subtle text-secondary border">Referencia</span>'
                            : `<button type="button" data-pdf-boleta-id="${escapeHtml(v.id)}" class="btn btn-outline-success btn-sm py-0 px-2" style="font-size: 0.72rem;">PDF</button>`}
                    </td>
                `;
                tbody.append(tr);
            }
            contenedorCrmAdmin.append(tableWrap);
            contenedorCrmAdmin.querySelectorAll("[data-pdf-boleta-id]").forEach(btn => {
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

            const citasCrm = Array.isArray(data.citas) ? data.citas.slice(0, 6) : [];
            if (citasCrm.length > 0) {
                const h4Citas = document.createElement("h4");
                h4Citas.className = "h6 fw-bold mb-2 text-dark";
                h4Citas.textContent = "Seguimiento CRM de citas médicas recientes";
                contenedorCrmAdmin.append(h4Citas);

                const citasWrap = document.createElement("div");
                citasWrap.className = "table-responsive";
                citasWrap.innerHTML = `
                    <table class="table table-hover align-middle small mb-0">
                        <thead class="table-light">
                            <tr>
                                <th>Paciente</th>
                                <th>Propietario</th>
                                <th>Servicio</th>
                                <th>Fecha y Hora</th>
                                <th>Estado</th>
                            </tr>
                        </thead>
                        <tbody id="tbody-crm-citas"></tbody>
                    </table>
                `;
                const tbodyCitas = citasWrap.querySelector("#tbody-crm-citas");
                for (const c of citasCrm) {
                    const badgeEstado = c.estado === "atendida"
                        ? "bg-success"
                        : c.estado === "confirmada"
                            ? "bg-primary"
                            : c.estado === "cancelada"
                                ? "bg-danger"
                                : "bg-warning text-dark";
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><strong>${escapeHtml(c.mascota_nombre)}</strong></td>
                        <td>${escapeHtml(c.propietario)} <small class="text-muted">(${escapeHtml(c.telefono || "-")})</small></td>
                        <td>${escapeHtml(c.servicio)}</td>
                        <td>${escapeHtml(c.fecha)} · ${escapeHtml(c.hora)}</td>
                        <td><span class="badge ${badgeEstado}">${escapeHtml((c.estado || "pendiente").toUpperCase())}</span></td>
                    `;
                    tbodyCitas.append(tr);
                }
                contenedorCrmAdmin.append(citasWrap);
            }
        } catch (err) {
            contenedorCrmAdmin.innerHTML = `<p class="small text-danger mb-0">Error: ${escapeHtml(err.message)}</p>`;
        }
    }

    async function actualizarContadorSolicitudesPendientes() {
        try {
            const data = await peticionApi("/api/admin/solicitudes-mascotas");
            const pendientes = (data?.solicitudes || []).filter(s => s.estado === "pendiente");
            if (badgeContadorSolicitudes) {
                if (pendientes.length > 0) {
                    badgeContadorSolicitudes.textContent = pendientes.length;
                    badgeContadorSolicitudes.classList.remove("d-none");
                } else {
                    badgeContadorSolicitudes.classList.add("d-none");
                }
            }
        } catch {
        }
    }

    async function cargarSolicitudesAdmin() {
        if (!contenedorSolicitudesAdmin) return;
        contenedorSolicitudesAdmin.replaceChildren();

        try {
            const data = await peticionApi("/api/admin/solicitudes-mascotas");
            const solicitudes = Array.isArray(data?.solicitudes) ? data.solicitudes : [];

            if (!solicitudes.length) {
                contenedorSolicitudesAdmin.innerHTML = "<p class='small text-muted mb-0'>No hay solicitudes de mascotas registradas.</p>";
                return;
            }

            const tableWrap = document.createElement("div");
            tableWrap.className = "table-responsive";
            tableWrap.innerHTML = `
                <table class="table table-hover align-middle small mb-0">
                    <thead class="table-light">
                        <tr>
                            <th>Propietario</th>
                            <th>Mascota</th>
                            <th>Tipo</th>
                            <th>Justificación descriptiva</th>
                            <th>Estado</th>
                            <th>Acciones</th>
                        </tr>
                    </thead>
                    <tbody id="tbody-admin-solicitudes"></tbody>
                </table>
            `;
            const tbody = tableWrap.querySelector("#tbody-admin-solicitudes");

            for (const s of solicitudes) {
                const tr = document.createElement("tr");
                const badgeClase = s.estado === "aprobada" ? "bg-success" : s.estado === "rechazada" ? "bg-danger" : "bg-warning text-dark";
                let detalleNuevos = "";
                if (s.tipo === "editar" && s.datos_nuevos) {
                    const dn = s.datos_nuevos;
                    detalleNuevos = `<br><small class="text-primary">Nuevos datos: ${escapeHtml(dn.nombre || "")} · ${escapeHtml(dn.especie || "")} · ${escapeHtml(dn.raza || "")} · ${escapeHtml(dn.edad || "")}a · ${escapeHtml(dn.peso_kg || "")}kg</small>`;
                }

                tr.innerHTML = `
                    <td><strong>${escapeHtml(s.propietario_nombre || "Cliente")}</strong><br><small class="text-muted">${escapeHtml(s.propietario_email || "")}</small></td>
                    <td><strong>${escapeHtml(s.mascota_nombre || "Paciente")}</strong></td>
                    <td><span class="badge bg-light text-dark border">${s.tipo === "editar" ? "Modificación" : "Baja"}</span></td>
                    <td>${escapeHtml(s.motivo)}${detalleNuevos}</td>
                    <td><span class="badge ${badgeClase}">${escapeHtml((s.estado || "").toUpperCase())}</span></td>
                    <td>
                        ${s.estado === "pendiente" ? `
                            <div class="d-flex gap-1">
                                <button type="button" class="btn btn-success btn-sm py-0 px-2 btn-aprobar-sol" data-id="${escapeHtml(s.id)}" style="font-size: 0.75rem;">Aprobar</button>
                                <button type="button" class="btn btn-outline-danger btn-sm py-0 px-2 btn-rechazar-sol" data-id="${escapeHtml(s.id)}" style="font-size: 0.75rem;">Rechazar</button>
                            </div>
                        ` : '<small class="text-muted">Procesada</small>'}
                    </td>
                `;

                tr.querySelector(".btn-aprobar-sol")?.addEventListener("click", async () => {
                    try {
                        await peticionApi(`/api/admin/solicitudes-mascotas/${s.id}/resolver`, { method: "POST", body: JSON.stringify({ accion: "aprobar" }) });
                        mostrarAlertaGlobal(`Solicitud #${s.id} aprobada con éxito.`, "success");
                        await cargarSolicitudesAdmin();
                        actualizarContadorSolicitudesPendientes();
                    } catch (err) {
                        mostrarAlertaGlobal(`Error al aprobar solicitud #${s.id}: ${err.message}`, "danger");
                    }
                });

                tr.querySelector(".btn-rechazar-sol")?.addEventListener("click", async () => {
                    try {
                        await peticionApi(`/api/admin/solicitudes-mascotas/${s.id}/resolver`, { method: "POST", body: JSON.stringify({ accion: "rechazar" }) });
                        mostrarAlertaGlobal(`Solicitud #${s.id} rechazada.`, "info");
                        await cargarSolicitudesAdmin();
                        actualizarContadorSolicitudesPendientes();
                    } catch (err) {
                        mostrarAlertaGlobal(`Error al rechazar solicitud #${s.id}: ${err.message}`, "danger");
                    }
                });

                tbody.append(tr);
            }

            contenedorSolicitudesAdmin.append(tableWrap);
        } catch (err) {
            contenedorSolicitudesAdmin.innerHTML = `<p class="small text-danger mb-0">Error: ${escapeHtml(err.message)}</p>`;
        }
    }

    const selectPersonalRol = document.getElementById("personal-input-rol");
    const wrapPersonalCmvp = document.getElementById("wrap-personal-cmvp");
    const wrapPersonalEspecialidad = document.getElementById("wrap-personal-especialidad");
    const inputPersonalCmvp = document.getElementById("personal-input-cmvp");
    const inputPersonalEspecialidad = document.getElementById("personal-input-especialidad");

    function sincronizarCamposPersonalPorRol() {
        const esDoctor = (selectPersonalRol?.value || "doctor") === "doctor";
        wrapPersonalCmvp?.classList.toggle("d-none", !esDoctor);
        wrapPersonalEspecialidad?.classList.toggle("d-none", !esDoctor);
        if (inputPersonalCmvp) {
            inputPersonalCmvp.required = esDoctor;
            if (!esDoctor) inputPersonalCmvp.value = "";
        }
        if (inputPersonalEspecialidad) {
            inputPersonalEspecialidad.required = esDoctor;
        }
    }

    selectPersonalRol?.addEventListener("change", sincronizarCamposPersonalPorRol);
    sincronizarCamposPersonalPorRol();

    formAltaPersonal?.addEventListener("submit", async ev => {
        ev.preventDefault();
        alertaAltaPersonal?.classList.add("d-none");

        const nombres = document.getElementById("personal-input-nombres")?.value.trim() || "";
        const apellidos = document.getElementById("personal-input-apellidos")?.value.trim() || "";
        const nombre = `${nombres} ${apellidos}`.trim();
        const email = document.getElementById("personal-input-email")?.value.trim().toLowerCase() || "";
        const rol = document.getElementById("personal-input-rol")?.value || "doctor";
        const cmvp = rol === "doctor" ? (document.getElementById("personal-input-cmvp")?.value.trim() || "") : "";
        const especialidad = rol === "doctor" ? (document.getElementById("personal-input-especialidad")?.value.trim() || "Medicina General") : "";
        const telefono = document.getElementById("personal-input-telefono")?.value.trim() || "";
        const password = document.getElementById("personal-input-password")?.value || "";
        const btnSubmit = document.getElementById("btn-submit-personal");

        if (nombres.length < 2 || apellidos.length < 2) {
            if (alertaAltaPersonal) {
                alertaAltaPersonal.textContent = "Ingresa tanto los nombres como los apellidos del personal (mínimo 2 caracteres cada uno).";
                alertaAltaPersonal.classList.remove("d-none");
            }
            return;
        }
        if (rol === "doctor" && !cmvp) {
            if (alertaAltaPersonal) {
                alertaAltaPersonal.textContent = "El número de colegiatura CMVP es obligatorio para registrar un Médico Veterinario.";
                alertaAltaPersonal.classList.remove("d-none");
            }
            inputPersonalCmvp?.focus();
            return;
        }

        if (btnSubmit) btnSubmit.disabled = true;
        try {
            const resp = await peticionApi("/api/admin/usuarios", {
                method: "POST",
                body: JSON.stringify({ nombre, nombres, apellidos, email, rol, cmvp, especialidad, telefono, password }),
            });
            const creadoId = resp?.usuario?.id ? `#${resp.usuario.id}` : "";
            formAltaPersonal.reset();
            sincronizarCamposPersonalPorRol();
            mostrarAlertaGlobal(
                `Personal '${nombre}' (${rol.toUpperCase()} ${creadoId}) almacenado permanentemente en SQL Server.`,
                "success"
            );
            await cargarPersonalAdmin();
            await cargarUsuariosAdmin();
            await cargarVisorBDResumen();
        } catch (err) {
            if (alertaAltaPersonal) {
                alertaAltaPersonal.textContent = err.message || "Error al registrar el personal.";
                alertaAltaPersonal.classList.remove("d-none");
            }
        } finally {
            if (btnSubmit) btnSubmit.disabled = false;
        }
    });

    async function cargarPersonalAdmin() {
        if (!contenedorPersonalAdmin) return;
        contenedorPersonalAdmin.replaceChildren();

        try {
            const data = await peticionApi("/api/admin/personal");
            const personal = Array.isArray(data?.personal) ? data.personal : [];

            if (badgeTotalPersonal) {
                badgeTotalPersonal.textContent = `${personal.length} trabajador(es) en SQL Server`;
            }

            if (!personal.length) {
                contenedorPersonalAdmin.innerHTML = "<p class='small text-muted mb-0'>No hay personal registrado en SQL Server.</p>";
                return;
            }

            const tableWrap = document.createElement("div");
            tableWrap.className = "table-responsive";
            tableWrap.innerHTML = `
                <table class="table table-hover align-middle small mb-0">
                    <thead class="table-light">
                        <tr>
                            <th>ID</th>
                            <th>Nombre y Teléfono</th>
                            <th>Correo Electrónico</th>
                            <th>Rol</th>
                            <th>Colegiatura CMVP</th>
                            <th>Especialidad / Área</th>
                            <th>Estado</th>
                        </tr>
                    </thead>
                    <tbody id="tbody-personal-admin"></tbody>
                </table>
            `;
            const tbody = tableWrap.querySelector("#tbody-personal-admin");

            for (const p of personal) {
                const tr = document.createElement("tr");
                const badgeClase = p.estado === "activo" ? "bg-success" : "bg-danger";
                const rolEtiqueta = p.rol === "admin" ? "ADMIN" : "DOCTOR";
                const idEtiqueta = p.usuario_id ? `#${p.usuario_id}` : `VET-${p.id_veterinario}`;
                const cmvpTexto = p.cmvp ? `<code>${escapeHtml(p.cmvp)}</code>` : '<span class="text-muted">N/A (Admin)</span>';
                const emailTexto = p.email ? escapeHtml(p.email) : '<span class="text-muted">Sin cuenta web</span>';
                const nombreCompleto = (p.nombres || p.apellidos)
                    ? `${p.nombres || ""} ${p.apellidos || ""}`.trim()
                    : (p.nombre || "Sin nombre");

                tr.innerHTML = `
                    <td><strong>${escapeHtml(idEtiqueta)}</strong></td>
                    <td><strong>${escapeHtml(nombreCompleto)}</strong><br><small class="text-muted">${escapeHtml(p.telefono || "Sin teléfono")}</small></td>
                    <td>${emailTexto}</td>
                    <td><span class="badge bg-light text-dark border">${rolEtiqueta}</span></td>
                    <td>${cmvpTexto}</td>
                    <td>${escapeHtml(p.especialidad || "Medicina General")}</td>
                    <td><span class="badge ${badgeClase}">${escapeHtml((p.estado || "activo").toUpperCase())}</span></td>
                `;
                tbody.append(tr);
            }

            contenedorPersonalAdmin.append(tableWrap);
        } catch (err) {
            contenedorPersonalAdmin.textContent = "";
            const pErr = document.createElement("p");
            pErr.className = "small text-danger mb-0";
            pErr.textContent = `Error al consultar personal en SQL Server: ${err.message}`;
            contenedorPersonalAdmin.append(pErr);
        }
    }

    async function cargarUsuariosAdmin() {
        if (!contenedorUsuariosAdmin) return;
        contenedorUsuariosAdmin.replaceChildren();

        try {
            const data = await peticionApi("/api/admin/crm?demo=0&page=1&page_size=25");
            const usuarios = Array.isArray(data?.usuarios) ? data.usuarios : [];

            const tableWrap = document.createElement("div");
            tableWrap.className = "table-responsive";
            tableWrap.innerHTML = `
                <table class="table table-hover align-middle small mb-0">
                    <thead class="table-light">
                        <tr>
                            <th>ID</th>
                            <th>Nombre</th>
                            <th>Email</th>
                            <th>Rol / CMVP</th>
                            <th>Estado</th>
                            <th>Acciones</th>
                        </tr>
                    </thead>
                    <tbody id="tbody-usuarios-admin"></tbody>
                </table>
            `;
            const tbody = tableWrap.querySelector("#tbody-usuarios-admin");

            for (const u of usuarios) {
                const tr = document.createElement("tr");
                const badgeClase = u.estado === "activo" ? "bg-success" : "bg-danger";
                const extraCredencial = u.cmvp ? `<br><small class="text-muted"><code>${escapeHtml(u.cmvp)}</code> · ${escapeHtml(u.especialidad || "Medicina General")}</small>` : "";

                tr.innerHTML = `
                    <td>${Number(u.id)}</td>
                    <td><strong>${escapeHtml(u.nombre)}</strong></td>
                    <td>${escapeHtml(u.email)}</td>
                    <td><span class="badge bg-light text-dark border">${escapeHtml(u.rol)}</span>${extraCredencial}</td>
                    <td><span class="badge ${badgeClase}">${escapeHtml((u.estado || "activo").toUpperCase())}</span></td>
                    <td>
                        <button type="button" class="btn btn-outline-${u.estado === "activo" ? "danger" : "success"} btn-sm py-0 px-2 btn-toggle-estado" data-id="${Number(u.id)}" data-estado="${escapeHtml(u.estado)}" style="font-size: 0.75rem;">
                            ${u.estado === "activo" ? "Suspender" : "Activar"}
                        </button>
                    </td>
                `;

                tr.querySelector(".btn-toggle-estado")?.addEventListener("click", async () => {
                    const nuevo = u.estado === "activo" ? "inactivo" : "activo";
                    try {
                        await peticionApi(`/api/admin/usuarios/${u.id}/estado`, {
                            method: "PATCH",
                            body: JSON.stringify({ estado: nuevo }),
                        });
                        mostrarAlertaGlobal(`Estado del usuario #${u.id} actualizado a ${nuevo}.`, "info");
                        await cargarUsuariosAdmin();
                        await cargarPersonalAdmin();
                    } catch (err) {
                        mostrarAlertaGlobal(err.message || "No se pudo cambiar el estado del usuario.", "danger");
                    }
                });

                tbody.append(tr);
            }

            contenedorUsuariosAdmin.append(tableWrap);
        } catch (err) {
            contenedorUsuariosAdmin.textContent = "";
            const pErr = document.createElement("p");
            pErr.className = "small text-danger mb-0";
            pErr.textContent = `Error: ${err.message}`;
            contenedorUsuariosAdmin.append(pErr);
        }
    }

    async function cargarVisorBDResumen() {
        if (!contenedorVisorTablas) return;
        contenedorVisorTablas.replaceChildren();

        try {
            const data = await peticionApi("/api/bd/tablas?limit=100");
            const tablas = data?.tablas || {};
            const nombres = Object.keys(tablas);

            const grid = document.createElement("div");
            grid.className = "row g-2";

            for (const t of nombres) {
                const col = document.createElement("div");
                col.className = "col-6 col-sm-4 col-md-3";
                col.innerHTML = `
                    <div class="p-2 border rounded bg-light text-center">
                        <strong class="d-block small text-dark">${escapeHtml(t)}</strong>
                        <span class="badge bg-secondary small">${tablas[t]?.length || 0} filas</span>
                    </div>
                `;
                grid.append(col);
            }
            contenedorVisorTablas.append(grid);
        } catch (err) {
            contenedorVisorTablas.innerHTML = `<p class="small text-danger mb-0">Error: ${escapeHtml(err.message)}</p>`;
        }
    }

    return {
        cargarAgendaDoctor,
        cargarFarmaciaDoctor,
        cargarCRMAdmin,
        actualizarContadorSolicitudesPendientes,
        cargarSolicitudesAdmin,
        cargarPersonalAdmin,
        cargarUsuariosAdmin,
        cargarVisorBDResumen,
    };
}
