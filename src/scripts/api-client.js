/* Cliente HTTP fetch() hacia el Backend Python FastAPI (Local y Hosting en la Nube) */

export const API_BASE_URL = (() => {
    if (typeof window === "undefined") return "http://127.0.0.1:8000";
    const host = window.location.hostname;
    const port = window.location.port;
    // Si estás en desarrollo local con Astro (puerto 4321), apunta a la API en 8000 con el mismo host (localhost o 127.0.0.1)
    if (port === "4321") {
        return `http://${host}:8000`;
    }
    // Si ya está compilado o alojado en hosting unificado
    if (window.location.origin.startsWith("http")) {
        return window.location.origin;
    }
    return "http://127.0.0.1:8000";
})();

const STORAGE_KEY_SESION = "patitas_sesion_rbac_v2";

export const RUTA_ESPACIO_POR_ROL = {
    cliente: "/perfil",
    doctor: "/perfil",
    admin: "/perfil"
};

export function guardarSesion(datosLogin) {
    try {
        localStorage.setItem(STORAGE_KEY_SESION, JSON.stringify(datosLogin));
    } catch {
        /* Entornos con almacenamiento restringido */
    }
}

export function obtenerSesion() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY_SESION);
        return raw ? JSON.parse(raw) : null;
    } catch {
        return null;
    }
}

export function cerrarSesion() {
    try {
        localStorage.removeItem(STORAGE_KEY_SESION);
    } catch {
        /* Ignorar */
    }
}

export async function peticionApi(ruta, opciones = {}) {
    const sesion = obtenerSesion();
    const cabeceras = {
        "Content-Type": "application/json",
        ...(opciones.headers || {})
    };
    if (sesion?.token && !cabeceras.Authorization) {
        cabeceras.Authorization = `Bearer ${sesion.token}`;
    }

    try {
        const respuesta = await fetch(`${API_BASE_URL}${ruta}`, {
            ...opciones,
            headers: cabeceras
        });

        const esJson = (respuesta.headers.get("content-type") || "").includes("application/json");
        const cuerpo = esJson ? await respuesta.json() : null;

        if (!respuesta.ok) {
            const mensaje = cuerpo?.detail || `Error HTTP ${respuesta.status}`;
            const error = new Error(mensaje);
            error.status = respuesta.status;
            throw error;
        }
        return cuerpo;
    } catch (err) {
        if (err.name === "TypeError" && err.message.includes("fetch")) {
            throw new Error(`No se pudo conectar con el Backend FastAPI en ${API_BASE_URL}. Asegúrate de tenerlo encendido (puerto 8000).`);
        }
        throw err;
    }
}

export function descargarPdfDesdeBase64(pdfBase64, nombreArchivo = "Boleta_Patitas_Felices.pdf") {
    const caracteres = atob(pdfBase64);
    const bytes = new Uint8Array(caracteres.length);
    for (let i = 0; i < caracteres.length; i += 1) {
        bytes[i] = caracteres.charCodeAt(i);
    }
    const blob = new Blob([bytes], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = nombreArchivo;
    document.body.append(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
}
