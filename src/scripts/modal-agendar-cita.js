/* modal-agendar-cita.js - Controlador global del Modal de Agendamiento de Citas */

import { API_BASE_URL, obtenerSesion, peticionApi } from "./api-client.js";

const CLINICA_WHATSAPP_NUMERO = "51990853697";

const SERVICIOS_ETIQUETAS = {
  "consulta-general": "Consulta general",
  "vacunacion": "Vacunación preventiva",
  "desparasitacion": "Desparasitación interna / externa",
  "control": "Control de salud y seguimiento"
};

const HORARIOS_DEFINIDOS = [
  { valor: "08:30", label: "08:30 AM" },
  { valor: "10:00", label: "10:00 AM" },
  { valor: "11:30", label: "11:30 AM" },
  { valor: "13:00", label: "01:00 PM" },
  { valor: "15:30", label: "03:30 PM" },
  { valor: "17:00", label: "05:00 PM" },
  { valor: "18:30", label: "06:30 PM" }
];

function obtenerFechasPermitidas() {
  const hoy = new Date();
  const yyyy = hoy.getFullYear();
  const mm = String(hoy.getMonth() + 1).padStart(2, "0");
  const dd = String(hoy.getDate()).padStart(2, "0");
  const hoyStr = `${yyyy}-${mm}-${dd}`;

  const max = new Date(hoy.getTime() + 7 * 24 * 60 * 60 * 1000);
  const maxY = max.getFullYear();
  const maxM = String(max.getMonth() + 1).padStart(2, "0");
  const maxD = String(max.getDate()).padStart(2, "0");
  const maxStr = `${maxY}-${maxM}-${maxD}`;

  return { hoy: hoyStr, maximo: maxStr };
}

let mascotasCargadas = [];
const disponibilidadCache = new Map();

function renderizarOpcionesMascotas(selectEl, lista) {
  if (!selectEl) return;
  selectEl.replaceChildren();
  if (!lista || lista.length === 0) {
    const optVacio = document.createElement("option");
    optVacio.value = "";
    optVacio.textContent = "No tienes mascotas registradas. Ve a tu perfil para agregar una.";
    selectEl.append(optVacio);
    return;
  }

  const valorPrevio = selectEl.value;
  const optDefault = document.createElement("option");
  optDefault.value = "";
  optDefault.textContent = "-- Selecciona una mascota --";
  selectEl.append(optDefault);

  for (const m of lista) {
    const opt = document.createElement("option");
    opt.value = String(m.id ?? "");
    opt.dataset.nombre = String(m.nombre ?? "");
    opt.textContent = `${m.nombre || "Mascota"} (${m.especie || "Mascota"} - ${m.raza || "Mestizo"})`;
    selectEl.append(opt);
  }

  if (lista.length === 1) {
    selectEl.value = String(lista[0].id);
  } else if (valorPrevio && lista.some(m => String(m.id) === String(valorPrevio))) {
    selectEl.value = valorPrevio;
  }
}

export async function abrirModalAgendarCita(servicioId = null) {
  if (typeof servicioId !== "string" || servicioId.startsWith("[object")) {
    servicioId = null;
  }
  const sesion = obtenerSesion();

  // Si no ha iniciado sesión, abrir de inmediato el modal de login
  if (!sesion || !sesion.token) {
    sessionStorage.setItem("patitas_abrir_modal_cita", "true");
    if (servicioId) {
      sessionStorage.setItem("patitas_servicio_pendiente", servicioId);
    }
    const modalLoginEl = document.getElementById("modalLogin");
    if (modalLoginEl && window.bootstrap?.Modal) {
      const modalLoginInstance = window.bootstrap.Modal.getOrCreateInstance(modalLoginEl);
      modalLoginInstance.show();
    }
    return;
  }

  // Si ya tiene sesión activa:
  const modalCitaEl = document.getElementById("modalAgendarCita");
  if (!modalCitaEl || !window.bootstrap?.Modal) return;

  // Limpiar caché de mascotas previas para que siempre refleje la cuenta actual en SQL Server
  mascotasCargadas = [];

  const inputPropietario = document.getElementById("modal-cita-propietario");
  const inputDocumento = document.getElementById("modal-cita-documento");
  const inputTelefono = document.getElementById("modal-cita-telefono");
  const selectMascota = document.getElementById("modal-cita-mascota");
  const selectServicio = document.getElementById("modal-cita-servicio");
  const inputFecha = document.getElementById("modal-cita-fecha");
  const alertError = document.getElementById("modal-cita-alerta-error");
  const alertSuccess = document.getElementById("modal-cita-alerta-success");
  const btnSubmit = document.getElementById("btn-confirmar-cita");

  if (alertError) alertError.classList.add("d-none");
  if (alertSuccess) alertSuccess.classList.add("d-none");
  if (btnSubmit) btnSubmit.disabled = false;

  // Llenar campos no modificables del usuario de inmediato
  const usuario = sesion.usuario || {};
  if (inputPropietario) {
    inputPropietario.value = usuario.nombre || "Cliente Patitas Felices";
  }
  if (inputDocumento) {
    const docTipo = usuario.tipo_documento || "DNI";
    const docNum = usuario.documento || "";
    inputDocumento.value = docNum ? `${docTipo}: ${docNum}` : "Pendiente de registro en perfil";
  }
  if (inputTelefono && !inputTelefono.value) {
    inputTelefono.value = usuario.telefono || "";
  }

  // Preseleccionar servicio si fue enviado
  if (selectServicio && servicioId) {
    selectServicio.value = servicioId;
  }

  // Configurar restricciones de fecha (hoy hasta hoy + 7 días)
  const { hoy, maximo } = obtenerFechasPermitidas();
  if (inputFecha) {
    inputFecha.min = hoy;
    inputFecha.max = maximo;
    if (!inputFecha.value || inputFecha.value < hoy || inputFecha.value > maximo) {
      inputFecha.value = hoy;
    }
  }

  // Mostrar el modal DE INMEDIATO (0ms de retardo visual)
  const modalCitaInstance = window.bootstrap.Modal.getOrCreateInstance(modalCitaEl);
  modalCitaInstance.show();

  // Cargar mascotas y disponibilidad en paralelo sin bloquear la apertura del modal
  await Promise.all([
    cargarMascotasCliente(selectMascota),
    inputFecha?.value ? actualizarDisponibilidadHorarios(inputFecha.value) : Promise.resolve()
  ]);
}

async function cargarMascotasCliente(selectEl) {
  if (!selectEl) return;

  // Si ya hay mascotas en caché, mostrarlas al instante mientras se sincroniza en segundo plano
  if (mascotasCargadas.length > 0) {
    renderizarOpcionesMascotas(selectEl, mascotasCargadas);
  } else {
    selectEl.innerHTML = '<option value="">Cargando mascotas...</option>';
  }

  try {
    const res = await peticionApi("/api/cliente/mis-mascotas");
    mascotasCargadas = res.mascotas || [];
    renderizarOpcionesMascotas(selectEl, mascotasCargadas);
  } catch (err) {
    console.error("Error al cargar mascotas:", err);
    if (mascotasCargadas.length === 0) {
      selectEl.innerHTML = '<option value="">Error cargando mascotas. Intenta de nuevo.</option>';
    }
  }
}

function renderizarHorariosEnSelect(selectHora, ayudaCupos, fecha, horarios) {
  if (!selectHora) return;
  const horaActualSeleccionada = selectHora.value;
  let html = "";
  let primeraOpcionDisponible = "";

  HORARIOS_DEFINIDOS.forEach(h => {
    const info = horarios[h.valor] || { ocupados: 0, disponible: true, capacidad_maxima: 3 };
    const ocupados = info.ocupados || 0;
    const capacidad = info.capacidad_maxima || 3;
    const disponibles = Math.max(0, capacidad - ocupados);
    const estaLleno = !info.disponible || ocupados >= capacidad;

    if (estaLleno) {
      html += `<option value="${h.valor}" disabled>${h.label} (Completo - 3 doctores ocupados)</option>`;
    } else {
      if (!primeraOpcionDisponible) primeraOpcionDisponible = h.valor;
      const textoCupos = disponibles === 1 ? "1 cupo disponible" : `${disponibles} cupos disponibles`;
      html += `<option value="${h.valor}">${h.label} (${textoCupos})</option>`;
    }
  });

  selectHora.innerHTML = html;

  const opcionExistente = selectHora.querySelector(`option[value="${horaActualSeleccionada}"]:not([disabled])`);
  if (opcionExistente) {
    selectHora.value = horaActualSeleccionada;
  } else if (primeraOpcionDisponible) {
    selectHora.value = primeraOpcionDisponible;
  }

  if (ayudaCupos) {
    ayudaCupos.textContent = `Capacidad: 3 doctores por turno. Horarios actualizados para el día ${fecha}.`;
  }
}

async function actualizarDisponibilidadHorarios(fecha) {
  const selectHora = document.getElementById("modal-cita-hora");
  const ayudaCupos = document.getElementById("ayuda-cupos");
  if (!selectHora) return;

  // Si existe en caché para esta fecha, mostrar de inmediato sin deshabilitar el control
  if (disponibilidadCache.has(fecha)) {
    renderizarHorariosEnSelect(selectHora, ayudaCupos, fecha, disponibilidadCache.get(fecha));
  } else {
    selectHora.disabled = true;
  }

  try {
    const res = await fetch(`${API_BASE_URL}/api/citas/disponibilidad?fecha=${encodeURIComponent(fecha)}`);
    const data = await res.json();
    const horarios = data.horarios || {};
    disponibilidadCache.set(fecha, horarios);
    renderizarHorariosEnSelect(selectHora, ayudaCupos, fecha, horarios);
  } catch (err) {
    console.warn("No se pudo cargar disponibilidad de horarios en vivo:", err);
    if (!disponibilidadCache.has(fecha)) {
      selectHora.innerHTML = HORARIOS_DEFINIDOS.map(h => `<option value="${h.valor}">${h.label}</option>`).join("");
    }
  } finally {
    selectHora.disabled = false;
  }
}

function inicializarEventosModalCita() {
  // 1. Interceptar clics en botones con data-abrir-modal-cita o enlaces a /agendar-cita
  document.addEventListener("click", e => {
    const btn = e.target.closest("[data-abrir-modal-cita], a[href^='/agendar-cita'], a[href='/agendar-cita']");
    if (!btn) return;

    e.preventDefault();
    let servicio = btn.getAttribute("data-servicio");
    if (!servicio && btn.getAttribute("href")) {
      try {
        const urlObj = new URL(btn.getAttribute("href"), window.location.origin);
        servicio = urlObj.searchParams.get("servicio");
      } catch {
        /* Ignorar error de parsing */
      }
    }
    abrirModalAgendarCita(servicio);
  });

  // 2. Cambio en la fecha -> recargar disponibilidad de horarios
  const inputFecha = document.getElementById("modal-cita-fecha");
  if (inputFecha) {
    inputFecha.addEventListener("change", () => {
      const { hoy, maximo } = obtenerFechasPermitidas();
      if (inputFecha.value < hoy) {
        inputFecha.value = hoy;
      } else if (inputFecha.value > maximo) {
        inputFecha.value = maximo;
      }
      actualizarDisponibilidadHorarios(inputFecha.value);
    });
  }

  // 3. Envío del formulario de agendar cita
  const formCita = document.getElementById("form-modal-cita");
  if (formCita) {
    formCita.addEventListener("submit", async e => {
      e.preventDefault();
      const alertError = document.getElementById("modal-cita-alerta-error");
      const alertSuccess = document.getElementById("modal-cita-alerta-success");
      const btnSubmit = document.getElementById("btn-confirmar-cita");

      if (alertError) alertError.classList.add("d-none");
      if (alertSuccess) alertSuccess.classList.add("d-none");

      const selectMascota = document.getElementById("modal-cita-mascota");
      const mascotaId = selectMascota?.value;
      if (!mascotaId) {
        if (alertError) {
          alertError.textContent = "Debes seleccionar una mascota para agendar la cita. Si aún no tienes mascotas registradas, ingresa a tu perfil.";
          alertError.classList.remove("d-none");
        }
        return;
      }

      const mascotaSeleccionada = mascotasCargadas.find(m => String(m.id) === String(mascotaId));
      const mascotaNombre = mascotaSeleccionada ? mascotaSeleccionada.nombre : "Mascota";

      const propietario = document.getElementById("modal-cita-propietario")?.value.trim();
      const telefono = document.getElementById("modal-cita-telefono")?.value.trim();
      const servicio = document.getElementById("modal-cita-servicio")?.value;
      const fecha = document.getElementById("modal-cita-fecha")?.value;
      const hora = document.getElementById("modal-cita-hora")?.value;
      const motivo = document.getElementById("modal-cita-motivo")?.value.trim();

      const telLimpio = telefono.replace(/\D/g, "");
      if (!telefono || telLimpio.length < 9) {
        if (alertError) {
          alertError.textContent = "Por favor ingresa un número de teléfono de contacto válido de al menos 9 dígitos.";
          alertError.classList.remove("d-none");
        }
        return;
      }

      if (!motivo || motivo.length < 10) {
        if (alertError) {
          alertError.textContent = "El motivo de la consulta debe tener al menos 10 caracteres explicativos.";
          alertError.classList.remove("d-none");
        }
        return;
      }

      if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.textContent = "Agendando cita...";
      }

      try {
        const respuesta = await peticionApi("/api/citas", {
          method: "POST",
          body: JSON.stringify({
            propietario,
            telefono,
            mascota_nombre: mascotaNombre,
            mascota_id: parseInt(mascotaId, 10),
            servicio,
            fecha,
            hora,
            motivo
          })
        });

        if (fecha) {
          disponibilidadCache.delete(fecha);
        }

        if (alertSuccess) {
          alertSuccess.textContent = `¡Cita agendada con éxito para ${mascotaNombre} el ${fecha} a las ${hora}! Un doctor confirmará tu atención.`;
          alertSuccess.classList.remove("d-none");
        }

        // Disparar evento global para que el perfil actualice la lista de citas si está abierto
        window.dispatchEvent(new CustomEvent("patitas:cita-creada", { detail: respuesta.cita }));

        setTimeout(() => {
          const modalCitaEl = document.getElementById("modalAgendarCita");
          if (modalCitaEl && window.bootstrap?.Modal) {
            window.bootstrap.Modal.getInstance(modalCitaEl)?.hide();
          }
          formCita.reset();
        }, 1800);

      } catch (err) {
        if (alertError) {
          let msg = (err && typeof err.message === "string" && err.message !== "[object Object]")
            ? err.message
            : "No se pudo agendar la cita. Verifica que los datos sean correctos y el turno siga disponible.";
          alertError.textContent = msg;
          alertError.classList.remove("d-none");
        }
        // Actualizar disponibilidad por si el cupo fue ganado
        if (fecha) {
          disponibilidadCache.delete(fecha);
          actualizarDisponibilidadHorarios(fecha);
        }
      } finally {
        if (btnSubmit) {
          btnSubmit.disabled = false;
          btnSubmit.textContent = "Confirmar y Agendar Cita";
        }
      }
    });
  }

  // 4. Botón de Consultar por WhatsApp
  const btnWhatsapp = document.getElementById("btn-cita-whatsapp");
  if (btnWhatsapp) {
    btnWhatsapp.addEventListener("click", () => {
      const propietario = document.getElementById("modal-cita-propietario")?.value || "";
      const documento = document.getElementById("modal-cita-documento")?.value || "";
      const selectMascota = document.getElementById("modal-cita-mascota");
      const mascotaId = selectMascota?.value;
      const mascotaSeleccionada = mascotasCargadas.find(m => String(m.id) === String(mascotaId));
      const mascotaNombre = mascotaSeleccionada ? mascotaSeleccionada.nombre : "Mi mascota";

      const servicioCod = document.getElementById("modal-cita-servicio")?.value || "consulta-general";
      const servicioNombre = SERVICIOS_ETIQUETAS[servicioCod] || servicioCod;
      const fecha = document.getElementById("modal-cita-fecha")?.value || "Por coordinar";
      const hora = document.getElementById("modal-cita-hora")?.value || "Por coordinar";
      const motivo = document.getElementById("modal-cita-motivo")?.value.trim() || "Consulta informativa";

      const mensaje = `Hola Clínica Veterinaria Patitas Felices, deseo consultar sobre una cita médica:
- Propietario: ${propietario}
- Documento: ${documento}
- Mascota: ${mascotaNombre}
- Servicio: ${servicioNombre}
- Fecha tentativa: ${fecha} (${hora})
- Motivo: ${motivo}`;

      const urlWa = `https://wa.me/${CLINICA_WHATSAPP_NUMERO}?text=${encodeURIComponent(mensaje)}`;
      window.open(urlWa, "_blank");
    });
  }

  // 5. Soporte para abrir el modal si el usuario venía de un login pendiente y precarga en segundo plano
  const sesion = obtenerSesion();
  if (sesion?.token) {
    if (sessionStorage.getItem("patitas_abrir_modal_cita") === "true") {
      const servicioPendiente = sessionStorage.getItem("patitas_servicio_pendiente");
      sessionStorage.removeItem("patitas_abrir_modal_cita");
      sessionStorage.removeItem("patitas_servicio_pendiente");
      setTimeout(() => {
        abrirModalAgendarCita(servicioPendiente);
      }, 150);
    } else {
      // Precargar mascotas y disponibilidad del día actual en segundo plano para apertura instantánea
      const { hoy } = obtenerFechasPermitidas();
      peticionApi("/api/cliente/mis-mascotas")
        .then(res => { mascotasCargadas = res.mascotas || []; })
        .catch(() => {});
      fetch(`${API_BASE_URL}/api/citas/disponibilidad?fecha=${encodeURIComponent(hoy)}`)
        .then(r => r.json())
        .then(d => { if (d?.horarios) disponibilidadCache.set(hoy, d.horarios); })
        .catch(() => {});
    }
  }
}

// Inicializar al cargar el DOM
if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", inicializarEventosModalCita);
  } else {
    inicializarEventosModalCita();
  }
}

// Exponer en window para llamadas manuales si es necesario
if (typeof window !== "undefined") {
  window.abrirModalAgendarCita = abrirModalAgendarCita;
}
