import { spawn } from "node:child_process";

console.log("=========================================================================");
console.log("  CLÍNICA VETERINARIA PATITAS FELICES - INICIANDO TODO EL SISTEMA");
console.log("=========================================================================");
console.log("  1. Página Pública (Astro)          : http://127.0.0.1:4321/");
console.log("  2. Inicio de Sesión por Rol        : http://127.0.0.1:4321/login");
console.log("  3. Espacio del Propietario/Cliente : http://127.0.0.1:4321/cliente");
console.log("  4. Espacio del Veterinario         : http://127.0.0.1:4321/doctor");
console.log("  5. App Administrativa (Integrada)  : http://127.0.0.1:4321/admin-app");
console.log("  6. Visor de Base de Datos          : http://127.0.0.1:8000/visor-bd");
console.log("  7. Documentación API (Swagger)     : http://127.0.0.1:8000/docs");
console.log("=========================================================================\n");

const backend = spawn(
    "python",
    ["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
    { stdio: "inherit", shell: true }
);

const frontend = spawn(
    "npm.cmd",
    ["run", "dev"],
    { stdio: "inherit", shell: true }
);

function detenerProcesos() {
    backend.kill();
    frontend.kill();
    process.exit(0);
}

process.on("SIGINT", detenerProcesos);
process.on("SIGTERM", detenerProcesos);
