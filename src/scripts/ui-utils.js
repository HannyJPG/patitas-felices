
/**
 * ui-utils.js
 * Utilidades puras de presentación (sanitización HTML, alertas Bootstrap, formato de fechas y modo demo).
 * Consumido por admin-app.js, perfil.js, cliente-panel.js y admin-doctor-panel.js.
 */

export function escapeHtml(valor) {
    return String(valor ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

export function mostrarAlerta(contenedor, mensaje, tipo = "info", autoOcultarMs = 6000) {
    if (!contenedor) return;
    contenedor.className = `alert alert-${tipo} py-2 px-3 small`;
    contenedor.textContent = mensaje;
    contenedor.classList.remove("d-none");
    if (autoOcultarMs > 0) {
        setTimeout(() => {
            contenedor.classList.add("d-none");
        }, autoOcultarMs);
    }
}

export function extraerFechaIso(fechaTexto) {
    return String(fechaTexto || "").slice(0, 10);
}

export function formatearFechaLatam(fechaIso) {
    const limpia = extraerFechaIso(fechaIso);
    const partes = limpia.split("-");
    return partes.length === 3 ? `${partes[2]}/${partes[1]}/${partes[0]}` : limpia;
}

export function formatearIsoLocal(fechaObj) {
    const yyyy = fechaObj.getFullYear();
    const mm = String(fechaObj.getMonth() + 1).padStart(2, "0");
    const dd = String(fechaObj.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
}

export function esModoDemoActivo() {
    if (typeof window === "undefined") return false;
    const params = new URLSearchParams(window.location.search);
    return params.get("demo") === "1";
}
