export const servicios = Object.freeze([
    {
        id: "consulta-general",
        titulo: "Consulta General",
        categoria: "Medicina Preventiva",
        duracion: "30 min",
        descripcion: "Evaluación integral de salud y bienestar para conocer a fondo el estado de tu mascota y resolver todas tus dudas.",
        caracteristicas: [
            "Examen físico completo de pies a cabeza",
            "Monitoreo de peso, temperatura y frecuencia cardíaca",
            "Orientación nutricional y cuidados diarios"
        ],
        icono: "M6 3v5a4 4 0 0 0 8 0V3M4 3h4m4 0h4m-6 9v3a5 5 0 0 0 10 0v-2m0-4a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z"
    },
    {
        id: "vacunacion",
        titulo: "Vacunación",
        categoria: "Inmunización Integral",
        duracion: "25 min",
        descripcion: "Aplicación segura de vacunas con carnet oficial para proteger a tu perro o gato frente a enfermedades infecciosas.",
        caracteristicas: [
            "Esquema anual y para cachorros/gatitos",
            "Revisión previa a la inoculación",
            "Registro y recordatorio digital de refuerzos"
        ],
        icono: "m15 3 6 6M18 6l-3 3m-8 2 6 6m-8 2 2 2 10-10-6-6L1 15l4 4Zm0 0-3 3"
    },
    {
        id: "desparasitacion",
        titulo: "Desparasitación",
        categoria: "Protección Antiparasitaria",
        duracion: "20 min",
        descripcion: "Protección interna y externa adaptada a la edad, peso y estilo de vida de tu compañero de cuatro patas.",
        caracteristicas: [
            "Fórmulas de alta eficacia contra pulgas y garrapatas",
            "Tratamiento para parásitos gastrointestinales",
            "Pautas preventivas para el hogar"
        ],
        icono: "M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7l-9-4Zm-4 9 3 3 5-6"
    },
    {
        id: "control",
        titulo: "Control y Seguimiento",
        categoria: "Atención Continua",
        duracion: "30 min",
        descripcion: "Monitoreo periódico para tratamientos en curso, cirugías previas o pacientes senior que requieren vigilancia especial.",
        caracteristicas: [
            "Seguimiento evolutivo de historias clínicas",
            "Ajuste de dosis o terapias farmacológicas",
            "Revisión de heridas y recuperación física"
        ],
        icono: "M20 8a5 5 0 0 0-8-4 5 5 0 0 0-8 4c0 5 8 12 8 12s8-7 8-12ZM4 12h5l2-3 2 6 2-3h5"
    }
]);

export const SERVICIOS = Object.freeze(Object.fromEntries(servicios.map(servicio => [servicio.id, servicio.titulo])));
