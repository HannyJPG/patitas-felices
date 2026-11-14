/**
 * whatsapp.js
 * Generador de enlaces wa.me y plantillas de mensaje para solicitudes de cita desde el navegador.
 * Lee el teléfono oficial desde data/clinica.js y los nombres de servicio desde data/servicios.js.
 */

import { clinica } from "../data/clinica.js";
import { SERVICIOS } from "../data/servicios.js";

export function enlaceWhatsApp(mensaje = "Hola, Patitas Felices. Quisiera consultar por la atención de mi mascota.") {
    return "https://wa.me/" + clinica.whatsapp + "?text=" + encodeURIComponent(mensaje);
}

export function mensajeSolicitudCita(valores) {
    const [anio, mes, dia] = valores.fecha.split("-");
    return [
        "Hola, Patitas Felices. Quisiera solicitar una cita veterinaria.",
        "",
        "Propietario: " + valores.propietario,
        "Teléfono de contacto: " + valores.telefono,
        "Mascota: " + valores.mascota,
        "Servicio: " + SERVICIOS[valores.servicio],
        "Fecha deseada: " + dia + "/" + mes + "/" + anio,
        "Hora deseada: " + valores.hora + " (Lima, Perú)",
        "Duración: " + clinica.duracionCitaMinutos + " minutos",
        "Motivo: " + valores.motivo,
        "",
        "¿Podrían confirmar si este horario está disponible?"
    ].join("\n");
}
