/**
 * perfil.js
 * Orquestador principal de perfil.astro: verifica la sesión activa (/api/auth/sesion),
 * renderiza el banner superior y los datos personales, filtra pestañas por rol ([data-roles])
 * y modo demo ([data-demo-only]), y delega la lógica específica a cliente-panel.js y admin-doctor-panel.js.
 */

import {
    cerrarSesion,
    guardarSesion,
    obtenerSesion,
    peticionApi,
} from "./api-client.js";
import { esModoDemoActivo, mostrarAlerta } from "./ui-utils.js";
import { crearControladorCliente } from "./perfil/cliente-panel.js";
import { crearControladorDoctorYAdmin } from "./perfil/admin-doctor-panel.js";

(() => {
    const bannerNombre = document.getElementById("perfil-usuario-nombre");
    const bannerRol = document.getElementById("perfil-usuario-rol");
    const bannerDetalle = document.getElementById("perfil-usuario-detalle");
    const bannerAvatar = document.getElementById("perfil-avatar");
    const alertaGlobal = document.getElementById("alerta-perfil-global");
    const btnCerrarSesionPerfil = document.getElementById("btn-cerrar-sesion-perfil");
    const btnSidebarCerrarSesion = document.getElementById("btn-sidebar-cerrar-sesion");

    const menuTabs = document.getElementById("menu-tabs-perfil");
    const paneles = document.querySelectorAll(".tab-panel-contenido");
    const badgeContadorSolicitudes = document.getElementById("badge-contador-solicitudes");

    const campoNombre = document.getElementById("perfil-campo-nombre");
    const campoEmail = document.getElementById("perfil-campo-email");
    const campoTelefono = document.getElementById("perfil-campo-telefono");
    const campoRol = document.getElementById("perfil-campo-rol");
    const badgeEstadoDoc = document.getElementById("badge-estado-doc-perfil");
    const contenedorDoc = document.getElementById("contenedor-doc-perfil");
    const formVincularDoc = document.getElementById("form-vincular-doc-perfil");

    let usuarioActual = null;
    const modoDemo = esModoDemoActivo();

    function mostrarAlertaGlobal(mensaje, tipo = "info") {
        mostrarAlerta(alertaGlobal, mensaje, tipo, 6000);
        if (alertaGlobal) window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function cerrarSesionYSalir() {
        cerrarSesion();
        window.location.href = "/";
    }

    btnCerrarSesionPerfil?.addEventListener("click", cerrarSesionYSalir);
    btnSidebarCerrarSesion?.addEventListener("click", cerrarSesionYSalir);

    const clienteCtrl = crearControladorCliente({
        mostrarAlertaGlobal,
        recargarPerfil: cargarMiPerfil,
    });
    const staffCtrl = crearControladorDoctorYAdmin({
        mostrarAlertaGlobal,
        badgeContadorSolicitudes,
    });

    function activarTab(targetId) {
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

        paneles.forEach(panel => {
            if (panel.id === targetId.replace("tab-", "panel-")) {
                panel.classList.remove("d-none");
            } else {
                panel.classList.add("d-none");
            }
        });

        if (targetId === "tab-mascotas") clienteCtrl.cargarMisMascotas();
        if (targetId === "tab-compras") clienteCtrl.cargarMisCompras();
        if (targetId === "tab-citas") clienteCtrl.cargarMisCitas();
        if (targetId === "tab-agenda") staffCtrl.cargarAgendaDoctor();
        if (targetId === "tab-farmacia") staffCtrl.cargarFarmaciaDoctor();
        if (targetId === "tab-crm") staffCtrl.cargarCRMAdmin();
        if (targetId === "tab-solicitudes") staffCtrl.cargarSolicitudesAdmin();
        if (targetId === "tab-personal") staffCtrl.cargarPersonalAdmin();
        if (targetId === "tab-usuarios") staffCtrl.cargarUsuariosAdmin();
        if (targetId === "tab-bd") staffCtrl.cargarVisorBDResumen();
    }

    menuTabs?.addEventListener("click", e => {
        const boton = e.target.closest("[data-tab-target]");
        if (!boton) return;
        activarTab(boton.getAttribute("data-tab-target"));
    });

    // --- Filtrado de pestañas por rol ([data-roles]) y modo demo ([data-demo-only]) ---
    function renderizarCabeceraYMenuPorRol(u) {
        const nombre = u.nombre || "Usuario Patitas Felices";
        const email = u.email || "";
        const rol = (u.rol || "cliente").toLowerCase();
        const telefono = u.telefono || "Sin teléfono registrado";

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

        const tabBotones = menuTabs?.querySelectorAll("[data-role-filter]") || [];
        tabBotones.forEach(btn => {
            const rolFiltro = btn.getAttribute("data-role-filter");
            const soloDemo = btn.getAttribute("data-demo-only") === "1";
            if (soloDemo && !modoDemo) {
                btn.classList.add("d-none");
                return;
            }
            if (rolFiltro === rol || (rol === "admin" && (rolFiltro === "doctor" || rolFiltro === "cliente"))) {
                btn.classList.remove("d-none");
            } else {
                btn.classList.add("d-none");
            }
        });
    }

    async function cargarMiPerfil() {
        try {
            const data = await peticionApi("/api/auth/sesion");
            const u = data.usuario || {};
            usuarioActual = u;

            const sesionActual = obtenerSesion();
            if (sesionActual) {
                guardarSesion({
                    ...sesionActual,
                    usuario: u,
                    rbac: data.rbac || sesionActual.rbac,
                });
            }

            renderizarCabeceraYMenuPorRol(u);

            if (campoNombre) campoNombre.textContent = u.nombre || "-";
            if (campoEmail) campoEmail.textContent = u.email || "-";
            if (campoTelefono) campoTelefono.textContent = u.telefono || "Sin registrar";
            const r = (u.rol || "cliente").toLowerCase();
            if (campoRol) {
                campoRol.textContent = r === "admin" ? "Administrador" : r === "doctor" ? "Médico Veterinario" : "Cliente / Propietario";
            }

            const wrapDocCmvp = document.getElementById("wrap-perfil-doctor-cmvp");
            const wrapDocEsp = document.getElementById("wrap-perfil-doctor-especialidad");
            const campoCmvp = document.getElementById("perfil-campo-cmvp");
            const campoEsp = document.getElementById("perfil-campo-especialidad");
            if (r === "doctor") {
                wrapDocCmvp?.classList.remove("d-none");
                wrapDocEsp?.classList.remove("d-none");
                if (campoCmvp) campoCmvp.textContent = u.cmvp || "Sin CMVP";
                if (campoEsp) campoEsp.textContent = u.especialidad || "Medicina General";
            } else {
                wrapDocCmvp?.classList.add("d-none");
                wrapDocEsp?.classList.add("d-none");
            }

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
                    const badgeDoc = document.createElement("span");
                    badgeDoc.className = "badge bg-light text-dark border me-2";
                    badgeDoc.textContent = `${tipoVal}: ${docVal}`;
                    const notaDoc = document.createElement("span");
                    notaDoc.className = "small text-muted fw-normal";
                    notaDoc.textContent = "Identificador oficial verificado (no modificable).";
                    p.append(badgeDoc, " ", notaDoc);
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
                        document.getElementById("perfil-input-num-doc")?.focus();
                    });

                    wrapSinDoc.append(p, btnAbrir);
                    contenedorDoc.append(wrapSinDoc);
                }
            }
            return true;
        } catch (err) {
            if (err?.status === 401 || err?.status === 403) {
                cerrarSesion();
                if (bannerNombre) bannerNombre.textContent = "Sesión expirada o inválida";
                if (bannerDetalle) bannerDetalle.textContent = err.message || "Inicia sesión nuevamente.";
                mostrarAlertaGlobal(err.message || "Tu sesión ya no es válida. Inicia sesión nuevamente.", "danger");
                setTimeout(() => {
                    window.location.href = "/?abrir_login=1";
                }, 1200);
                return false;
            }
            mostrarAlertaGlobal(err?.message || "No se pudo verificar la sesión con SQL Server.", "danger");
            return false;
        }
    }

    // --- Verificación de sesión en /api/auth/sesion e inicialización de subcontroladores ---
    async function inicializarSesion() {
        const sesion = obtenerSesion();
        if (!sesion?.token) {
            menuTabs?.querySelectorAll("[data-role-filter]")?.forEach(btn => btn.classList.add("d-none"));
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

        const sesionValida = await cargarMiPerfil();
        if (!sesionValida) return;

        const rol = (usuarioActual?.rol || "cliente").toLowerCase();
        const hashLimpio = (window.location.hash || "").replace(/^#/, "").replace(/^panel-/, "").replace(/^tab-/, "");
        let tabPersonalActivado = false;
        if (hashLimpio) {
            const tabObjetivo = `tab-${hashLimpio}`;
            const existeTab = menuTabs?.querySelector(`[data-tab-target="${tabObjetivo}"]:not(.d-none)`);
            if (existeTab) {
                activarTab(tabObjetivo);
                if (tabObjetivo === "tab-personal") tabPersonalActivado = true;
            }
        }

        if (rol === "admin") {
            staffCtrl.actualizarContadorSolicitudesPendientes();
            if (!tabPersonalActivado) {
                staffCtrl.cargarPersonalAdmin();
            }
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", inicializarSesion);
    } else {
        inicializarSesion();
    }
})();
