import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

console.log("=========================================================================");
console.log("  CLÍNICA VETERINARIA PATITAS FELICES - MICROSOFT SQL SERVER");
console.log("=========================================================================");
console.log("  1. Portal Principal y Vistas       : http://127.0.0.1:8000/");
console.log("  2. Inicio de Sesión / Perfil       : http://127.0.0.1:8000/perfil");
console.log("  3. Espacio del Veterinario         : http://127.0.0.1:8000/doctor");
console.log("  4. App Administrativa (CRM)        : http://127.0.0.1:8000/admin-app");
console.log("  5. Visor en Vivo de las 16 Tablas  : http://127.0.0.1:8000/visor-bd");
console.log("  6. Documentación API (Swagger)     : http://127.0.0.1:8000/docs");
console.log("=========================================================================\n");

const backend = spawn(
    "python",
    ["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
    { stdio: "inherit", shell: true }
);

let frontend = null;
const tieneAstroLocal = existsSync(join(process.cwd(), "node_modules", ".bin", "astro")) ||
                       existsSync(join(process.cwd(), "node_modules", ".bin", "astro.cmd"));

if (tieneAstroLocal) {
    console.log("-> Se detectó entorno Astro local. Iniciando servidor Astro en http://127.0.0.1:4321/...");
    frontend = spawn(
        "npm.cmd",
        ["run", "dev"],
        { stdio: "inherit", shell: true }
    );
} else {
    console.log("-> El sistema se ejecuta de forma unificada desde FastAPI (puerto 8000), sirviendo el Frontend compilado y la API con SQL Server.");
}

function detenerProcesos() {
    backend.kill();
    if (frontend) {
        frontend.kill();
    }
    process.exit(0);
}

process.on("SIGINT", detenerProcesos);
process.on("SIGTERM", detenerProcesos);
