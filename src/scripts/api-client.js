
export const API_BASE_URL = (() => {
    if (typeof window === "undefined") return "http://127.0.0.1:8000";
    const host = window.location.hostname;
    const port = window.location.port;
    if (port === "4321") {
        return `http://${host}:8000`;
    }
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
            let mensaje = `Error HTTP ${respuesta.status}`;
            if (typeof cuerpo?.detail === "string") {
                mensaje = cuerpo.detail;
            } else if (Array.isArray(cuerpo?.detail)) {
                mensaje = cuerpo.detail
                    .map(d => (typeof d === "string" ? d : (d?.msg || d?.message || JSON.stringify(d))))
                    .join(", ");
            } else if (cuerpo?.detail && typeof cuerpo.detail === "object") {
                mensaje = cuerpo.detail.msg || cuerpo.detail.message || cuerpo.detail.error || JSON.stringify(cuerpo.detail);
            } else if (typeof cuerpo?.error === "string") {
                mensaje = cuerpo.error;
            } else if (typeof cuerpo?.message === "string") {
                mensaje = cuerpo.message;
            } else if (typeof cuerpo?.mensaje === "string") {
                mensaje = cuerpo.mensaje;
            }
            if (typeof mensaje !== "string" || mensaje === "[object Object]") {
                mensaje = `Error HTTP ${respuesta.status} en la operación.`;
            }
            const error = new Error(mensaje);
            error.status = respuesta.status;
            error.detalles = cuerpo?.detail;
            throw error;
        }
        return cuerpo;
    } catch (err) {
        if (err instanceof TypeError) {
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

export async function abrirPdfBoletaAutenticada(ventaId) {
    const sesion = obtenerSesion();
    if (!sesion?.token) {
        throw new Error("Debes iniciar sesión para abrir esta boleta PDF.");
    }
    const respuesta = await fetch(`${API_BASE_URL}/api/tienda/boleta/${encodeURIComponent(ventaId)}/pdf`, {
        headers: { Authorization: `Bearer ${sesion.token}` },
    });
    if (!respuesta.ok) {
        let mensaje = `No se pudo abrir la boleta (HTTP ${respuesta.status}).`;
        try {
            const errJson = await respuesta.json();
            if (typeof errJson?.detail === "string") mensaje = errJson.detail;
        } catch {
        }
        throw new Error(mensaje);
    }
    const blob = await respuesta.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
}
