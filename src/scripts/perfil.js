import { peticionApi, obtenerSesion, guardarSesion, cerrarSesion, descargarPdfDesdeBase64 } from "./api-client.js";

(() => {
    // Referencias principales del layout
    const bannerNombre = document.getElementById("perfil-usuario-nombre");
    const bannerRol = document.getElementById("perfil-usuario-rol");
    const bannerEstado = document.getElementById("perfil-usuario-estado");
    const bannerDetalle = document.getElementById("perfil-usuario-detalle");
    const bannerAvatar = document.getElementById("perfil-avatar");
    const alertaGlobal = document.getElementById("alerta-perfil-global");
    const btnCerrarSesionPerfil = document.getElementById("btn-cerrar-sesion-perfil");
    const btnSidebarCerrarSesion = document.getElementById("btn-sidebar-cerrar-sesion");

    // Menú de navegación por pestañas
    const menuTabs = document.getElementById("menu-tabs-perfil");
    const paneles = document.querySelectorAll(".tab-panel-contenido");
    const badgeContadorSolicitudes = document.getElementById("badge-contador-solicitudes");

    // Referencias: Panel Mi Perfil
    const campoNombre = document.getElementById("perfil-campo-nombre");
    const campoEmail = document.getElementById("perfil-campo-email");
    const campoTelefono = document.getElementById("perfil-campo-telefono");
    const campoRol = document.getElementById("perfil-campo-rol");
    const badgeEstadoDoc = document.getElementById("badge-estado-doc-perfil");
    const contenedorDoc = document.getElementById("contenedor-doc-perfil");
    const formVincularDoc = document.getElementById("form-vincular-doc-perfil");
    const selectTipoDoc = document.getElementById("perfil-select-tipo-doc");
    const inputNumDoc = document.getElementById("perfil-input-num-doc");
    const btnCancelarVincularDoc = document.getElementById("btn-cancelar-vincular-doc");
    const formCambiarPassword = document.getElementById("form-cambiar-password");
    const alertaPassword = document.getElementById("alerta-cambio-password");

    // Referencias: Panel Mis Mascotas
    const contenedorListaMascotas = document.getElementById("contenedor-lista-mascotas");
    const contenedorMisSolicitudes = document.getElementById("contenedor-mis-solicitudes");
    const btnToggleAltaMascota = document.getElementById("btn-toggle-alta-mascota");
    const wrapAltaMascota = document.getElementById("wrap-alta-mascota");
    const formAltaMascota = document.getElementById("form-alta-mascota");
    const btnCancelarAltaMascota = document.getElementById("btn-cancelar-alta-mascota");
    const alertaAltaMascota = document.getElementById("alerta-alta-mascota");

    // Referencias: Modal Solicitud de Mascota
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

    // Referencias: Panel Mis Compras
    const contenedorMisCompras = document.getElementById("contenedor-mis-compras");

    // Referencias: Panel Métodos de Pago
    const btnMockAgregarTarjeta = document.getElementById("btn-mock-agregar-tarjeta");

    // Referencias: Panel Mis Citas (Cliente)
    const contenedorMisCitas = document.getElementById("contenedor-mis-citas");

    // Referencias: Panel Agenda (Doctor)
    const contenedorAgendaDoctor = document.getElementById("contenedor-agenda-doctor");
    const wrapAtencionDoctor = document.getElementById("wrap-atencion-doctor");
    const formAtencionDoctor = document.getElementById("form-atencion-doctor");
    const inputAtencionCitaId = document.getElementById("doctor-input-cita-id");
    const infoPacienteAtencion = document.getElementById("doctor-info-paciente");
    const inputDiagnostico = document.getElementById("doctor-input-diagnostico");
    const inputTratamiento = document.getElementById("doctor-input-tratamiento");
    const btnCancelarAtencion = document.getElementById("btn-cancelar-atencion");
    const alertaAtencionDoctor = document.getElementById("alerta-atencion-doctor");

    // Referencias: Panel Farmacia (Doctor)
    const contenedorFarmaciaDoctor = document.getElementById("contenedor-farmacia-doctor");

    // Referencias: Panel CRM (Admin)
    const contenedorCrmAdmin = document.getElementById("contenedor-crm-admin");

    // Referencias: Panel Solicitudes (Admin)
    const contenedorSolicitudesAdmin = document.getElementById("contenedor-solicitudes-admin");

    // Referencias: Panel Personal (Admin)
    const formAltaPersonal = document.getElementById("form-alta-personal");
    const alertaAltaPersonal = document.getElementById("alerta-alta-personal");

    // Referencias: Panel Usuarios (Admin)
    const contenedorUsuariosAdmin = document.getElementById("contenedor-usuarios-admin");

    // Referencias: Panel Visor 16 Tablas (Admin)
    const contenedorVisorTablas = document.getElementById("contenedor-visor-tablas-resumen");

    let modalSolicitudInstance = null;
    let usuarioActual = null;

    function mostrarAlertaGlobal(mensaje, tipo = "info") {
        if (!alertaGlobal) return;
        alertaGlobal.className = `alert alert-${tipo} py-2 px-3 small`;
        alertaGlobal.textContent = mensaje;
        alertaGlobal.classList.remove("d-none");
        window.scrollTo({ top: 0, behavior: "smooth" });
        setTimeout(() => {
            alertaGlobal.classList.add("d-none");
        }, 6000);
    }

    function cerrarSesionYSalir() {
        cerrarSesion();
        window.location.href = "/";
    }

    btnCerrarSesionPerfil?.addEventListener("click", cerrarSesionYSalir);
    btnSidebarCerrarSesion?.addEventListener("click", cerrarSesionYSalir);

    // =========================================================================
    // NAVEGACIÓN SPA POR PESTAÑAS
    // =========================================================================
    function activarTab(targetId) {
        // Actualizar botones de la barra lateral
        const tabBotones = menuTabs?.querySelectorAll(".nav-link") || [];
        tabBotones.forEach(btn => {
            if (btn.getAttribute("data-tab-target") === targetId) {
                btn.classList.add("active");
                btn.setAttribute("aria-selected", "true");
            } else {
                btn.classList.remove("active");
                btn.setAttribute("aria-selected", "false");
            }
        });

        // Actualizar paneles de contenido
        paneles.forEach(panel => {
            if (panel.id === targetId.replace("tab-", "panel-")) {
                panel.classList.remove("d-none");
            } else {
                panel.classList.add("d-none");
            }
        });

        // Cargar datos bajo demanda según la pestaña
        if (targetId === "tab-mascotas") cargarMisMascotas();
        if (targetId === "tab-compras") cargarMisCompras();
        if (targetId === "tab-citas") cargarMisCitas();
        if (targetId === "tab-agenda") cargarAgendaDoctor();
        if (targetId === "tab-farmacia") cargarFarmaciaDoctor();
        if (targetId === "tab-crm") cargarCRMAdmin();
        if (targetId === "tab-solicitudes") cargarSolicitudesAdmin();
        if (targetId === "tab-usuarios") cargarUsuariosAdmin();
        if (targetId === "tab-bd") cargarVisorBDResumen();
    }

    menuTabs?.addEventListener("click", e => {
        const boton = e.target.closest("[data-tab-target]");
        if (!boton) return;
        const targetId = boton.getAttribute("data-tab-target");
        activarTab(targetId);
    });

    // =========================================================================
    // INICIALIZACIÓN DE LA SESIÓN Y CONTROL DE ACCESO
    // =========================================================================
    async function inicializarSesion() {
        const sesion = obtenerSesion();
        if (!sesion?.token) {
            // Usuario no autenticado: redirigir o invitar al login
            if (bannerNombre) bannerNombre.textContent = "Acceso Restringido";
            if (bannerDetalle) bannerDetalle.textContent = "Debes iniciar sesión para consultar tu perfil.";
            mostrarAlertaGlobal("Por favor inicia sesión para acceder a tu panel de perfil.", "warning");
            setTimeout(() => {
                const modalLoginEl = document.getElementById("modalLogin");
                if (modalLoginEl && window.bootstrap?.Modal) {
                    window.bootstrap.Modal.getOrCreateInstance(modalLoginEl).show();
                }
            }, 400);
            return;
        }

        usuarioActual = sesion.usuario || {};

        // 1. Renderizar Banner Superior
        const nombre = usuarioActual.nombre || "Usuario Patitas Felices";
        const email = usuarioActual.email || "";
        const rol = (usuarioActual.rol || "cliente").toLowerCase();
        const telefono = usuarioActual.telefono || "Sin teléfono registrado";

        if (bannerNombre) bannerNombre.textContent = nombre;
        if (bannerDetalle) bannerDetalle.textContent = `${email} · Teléfono: ${telefono}`;
        if (bannerAvatar) {
            const partes = nombre.split(" ");
            const iniciales = (partes[0]?.[0] || "P") + (partes[1]?.[0] || "F");
            bannerAvatar.textContent = iniciales.toUpperCase();
        }

        let etiquetaRol = "Cliente / Propietario";
        if (rol === "doctor") etiquetaRol = "Médico Veterinario";
        if (rol === "admin") etiquetaRol = "Administrador de la Clínica";
        if (bannerRol) bannerRol.textContent = etiquetaRol;

        // 2. Filtrar Pestañas del Menú Lateral por Rol
        const tabBotones = menuTabs?.querySelectorAll("[data-role-filter]") || [];
        tabBotones.forEach(btn => {
            const rolFiltro = btn.getAttribute("data-role-filter");
            if (rolFiltro === rol || (rol === "admin" && (rolFiltro === "doctor" || rolFiltro === "cliente"))) {
                btn.classList.remove("d-none");
            } else {
                btn.classList.add("d-none");
            }
        });

        // 3. Cargar Mi Perfil
        await cargarMiPerfil();

        // 4. Si hay hash en la URL (ej. #mascotas desde el modal de citas), activar esa pestaña
        const hashLimpio = (window.location.hash || "").replace(/^#/, "").replace(/^panel-/, "").replace(/^tab-/, "");
        if (hashLimpio) {
            const tabObjetivo = `tab-${hashLimpio}`;
            const existeTab = menuTabs?.querySelector(`[data-tab-target="${tabObjetivo}"]:not(.d-none)`);
            if (existeTab) {
                activarTab(tabObjetivo);
            }
        }

        // Si es admin, cargar contador de solicitudes pendientes
        if (rol === "admin") {
            actualizarContadorSolicitudesPendientes();
        }
    }

    // =========================================================================
    // 1. MI PERFIL (Datos, DNI/RUC inmutable, Cambiar Contraseña)
    // =========================================================================
    async function cargarMiPerfil() {
        try {
            const data = await peticionApi("/api/auth/sesion");
            const u = data.usuario || usuarioActual || {};
            usuarioActual = u;

            if (campoNombre) campoNombre.textContent = u.nombre || "-";
            if (campoEmail) campoEmail.textContent = u.email || "-";
            if (campoTelefono) campoTelefono.textContent = u.telefono || "Sin registrar";
            if (campoRol) {
                const r = (u.rol || "cliente").toLowerCase();
                campoRol.textContent = r === "admin" ? "Administrador" : r === "doctor" ? "Médico Veterinario" : "Cliente / Propietario";
            }

            // DNI / RUC
            const tieneDoc = Boolean(u.documento && String(u.documento).trim());
            if (tieneDoc) {
                const docVal = String(u.documento).trim();
                const tipoVal = u.tipo_documento || (docVal.length === 11 ? "RUC" : "DNI");
                if (badgeEstadoDoc) {
                    badgeEstadoDoc.textContent = "Verificado";
                    badgeEstadoDoc.className = "badge bg-success-subtle text-success border border-success-subtle small";
                }
                if (contenedorDoc) {
                    contenedorDoc.replaceChildren();
                    const p = document.createElement("p");
                    p.className = "mb-0 fw-semibold text-dark";
                    p.innerHTML = `<span class="badge bg-light text-dark border me-2">${tipoVal}: ${docVal}</span> <span class="small text-muted fw-normal">Identificador oficial verificado (no modificable).</span>`;
                    contenedorDoc.append(p);
                }
                formVincularDoc?.classList.add("d-none");
            } else {
                if (badgeEstadoDoc) {
                    badgeEstadoDoc.textContent = "Por vincular";
                    badgeEstadoDoc.className = "badge bg-light text-secondary border small";
                }
                if (contenedorDoc) {
                    contenedorDoc.replaceChildren();
                    const wrapSinDoc = document.createElement("div");
                    wrapSinDoc.className = "d-flex flex-wrap align-items-center justify-content-between gap-2";
                    
                    const p = document.createElement("p");
                    p.className = "mb-0 small text-muted";
                    p.textContent = "Aún no has vinculado tu DNI o RUC a tu cuenta.";
                    
                    const btnAbrir = document.createElement("button");
                    btnAbrir.type = "button";
                    btnAbrir.className = "btn btn-outline-dark btn-sm";
                    btnAbrir.textContent = "+ Vincular DNI o RUC";
                    btnAbrir.addEventListener("click", () => {
                        formVincularDoc?.classList.remove("d-none");
                        inputNumDoc?.focus();
                    });

                    wrapSinDoc.append(p, btnAbrir);
                    contenedorDoc.append(wrapSinDoc);
                }
            }
        } catch {
            // Usar datos locales si falla la consulta
        }
    }

    // Vincular DNI / RUC desde el perfil
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
            await cargarMiPerfil();
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    });

    // Cambiar contraseña
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

    // =========================================================================
    // 2. MIS MASCOTAS (Listado, Alta y Solicitudes justificadas)
    // =========================================================================
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

                    // Botón Solicitar Edición
                    const btnEditar = document.createElement("button");
                    btnEditar.type = "button";
                    btnEditar.className = "btn btn-outline-secondary btn-sm py-0 px-2";
                    btnEditar.style.fontSize = "0.75rem";
                    btnEditar.textContent = "Solicitar edición";
                    btnEditar.addEventListener("click", () => abrirModalSolicitud("editar", m));

                    // Botón Solicitar Baja
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

            // Consultar solicitudes enviadas
            cargarMisSolicitudes();
        } catch (err) {
            contenedorListaMascotas.innerHTML = `<p class="small text-danger mb-0">Error al cargar mascotas: ${err.message}</p>`;
        }
    }

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
                        <span class="badge ${badgeEstado} small" style="font-size: 0.68rem;">${s.estado.toUpperCase()}</span>
                    </div>
                    <p class="small text-muted mb-0"><strong>Mascota:</strong> ${s.mascota_nombre || "Paciente"} · <strong>Motivo:</strong> ${s.motivo}</p>
                `;
                li.append(info);
                ul.append(li);
            }
            contenedorMisSolicitudes.replaceChildren(ul);
        } catch {
            // Silenciar si no aplica
        }
    }

    // Modal de Solicitud con justificación
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

    // =========================================================================
    // 3. MIS COMPRAS Y BOLETAS (Historial y Descargas)
    // =========================================================================
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
                    <td><strong>${c.numero_boleta}</strong></td>
                    <td class="text-muted">${(c.creado_en || "").substring(0, 10)}</td>
                    <td class="text-secondary">${resumenItems}</td>
                    <td><strong>S/ ${parseFloat(c.total).toFixed(2)}</strong></td>
                    <td>
                        <div class="d-flex gap-1">
                            <a href="/api/tienda/boleta/${c.id}/pdf" target="_blank" class="btn btn-outline-success btn-sm py-0 px-2" style="font-size: 0.75rem;">
                                PDF
                            </a>
                        </div>
                    </td>
                `;
                tbody.append(tr);
            }

            tableWrap.append(table);
            contenedorMisCompras.append(tableWrap);
        } catch (err) {
            contenedorMisCompras.innerHTML = `<p class="small text-danger mb-0">Error al cargar compras: ${err.message}</p>`;
        }
    }

    // =========================================================================
    // 4. MÉTODOS DE PAGO (Ejemplar visual / Maqueta)
    // =========================================================================
    btnMockAgregarTarjeta?.addEventListener("click", () => {
        alert("En este entorno demostrativo no se procesan tarjetas reales. Tus compras en Patitas Felices generan boleta inmediata y se coordinan en caja o vía Yape/Plin.");
    });

    // =========================================================================
    // 5. MIS CITAS MÉDICAS (Cliente)
    // =========================================================================
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
                        <strong class="text-dark small">${c.mascota_nombre} · ${c.servicio}</strong>
                        <span class="badge ${badgeClase} small" style="font-size: 0.7rem;">${(c.estado || "pendiente").toUpperCase()}</span>
                    </div>
                    <p class="small text-muted mb-1">Fecha: ${c.fecha} a las ${c.hora} (Lima)</p>
                    <p class="small text-secondary mb-1"><strong>Motivo:</strong> ${c.motivo}</p>
                    ${c.diagnostico ? `<p class="small border-top pt-2 mb-0 text-dark"><strong>Evaluación médica:</strong> ${c.diagnostico} — <strong>Tratamiento:</strong> ${c.tratamiento || "Sin indicaciones"}</p>` : ""}
                `;
                contenedorMisCitas.append(card);
            }
        } catch (err) {
            contenedorMisCitas.innerHTML = `<p class="small text-danger mb-0">Error: ${err.message}</p>`;
        }
    }

    // =========================================================================
    // 6. AGENDA Y CATÁLOGO DEL DOCTOR
    // =========================================================================
    async function cargarAgendaDoctor() {
        if (!contenedorAgendaDoctor) return;
        contenedorAgendaDoctor.replaceChildren();

        try {
            const data = await peticionApi("/api/doctor/agenda");
            const citas = Array.isArray(data?.citas) ? data.citas : [];

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
                            <strong class="text-dark">Paciente: ${c.mascota_nombre}</strong>
                            <small class="text-muted d-block">Propietario: ${c.propietario} (${c.telefono})</small>
                        </div>
                        <span class="badge ${badgeClase}">${(c.estado || "pendiente").toUpperCase()}</span>
                    </div>
                    <p class="small mb-1"><strong>Servicio:</strong> ${c.servicio} · <strong>Fecha:</strong> ${c.fecha} (${c.hora})</p>
                    <p class="small text-muted mb-2"><strong>Motivo:</strong> ${c.motivo}</p>
                    <div class="d-flex gap-2">
                        ${c.estado === "pendiente" ? `<button type="button" class="btn btn-outline-primary btn-sm py-0 px-2 btn-confirmar-cita" data-id="${c.id}">Confirmar cita</button>` : ""}
                        ${c.estado !== "atendida" ? `<button type="button" class="btn btn-success btn-sm py-0 px-2 btn-atender-cita" data-id="${c.id}" data-paciente="${c.mascota_nombre}">Atender paciente</button>` : ""}
                        ${c.estado !== "cancelada" && c.estado !== "atendida" ? `<button type="button" class="btn btn-outline-danger btn-sm py-0 px-2 btn-cancelar-cita" data-id="${c.id}">Cancelar</button>` : ""}
                    </div>
                    ${c.diagnostico ? `<div class="mt-2 pt-2 border-top small text-dark"><strong>Diagnóstico:</strong> ${c.diagnostico}<br><strong>Tratamiento:</strong> ${c.tratamiento}</div>` : ""}
                `;

                // Eventos de botones
                card.querySelector(".btn-confirmar-cita")?.addEventListener("click", async () => {
                    await peticionApi(`/api/doctor/citas/${c.id}`, { method: "PATCH", body: JSON.stringify({ estado: "confirmada" }) });
                    await cargarAgendaDoctor();
                });

                card.querySelector(".btn-cancelar-cita")?.addEventListener("click", async () => {
                    if (!confirm("¿Deseas cancelar esta cita?")) return;
                    await peticionApi(`/api/doctor/citas/${c.id}`, { method: "PATCH", body: JSON.stringify({ estado: "cancelada" }) });
                    await cargarAgendaDoctor();
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
            contenedorAgendaDoctor.innerHTML = `<p class="small text-danger mb-0">Error: ${err.message}</p>`;
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
                    <td><code>${p.codigo}</code></td>
                    <td><strong>${p.nombre}</strong></td>
                    <td>${p.categoria}</td>
                    <td>S/ ${parseFloat(p.precio).toFixed(2)}</td>
                    <td><span class="badge ${p.stock > 5 ? 'bg-success' : 'bg-warning text-dark'}">${p.stock} unid.</span></td>
                `;
                tbody.append(tr);
            }
            contenedorFarmaciaDoctor.append(tableWrap);
        } catch (err) {
            contenedorFarmaciaDoctor.innerHTML = `<p class="small text-danger mb-0">Error: ${err.message}</p>`;
        }
    }

    // =========================================================================
    // 7. ADMINISTRACIÓN (CRM, Solicitudes, Personal, Usuarios y Visor)
    // =========================================================================
    async function cargarCRMAdmin() {
        if (!contenedorCrmAdmin) return;
        contenedorCrmAdmin.replaceChildren();

        try {
            const data = await peticionApi("/api/admin/crm");
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
                        <small class="text-muted d-block">Ingresos Totales ${balance.modo_demostracion ? '<span class="badge bg-secondary-subtle text-secondary border ms-1">Ref.</span>' : ''}</small>
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
                    <td><strong>${v.numero_boleta}</strong></td>
                    <td>${v.cliente_nombre}</td>
                    <td class="text-secondary">${detalleTexto}</td>
                    <td><code>${v.cliente_documento || "-"}</code></td>
                    <td><span class="badge bg-light text-dark border">${v.metodo_pago || "Yape / Tarjeta"}</span></td>
                    <td><strong>S/ ${parseFloat(v.total || 0).toFixed(2)}</strong></td>
                    <td>
                        ${esDemo
                            ? `<span class="badge bg-secondary-subtle text-secondary border">Referencia</span>`
                            : `<a href="/api/tienda/boleta/${v.id}/pdf" target="_blank" class="btn btn-outline-success btn-sm py-0 px-2" style="font-size: 0.72rem;">PDF</a>`
                        }
                    </td>
                `;
                tbody.append(tr);
            }
            contenedorCrmAdmin.append(tableWrap);

            // Resumen rápido de citas clínicas en el CRM
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
                        <td><strong>${c.mascota_nombre}</strong></td>
                        <td>${c.propietario} <small class="text-muted">(${c.telefono || "-"})</small></td>
                        <td>${c.servicio}</td>
                        <td>${c.fecha} · ${c.hora}</td>
                        <td><span class="badge ${badgeEstado}">${(c.estado || "pendiente").toUpperCase()}</span></td>
                    `;
                    tbodyCitas.append(tr);
                }
                contenedorCrmAdmin.append(citasWrap);
            }
        } catch (err) {
            contenedorCrmAdmin.innerHTML = `<p class="small text-danger mb-0">Error: ${err.message}</p>`;
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
            // Ignorar
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
                    detalleNuevos = `<br><small class="text-primary">Nuevos datos: ${dn.nombre || ""} · ${dn.especie || ""} · ${dn.raza || ""} · ${dn.edad || ""}a · ${dn.peso_kg || ""}kg</small>`;
                }

                tr.innerHTML = `
                    <td><strong>${s.propietario_nombre || "Cliente"}</strong><br><small class="text-muted">${s.propietario_email || ""}</small></td>
                    <td><strong>${s.mascota_nombre || "Paciente"}</strong></td>
                    <td><span class="badge bg-light text-dark border">${s.tipo === "editar" ? "Modificación" : "Baja"}</span></td>
                    <td>${s.motivo}${detalleNuevos}</td>
                    <td><span class="badge ${badgeClase}">${s.estado.toUpperCase()}</span></td>
                    <td>
                        ${s.estado === "pendiente" ? `
                            <div class="d-flex gap-1">
                                <button type="button" class="btn btn-success btn-sm py-0 px-2 btn-aprobar-sol" data-id="${s.id}" style="font-size: 0.75rem;">Aprobar</button>
                                <button type="button" class="btn btn-outline-danger btn-sm py-0 px-2 btn-rechazar-sol" data-id="${s.id}" style="font-size: 0.75rem;">Rechazar</button>
                            </div>
                        ` : `<small class="text-muted">Procesada</small>`}
                    </td>
                `;

                tr.querySelector(".btn-aprobar-sol")?.addEventListener("click", async () => {
                    await peticionApi(`/api/admin/solicitudes-mascotas/${s.id}/resolver`, { method: "POST", body: JSON.stringify({ accion: "aprobar" }) });
                    mostrarAlertaGlobal(`Solicitud #${s.id} aprobada con éxito.`, "success");
                    await cargarSolicitudesAdmin();
                    actualizarContadorSolicitudesPendientes();
                });

                tr.querySelector(".btn-rechazar-sol")?.addEventListener("click", async () => {
                    await peticionApi(`/api/admin/solicitudes-mascotas/${s.id}/resolver`, { method: "POST", body: JSON.stringify({ accion: "rechazar" }) });
                    mostrarAlertaGlobal(`Solicitud #${s.id} rechazada.`, "info");
                    await cargarSolicitudesAdmin();
                    actualizarContadorSolicitudesPendientes();
                });

                tbody.append(tr);
            }

            contenedorSolicitudesAdmin.append(tableWrap);
        } catch (err) {
            contenedorSolicitudesAdmin.innerHTML = `<p class="small text-danger mb-0">Error: ${err.message}</p>`;
        }
    }

    formAltaPersonal?.addEventListener("submit", async ev => {
        ev.preventDefault();
        alertaAltaPersonal?.classList.add("d-none");

        const nombre = document.getElementById("personal-input-nombre").value.trim();
        const email = document.getElementById("personal-input-email").value.trim().toLowerCase();
        const rol = document.getElementById("personal-input-rol").value;
        const cmvp = document.getElementById("personal-input-cmvp").value.trim();
        const especialidad = document.getElementById("personal-input-especialidad").value.trim();
        const telefono = document.getElementById("personal-input-telefono").value.trim();
        const password = document.getElementById("personal-input-password").value;

        try {
            await peticionApi("/api/admin/usuarios", {
                method: "POST",
                body: JSON.stringify({ nombre, email, rol, cmvp, especialidad, telefono, password }),
            });
            formAltaPersonal.reset();
            mostrarAlertaGlobal(`Personal '${nombre}' (${rol}) registrado exitosamente.`, "success");
        } catch (err) {
            alertaAltaPersonal.textContent = err.message || "Error al registrar el personal.";
            alertaAltaPersonal.classList.remove("d-none");
        }
    });

    async function cargarUsuariosAdmin() {
        if (!contenedorUsuariosAdmin) return;
        contenedorUsuariosAdmin.replaceChildren();

        try {
            const data = await peticionApi("/api/admin/crm");
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
                            <th>Rol</th>
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

                tr.innerHTML = `
                    <td>${u.id}</td>
                    <td><strong>${u.nombre}</strong></td>
                    <td>${u.email}</td>
                    <td><span class="badge bg-light text-dark border">${u.rol}</span></td>
                    <td><span class="badge ${badgeClase}">${u.estado.toUpperCase()}</span></td>
                    <td>
                        <button type="button" class="btn btn-outline-${u.estado === 'activo' ? 'danger' : 'success'} btn-sm py-0 px-2 btn-toggle-estado" data-id="${u.id}" data-estado="${u.estado}" style="font-size: 0.75rem;">
                            ${u.estado === "activo" ? "Suspender" : "Activar"}
                        </button>
                    </td>
                `;

                tr.querySelector(".btn-toggle-estado")?.addEventListener("click", async () => {
                    const nuevo = u.estado === "activo" ? "inactivo" : "activo";
                    await peticionApi(`/api/admin/usuarios/${u.id}/estado`, {
                        method: "PATCH",
                        body: JSON.stringify({ estado: nuevo }),
                    });
                    mostrarAlertaGlobal(`Estado del usuario #${u.id} actualizado a ${nuevo}.`, "info");
                    await cargarUsuariosAdmin();
                });

                tbody.append(tr);
            }

            contenedorUsuariosAdmin.append(tableWrap);
        } catch (err) {
            contenedorUsuariosAdmin.innerHTML = `<p class="small text-danger mb-0">Error: ${err.message}</p>`;
        }
    }

    async function cargarVisorBDResumen() {
        if (!contenedorVisorTablas) return;
        contenedorVisorTablas.replaceChildren();

        try {
            const data = await peticionApi("/api/bd/tablas");
            const tablas = data?.tablas || {};
            const nombres = Object.keys(tablas);

            const grid = document.createElement("div");
            grid.className = "row g-2";

            for (const t of nombres) {
                const col = document.createElement("div");
                col.className = "col-6 col-sm-4 col-md-3";
                col.innerHTML = `
                    <div class="p-2 border rounded bg-light text-center">
                        <strong class="d-block small text-dark">${t}</strong>
                        <span class="badge bg-secondary small">${tablas[t]?.length || 0} filas</span>
                    </div>
                `;
                grid.append(col);
            }
            contenedorVisorTablas.append(grid);
        } catch (err) {
            contenedorVisorTablas.innerHTML = `<p class="small text-danger mb-0">Error: ${err.message}</p>`;
        }
    }

    // Inicializar al cargar el DOM
    document.addEventListener("DOMContentLoaded", inicializarSesion);
    if (document.readyState === "interactive" || document.readyState === "complete") {
        inicializarSesion();
    }
})();
