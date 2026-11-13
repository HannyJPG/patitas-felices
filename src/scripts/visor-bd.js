import { obtenerSesion, peticionApi } from "./api-client.js";

let cacheTablas = {};
let tablaSeleccionada = "TODAS";

function renderizarFiltros() {
    const filtros = document.getElementById("barra-filtros");
    if (!filtros) return;
    filtros.innerHTML = "";

    const btnTodas = document.createElement("button");
    btnTodas.type = "button";
    btnTodas.className = "visor-chip" + (tablaSeleccionada === "TODAS" ? " active" : "");
    btnTodas.textContent = "Mostrar todas las tablas";
    btnTodas.addEventListener("click", () => {
        tablaSeleccionada = "TODAS";
        renderizarFiltros();
        renderizarTablas();
    });
    filtros.appendChild(btnTodas);

    Object.keys(cacheTablas).forEach((nombre, idx) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "visor-chip" + (tablaSeleccionada === nombre ? " active" : "");
        btn.textContent = `${idx + 1}. ${nombre} (${(cacheTablas[nombre] || []).length})`;
        btn.addEventListener("click", () => {
            tablaSeleccionada = nombre;
            renderizarFiltros();
            renderizarTablas();
        });
        filtros.appendChild(btn);
    });
}

function renderizarTablas() {
    const cont = document.getElementById("contenedor-tablas");
    if (!cont) return;
    cont.innerHTML = "";

    const nombres = tablaSeleccionada === "TODAS" ? Object.keys(cacheTablas) : [tablaSeleccionada];
    for (const nombre of nombres) {
        const filas = cacheTablas[nombre] || [];
        const section = document.createElement("section");
        section.className = "card shadow-sm border mb-4";

        const header = document.createElement("div");
        header.className = "card-header d-flex justify-content-between align-items-center bg-light fw-semibold";
        const spanTitulo = document.createElement("span");
        spanTitulo.textContent = "Tabla: ";
        const codeNombre = document.createElement("code");
        codeNombre.textContent = nombre;
        spanTitulo.appendChild(codeNombre);

        const spanCount = document.createElement("span");
        spanCount.className = "badge text-bg-secondary";
        spanCount.textContent = `${filas.length} registros`;

        header.appendChild(spanTitulo);
        header.appendChild(spanCount);
        section.appendChild(header);

        if (filas.length === 0) {
            const emp = document.createElement("div");
            emp.className = "p-3 text-center text-muted small";
            emp.textContent = "La tabla no contiene registros actualmente.";
            section.appendChild(emp);
        } else {
            const wrap = document.createElement("div");
            wrap.className = "visor-table-wrap";
            const tbl = document.createElement("table");
            tbl.className = "table table-sm table-hover mb-0 visor-table";

            const thead = document.createElement("thead");
            const trHead = document.createElement("tr");
            const columnas = Object.keys(filas[0]);
            for (const c of columnas) {
                const th = document.createElement("th");
                th.textContent = c;
                trHead.appendChild(th);
            }
            thead.appendChild(trHead);
            tbl.appendChild(thead);

            const tbody = document.createElement("tbody");
            for (const f of filas) {
                const tr = document.createElement("tr");
                for (const c of columnas) {
                    const td = document.createElement("td");
                    td.textContent = f[c] !== null && f[c] !== undefined ? String(f[c]) : "—";
                    tr.appendChild(td);
                }
                tbody.appendChild(tr);
            }
            tbl.appendChild(tbody);
            wrap.appendChild(tbl);
            section.appendChild(wrap);
        }
        cont.appendChild(section);
    }
}

async function cargarTablas() {
    const metaEl = document.getElementById("meta-bd");
    const contEl = document.getElementById("contenedor-tablas");
    const sesion = obtenerSesion();
    if (!sesion || !sesion.token) {
        if (metaEl) {
            metaEl.textContent =
                "Acceso restringido: inicia sesión como Administrador para consultar las 16 tablas.";
        }
        if (contEl) contEl.innerHTML = "";
        return;
    }

    const selectLimite = document.getElementById("select-limite-bd");
    const limitVal = selectLimite ? selectLimite.value : "100";
    const endpoint = limitVal ? `/api/bd/tablas?limit=${encodeURIComponent(limitVal)}` : "/api/bd/tablas";

    try {
        const data = await peticionApi(endpoint);
        cacheTablas = data.tablas || {};
        if (metaEl) {
            metaEl.textContent = `Total tablas activas: ${data.total_tablas} | Base de datos: ${data.motor_bd}`;
        }
        renderizarFiltros();
        renderizarTablas();
    } catch (err) {
        if (metaEl) {
            metaEl.textContent = err.message || "Acceso denegado al visor de base de datos.";
        }
        if (contEl) contEl.innerHTML = "";
    }
}

function iniciarVisorBD() {
    const btnRefrescar = document.getElementById("btn-refrescar-bd");
    const selectLimite = document.getElementById("select-limite-bd");
    if (btnRefrescar) btnRefrescar.addEventListener("click", cargarTablas);
    if (selectLimite) selectLimite.addEventListener("change", cargarTablas);
    cargarTablas();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciarVisorBD);
} else {
    iniciarVisorBD();
}
