import { peticionApi, obtenerSesion, guardarSesion } from "./api-client.js";

(() => {
    const contenedorCitas = document.getElementById("contenedor-citas-doctor");
    if (!contenedorCitas) return;

    const contenedorMascotas = document.getElementById("contenedor-mascotas-doctor");
    const tituloDoctor = document.getElementById("perfil-doctor-titulo");
    const detalleDoctor = document.getElementById("perfil-doctor-detalle");
    const contadorCitas = document.getElementById("contador-citas-doctor");
    const btnRecargar = document.getElementById("btn-recargar-agenda");
    const formDiagnostico = document.getElementById("formulario-diagnostico");
    const alertaDoctor = document.getElementById("alerta-doctor");
    const inputCitaId = document.getElementById("doctor-cita-id");
    const selectEstado = document.getElementById("doctor-cita-estado");
    const inputDiag = document.getElementById("doctor-diagnostico");
    const inputTrat = document.getElementById("doctor-tratamiento");
    const infoCitaActiva = document.getElementById("doctor-cita-activa-info");

    async function asegurarSesionDoctor() {
        const sesion = obtenerSesion();
        if (!sesion?.token) {
            window.location.href = "/?abrir_login=1";
            throw new Error("Debes iniciar sesión como Médico Veterinario o Administrador.");
        }
        const verificada = await peticionApi("/api/auth/sesion");
        const rolReal = (verificada?.usuario?.rol || "").toLowerCase();
        const sesionSincronizada = {
            ...sesion,
            usuario: verificada.usuario,
            rbac: verificada.rbac || sesion.rbac,
        };
        guardarSesion(sesionSincronizada);
        if (rolReal !== "doctor" && rolReal !== "admin") {
            window.location.href = "/perfil";
            throw new Error("Acceso reservado para personal médico veterinario.");
        }
        return sesionSincronizada;
    }

    function renderizarCitas(citas) {
        contenedorCitas.replaceChildren();
        if (contadorCitas) {
            contadorCitas.textContent = `${citas.length} cita(s)`;
        }

        if (!citas.length) {
            const p = document.createElement("p");
            p.className = "small-note mb-0 text-muted";
            p.textContent = "No hay citas registradas en la agenda médica en este momento.";
            contenedorCitas.append(p);
            return;
        }

        for (const cita of citas) {
            const card = document.createElement("article");
            card.className = "role-item-card";

            const cabecera = document.createElement("div");
            cabecera.className = "d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2";
            const titulo = document.createElement("strong");
            titulo.className = "text-dark";
            titulo.textContent = `Cita #${cita.id} · Paciente: ${cita.mascota_nombre} (${cita.servicio})`;
            
            const badge = document.createElement("span");
            const estadoTexto = (cita.estado || "pendiente").toLowerCase();
            badge.className = estadoTexto === "confirmada" ? "status-label mb-0" : "badge bg-secondary-subtle text-dark mb-0";
            badge.textContent = estadoTexto.toUpperCase();
            cabecera.append(titulo, badge);

            const info = document.createElement("p");
            info.className = "small mb-1 text-muted";
            info.textContent = `Propietario: ${cita.propietario} (Tel: ${cita.telefono}) · Fecha programada: ${cita.fecha} a las ${cita.hora}`;

            const motivo = document.createElement("p");
            motivo.className = "small-note mb-2";
            motivo.textContent = `Motivo: ${cita.motivo}`;

            if (cita.diagnostico || cita.tratamiento) {
                const diag = document.createElement("p");
                diag.className = "small mb-2 text-muted pt-2 border-top";
                diag.textContent = `Diagnóstico: ${cita.diagnostico || "Sin diagnóstico"} | Indicaciones: ${cita.tratamiento || "Sin indicaciones"}`;
                card.append(cabecera, info, motivo, diag);
            } else {
                card.append(cabecera, info, motivo);
            }

            // Barra de acciones con 1 clic directo en la tarjeta
            const acciones = document.createElement("div");
            acciones.className = "d-flex flex-wrap gap-2 pt-2 border-top";

            // Botón 1: Confirmar cita (si está pendiente)
            if (estadoTexto === "pendiente") {
                const btnConfirmar = document.createElement("button");
                btnConfirmar.type = "button";
                btnConfirmar.className = "btn btn-outline-success btn-sm";
                btnConfirmar.textContent = "Confirmar cita";
                btnConfirmar.addEventListener("click", async () => {
                    btnConfirmar.disabled = true;
                    try {
                        await peticionApi(`/api/doctor/citas/${cita.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({
                                estado: "confirmada",
                                diagnostico: cita.diagnostico || "",
                                tratamiento: cita.tratamiento || ""
                            })
                        });
                        await cargarAgenda();
                    } catch (err) {
                        alert(`No se pudo confirmar la cita: ${err.message}`);
                        btnConfirmar.disabled = false;
                    }
                });
                acciones.append(btnConfirmar);
            }

            // Botón 2: Atender paciente y abrir ficha de evaluación médica
            const btnAtender = document.createElement("button");
            btnAtender.type = "button";
            btnAtender.className = "btn btn-primary btn-sm";
            btnAtender.textContent = "Atender paciente";
            btnAtender.addEventListener("click", () => {
                if (inputCitaId) inputCitaId.value = String(cita.id);
                if (selectEstado) selectEstado.value = "atendida";
                if (inputDiag) inputDiag.value = cita.diagnostico || "";
                if (inputTrat) inputTrat.value = cita.tratamiento || "";
                if (infoCitaActiva) {
                    infoCitaActiva.className = "alert alert-primary py-2 px-3 small mb-3";
                    infoCitaActiva.textContent = `Atendiendo Cita #${cita.id} · Paciente: ${cita.mascota_nombre} (${cita.propietario} - ${cita.servicio})`;
                }
                formDiagnostico?.scrollIntoView({ behavior: "smooth" });
                inputDiag?.focus();
            });
            acciones.append(btnAtender);

            // Botón 3: Cancelar cita
            if (estadoTexto !== "cancelada" && estadoTexto !== "atendida") {
                const btnCancelar = document.createElement("button");
                btnCancelar.type = "button";
                btnCancelar.className = "btn btn-outline-secondary btn-sm";
                btnCancelar.textContent = "Cancelar cita";
                btnCancelar.addEventListener("click", async () => {
                    if (!confirm(`¿Deseas cancelar la cita #${cita.id} de ${cita.mascota_nombre}?`)) return;
                    btnCancelar.disabled = true;
                    try {
                        await peticionApi(`/api/doctor/citas/${cita.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({
                                estado: "cancelada",
                                diagnostico: cita.diagnostico || "",
                                tratamiento: cita.tratamiento || ""
                            })
                        });
                        await cargarAgenda();
                    } catch (err) {
                        alert(`Error al cancelar: ${err.message}`);
                        btnCancelar.disabled = false;
                    }
                });
                acciones.append(btnCancelar);
            }

            card.append(acciones);
            contenedorCitas.append(card);
        }
    }

    function renderizarMascotas(mascotas) {
        if (!contenedorMascotas) return;
        contenedorMascotas.replaceChildren();
        for (const m of mascotas) {
            const col = document.createElement("div");
            col.className = "col-12 col-md-6";
            const box = document.createElement("div");
            box.className = "role-item-card h-100";
            const h3 = document.createElement("h3");
            h3.className = "h6 mb-1";
            h3.textContent = `${m.nombre} (${m.especie} · ${m.raza || "Mestizo"})`;
            const meta = document.createElement("p");
            meta.className = "small mb-1";
            meta.textContent = `Edad: ${m.edad} año(s) · Peso: ${m.peso_kg} kg · Propietario: ${m.propietario_nombre || ""}`;
            const notas = document.createElement("p");
            notas.className = "small-note mb-0";
            notas.textContent = m.historial_resumen || "Sin antecedentes registrados.";
            box.append(h3, meta, notas);
            col.append(box);
            contenedorMascotas.append(col);
        }
    }

    async function cargarAgenda() {
        try {
            await asegurarSesionDoctor();
            const data = await peticionApi("/api/doctor/agenda");
            if (data.perfil_profesional) {
                const prof = data.perfil_profesional;
                if (tituloDoctor) tituloDoctor.textContent = `${prof.nombre} · ${prof.colegiatura}`;
                if (detalleDoctor) detalleDoctor.textContent = `Especialidad: ${prof.especialidad} · Turno: ${prof.horario_turno}`;
            }
            renderizarCitas(data.citas || []);
            renderizarMascotas(data.mascotas || []);
        } catch (error) {
            if (contadorCitas) contadorCitas.textContent = "Sin conexión";
        }
    }

    formDiagnostico?.addEventListener("submit", async evento => {
        evento.preventDefault();
        if (!inputCitaId || !inputCitaId.value) {
            if (alertaDoctor) {
                alertaDoctor.className = "alert alert-warning py-2 px-3 small";
                alertaDoctor.textContent = "Por favor selecciona primero una cita de la lista con el botón 'Atender paciente'.";
                alertaDoctor.hidden = false;
            }
            return;
        }

        if (alertaDoctor) alertaDoctor.hidden = true;
        try {
            await asegurarSesionDoctor();
            const citaId = Number(inputCitaId.value);
            await peticionApi(`/api/doctor/citas/${citaId}`, {
                method: "PATCH",
                body: JSON.stringify({
                    estado: selectEstado?.value || "atendida",
                    diagnostico: inputDiag?.value?.trim() || "",
                    tratamiento: inputTrat?.value?.trim() || ""
                })
            });
            if (alertaDoctor) {
                alertaDoctor.className = "alert alert-success py-2 px-3 small";
                alertaDoctor.textContent = `¡Ficha médica de la cita #${citaId} guardada exitosamente!`;
                alertaDoctor.hidden = false;
            }
            if (infoCitaActiva) {
                infoCitaActiva.className = "alert alert-light border py-2 px-3 small mb-3 text-muted";
                infoCitaActiva.textContent = "Selecciona una cita de la lista con el botón 'Atender paciente' para redactar su evaluación.";
            }
            inputCitaId.value = "";
            await cargarAgenda();
        } catch (error) {
            if (alertaDoctor) {
                alertaDoctor.className = "alert alert-danger py-2 px-3 small";
                alertaDoctor.textContent = error.message || "No se pudo guardar la evaluación médica.";
                alertaDoctor.hidden = false;
            }
        }
    });

    btnRecargar?.addEventListener("click", cargarAgenda);
    cargarAgenda();
})();
