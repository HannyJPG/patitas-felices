/**
 * header-auth.js
 * Controlador global de autenticación conectado a Header.astro y ModalLogin.astro.
 * Sincroniza la barra de usuario (#btn-header-login, #dropdown-header-perfil) con /api/auth/sesion,
 * gestiona los formularios de login (/api/auth/login) y registro (/api/auth/register), y dispara
 * el evento personalizado "patitas:sesion-actualizada" para que otras vistas reaccionen al instante.
 */

import { peticionApi, guardarSesion, obtenerSesion, cerrarSesion, RUTA_ESPACIO_POR_ROL } from "./api-client.js";

const STORAGE_REMEMBER_EMAIL = "patitas_remember_email";

/**
 * Obtiene la ruta del panel según el rol del usuario autenticado
 */
function obtenerRutaEspacio(datos) {
    return "/perfil";
}

/**
 * Obtiene el nombre amigable del rol para la interfaz
 */
function obtenerEtiquetaRol(datos) {
    if (datos?.rbac?.etiqueta) return datos.rbac.etiqueta;
    const rol = datos?.usuario?.rol || datos?.rbac?.rol;
    if (rol === "admin") return "Administrador";
    if (rol === "doctor") return "Médico Veterinario";
    return "Propietario de Mascota";
}

document.addEventListener("DOMContentLoaded", () => {
    const btnHeaderLogin = document.getElementById("btn-header-login");
    const contenedorPerfil = document.getElementById("dropdown-header-perfil");
    const avatarInicial = document.getElementById("header-avatar-inicial");
    const textoPerfil = document.getElementById("header-texto-perfil");
    const menuNombre = document.getElementById("header-menu-nombre");
    const menuRol = document.getElementById("header-menu-rol");
    const enlaceMiEspacio = document.getElementById("header-enlace-espacio");
    const btnCerrarSesion = document.getElementById("header-btn-cerrar-sesion");

    const modalEl = document.getElementById("modalLogin");
    const tabLogin = document.getElementById("tab-modal-login");
    const tabRegistro = document.getElementById("tab-modal-registro");
    const vistaLogin = document.getElementById("vista-login");
    const vistaRegistro = document.getElementById("vista-registro");

    const formLogin = document.getElementById("form-modal-login");
    const inputEmail = document.getElementById("modal-input-email");
    const inputPassword = document.getElementById("modal-input-password");
    const checkRecordar = document.getElementById("modal-check-recordar");
    const btnRecordarContrasena = document.getElementById("btn-recordar-contrasena");
    const panelRecordarAyuda = document.getElementById("panel-recordar-ayuda");
    const btnTogglePass = document.getElementById("btn-modal-toggle-pass");
    const alertError = document.getElementById("modal-login-error");
    const alertSuccess = document.getElementById("modal-login-success");
    const btnSubmit = document.getElementById("btn-modal-submit");
    const spinnerSubmit = document.getElementById("spinner-modal-login");
    const textoSubmit = document.getElementById("texto-modal-submit");

    const formRegistro = document.getElementById("form-modal-registro");
    const inputRegNombre = document.getElementById("registro-input-nombre");
    const inputRegTelefono = document.getElementById("registro-input-telefono");
    const inputRegEmail = document.getElementById("registro-input-email");
    const inputRegPass = document.getElementById("registro-input-password");
    const alertRegError = document.getElementById("modal-registro-error");
    const alertRegSuccess = document.getElementById("modal-registro-success");
    const btnRegSubmit = document.getElementById("btn-registro-submit");
    const spinnerReg = document.getElementById("spinner-modal-registro");
    const textoReg = document.getElementById("texto-registro-submit");

    function activarTab(tab) {
        if (tab === "registro") {
            tabRegistro?.classList.add("active");
            tabRegistro?.setAttribute("aria-selected", "true");
            tabLogin?.classList.remove("active");
            tabLogin?.setAttribute("aria-selected", "false");
            vistaRegistro?.classList.remove("d-none");
            vistaLogin?.classList.add("d-none");
            if (alertRegError) alertRegError.classList.add("d-none");
            if (alertRegSuccess) alertRegSuccess.classList.add("d-none");
            inputRegNombre?.focus();
        } else {
            tabLogin?.classList.add("active");
            tabLogin?.setAttribute("aria-selected", "true");
            tabRegistro?.classList.remove("active");
            tabRegistro?.setAttribute("aria-selected", "false");
            vistaLogin?.classList.remove("d-none");
            vistaRegistro?.classList.add("d-none");
            if (alertError) alertError.classList.add("d-none");
            if (alertSuccess) alertSuccess.classList.add("d-none");
            inputEmail?.focus();
        }
    }

    tabLogin?.addEventListener("click", () => activarTab("login"));
    tabRegistro?.addEventListener("click", () => activarTab("registro"));

    /**
     * Muestra u oculta el modal de forma compatible (Bootstrap o Fallback CSS)
     */
    function abrirModal() {
        if (!modalEl) return;
        
        const emailRecordado = localStorage.getItem(STORAGE_REMEMBER_EMAIL);
        if (emailRecordado && inputEmail) {
            inputEmail.value = emailRecordado;
            if (checkRecordar) checkRecordar.checked = true;
        }

        if (alertError) alertError.classList.add("d-none");
        if (alertSuccess) alertSuccess.classList.add("d-none");

        if (window.bootstrap && window.bootstrap.Modal) {
            const instancia = window.bootstrap.Modal.getOrCreateInstance(modalEl);
            instancia.show();
        } else {
            modalEl.classList.add("show");
            modalEl.style.display = "block";
            document.body.classList.add("modal-open");
        }
    }

    function cerrarModal() {
        if (!modalEl) return;
        if (window.bootstrap && window.bootstrap.Modal) {
            const instancia = window.bootstrap.Modal.getInstance(modalEl);
            if (instancia) instancia.hide();
        } else {
            modalEl.classList.remove("show");
            modalEl.style.display = "none";
            document.body.classList.remove("modal-open");
        }
    }

    /**
     * Actualiza el estado visual del Header dinámicamente según la sesión
     */
    // --- Sincronización visual de Header.astro según sesión activa ---
    function actualizarEstadoHeader() {
        const sesion = obtenerSesion();

        if (sesion && sesion.usuario) {
            if (btnHeaderLogin) btnHeaderLogin.classList.add("d-none");
            if (contenedorPerfil) contenedorPerfil.classList.remove("d-none");

            const nombre = sesion.usuario.nombre || "Usuario";
            const inicial = nombre.trim().charAt(0).toUpperCase() || "U";
            const rutaEspacio = obtenerRutaEspacio(sesion);
            const etiquetaRol = obtenerEtiquetaRol(sesion);

            if (avatarInicial) avatarInicial.textContent = inicial;
            if (textoPerfil) textoPerfil.textContent = "Ver perfil";
            if (menuNombre) menuNombre.textContent = nombre;
            if (menuRol) menuRol.textContent = etiquetaRol;
            if (enlaceMiEspacio) enlaceMiEspacio.setAttribute("href", rutaEspacio);
        } else {
            if (btnHeaderLogin) btnHeaderLogin.classList.remove("d-none");
            if (contenedorPerfil) contenedorPerfil.classList.add("d-none");
        }
    }

    actualizarEstadoHeader();
    const sesionInicial = obtenerSesion();
    if (sesionInicial?.token) {
        peticionApi("/api/auth/sesion")
            .then(data => {
                if (data?.usuario) {
                    guardarSesion({
                        ...sesionInicial,
                        usuario: data.usuario,
                        rbac: data.rbac || sesionInicial.rbac,
                    });
                    actualizarEstadoHeader();
                }
            })
            .catch(err => {
                if (err?.status === 401 || err?.status === 403) {
                    cerrarSesion();
                    actualizarEstadoHeader();
                }
            });
    }

    document.querySelectorAll("[data-abrir-login]").forEach(elem => {
        elem.addEventListener("click", evento => {
            evento.preventDefault();
            abrirModal();
        });
    });

    if (btnHeaderLogin) {
        btnHeaderLogin.addEventListener("click", evento => {
            evento.preventDefault();
            abrirModal();
        });
    }

    if (btnCerrarSesion) {
        btnCerrarSesion.addEventListener("click", () => {
            cerrarSesion();
            actualizarEstadoHeader();
            const path = window.location.pathname;
            if (path.includes("/perfil") || path.includes("/cliente") || path.includes("/doctor") || path.includes("/admin")) {
                window.location.assign("/");
            }
        });
    }

    if (btnTogglePass && inputPassword) {
        btnTogglePass.addEventListener("click", () => {
            const esPassword = inputPassword.getAttribute("type") === "password";
            inputPassword.setAttribute("type", esPassword ? "text" : "password");
            btnTogglePass.setAttribute("aria-label", esPassword ? "Ocultar contraseña" : "Mostrar contraseña");
        });
    }

    if (btnRecordarContrasena && panelRecordarAyuda) {
        btnRecordarContrasena.addEventListener("click", () => {
            panelRecordarAyuda.classList.toggle("d-none");
        });
    }

    if (formLogin) {
        // --- Envío de credenciales contra POST /api/auth/login ---
        formLogin.addEventListener("submit", async evento => {
            evento.preventDefault();
            if (alertError) alertError.classList.add("d-none");
            if (alertSuccess) alertSuccess.classList.add("d-none");

            const email = (inputEmail?.value || "").trim();
            const password = inputPassword?.value || "";

            if (!email || !password) {
                if (alertError) {
                    alertError.textContent = "Por favor, ingresa tu correo y contraseña.";
                    alertError.classList.remove("d-none");
                }
                return;
            }

            if (btnSubmit) btnSubmit.disabled = true;
            if (spinnerSubmit) spinnerSubmit.classList.remove("d-none");
            if (textoSubmit) textoSubmit.textContent = "Comprobando credenciales...";

            try {
                const respuesta = await peticionApi("/api/auth/login", {
                    method: "POST",
                    body: JSON.stringify({ email, password })
                });

                guardarSesion(respuesta);

                if (checkRecordar && checkRecordar.checked) {
                    localStorage.setItem(STORAGE_REMEMBER_EMAIL, email);
                } else {
                    localStorage.removeItem(STORAGE_REMEMBER_EMAIL);
                }

                if (alertSuccess) {
                    alertSuccess.textContent = `¡Bienvenido(a), ${respuesta.usuario.nombre}! Redirigiendo a tu espacio...`;
                    alertSuccess.classList.remove("d-none");
                }

                actualizarEstadoHeader();

                if (sessionStorage.getItem("patitas_abrir_modal_cita") === "true") {
                    const rawServicio = sessionStorage.getItem("patitas_servicio_pendiente");
                    const servicioPendiente = (typeof rawServicio === "string" && !rawServicio.startsWith("[object") && rawServicio !== "null" && rawServicio !== "undefined") ? rawServicio : null;
                    sessionStorage.removeItem("patitas_abrir_modal_cita");
                    sessionStorage.removeItem("patitas_servicio_pendiente");
                    setTimeout(() => {
                        cerrarModal();
                        if (typeof window.abrirModalAgendarCita === "function") {
                            window.abrirModalAgendarCita(servicioPendiente);
                        } else {
                            window.location.reload();
                        }
                    }, 500);
                    return;
                }

                const rutaDestino = obtenerRutaEspacio(respuesta);
                setTimeout(() => {
                    cerrarModal();
                    window.location.assign(rutaDestino);
                }, 600);

            } catch (err) {
                if (alertError) {
                    alertError.textContent = err.message || "No se pudo iniciar sesión. Verifica tus credenciales.";
                    alertError.classList.remove("d-none");
                }
            } finally {
                if (btnSubmit) btnSubmit.disabled = false;
                if (spinnerSubmit) spinnerSubmit.classList.add("d-none");
                if (textoSubmit) textoSubmit.textContent = "Ingresar a mi cuenta";
            }
        });
    }

    if (formRegistro) {
        // --- Registro de nuevo cliente contra POST /api/auth/register ---
        formRegistro.addEventListener("submit", async evento => {
            evento.preventDefault();
            if (alertRegError) alertRegError.classList.add("d-none");
            if (alertRegSuccess) alertRegSuccess.classList.add("d-none");

            const nombre = (inputRegNombre?.value || "").trim();
            const telefono = (inputRegTelefono?.value || "").trim();
            const email = (inputRegEmail?.value || "").trim();
            const password = inputRegPass?.value || "";

            if (!nombre || !email || !password) {
                if (alertRegError) {
                    alertRegError.textContent = "Por favor, completa nombre, correo y contraseña.";
                    alertRegError.classList.remove("d-none");
                }
                return;
            }

            if (nombre.length < 2) {
                if (alertRegError) {
                    alertRegError.textContent = "El nombre y apellido deben tener al menos 2 caracteres.";
                    alertRegError.classList.remove("d-none");
                }
                return;
            }

            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
                if (alertRegError) {
                    alertRegError.textContent = "Por favor, ingresa un correo electrónico con formato válido.";
                    alertRegError.classList.remove("d-none");
                }
                return;
            }

            if (password.length < 6) {
                if (alertRegError) {
                    alertRegError.textContent = "La contraseña debe tener al menos 6 caracteres.";
                    alertRegError.classList.remove("d-none");
                }
                return;
            }

            if (btnRegSubmit) btnRegSubmit.disabled = true;
            if (spinnerReg) spinnerReg.classList.remove("d-none");
            if (textoReg) textoReg.textContent = "Creando tu cuenta...";

            try {
                const respuesta = await peticionApi("/api/auth/register", {
                    method: "POST",
                    body: JSON.stringify({ nombre, telefono, email, password })
                });

                if (!respuesta?.token || !respuesta?.usuario?.id) {
                    throw new Error("No se pudo confirmar el registro de la cuenta en SQL Server.");
                }

                guardarSesion(respuesta);
                window.dispatchEvent(new CustomEvent("sesion_actualizada"));

                actualizarEstadoHeader();

                if (alertRegSuccess) {
                    alertRegSuccess.textContent = `¡Cuenta creada exitosamente! Bienvenido(a), ${respuesta.usuario.nombre}.`;
                    alertRegSuccess.classList.remove("d-none");
                }

                if (sessionStorage.getItem("patitas_abrir_modal_cita") === "true") {
                    const rawServicio = sessionStorage.getItem("patitas_servicio_pendiente");
                    const servicioPendiente = (typeof rawServicio === "string" && !rawServicio.startsWith("[object") && rawServicio !== "null" && rawServicio !== "undefined") ? rawServicio : null;
                    sessionStorage.removeItem("patitas_abrir_modal_cita");
                    sessionStorage.removeItem("patitas_servicio_pendiente");
                    setTimeout(() => {
                        cerrarModal();
                        formRegistro.reset();
                        activarTab("login");
                        if (typeof window.abrirModalAgendarCita === "function") {
                            window.abrirModalAgendarCita(servicioPendiente);
                        } else {
                            window.location.reload();
                        }
                    }, 900);
                    return;
                }

                setTimeout(() => {
                    cerrarModal();
                    formRegistro.reset();
                    activarTab("login");
                }, 1100);

            } catch (err) {
                if (alertRegError) {
                    alertRegError.textContent = err.message || "No se pudo registrar la cuenta. Intenta nuevamente.";
                    alertRegError.classList.remove("d-none");
                }
            } finally {
                if (btnRegSubmit) btnRegSubmit.disabled = false;
                if (spinnerReg) spinnerReg.classList.add("d-none");
                if (textoReg) textoReg.textContent = "Crear mi cuenta";
            }
        });
    }

    const params = new URLSearchParams(window.location.search);
    if (params.get("abrir_login") === "1" && !obtenerSesion()) {
        abrirModal();
    }
});
