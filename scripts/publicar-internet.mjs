import { spawn } from "node:child_process";

console.log("=========================================================================");
console.log("  PUBLICANDO CLÍNICA PATITAS FELICES EN INTERNET (HOSTING EN VIVO)");
console.log("  Unificando Frontend Astro + Backend FastAPI + 16 Tablas en puerto 8000");
console.log("=========================================================================\n");

const servidor = spawn(
    "python",
    ["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"],
    { stdio: "inherit", shell: true }
);

setTimeout(() => {
    console.log("\nGenerando enlace público HTTPS accesible desde cualquier celular o PC...\n");
    const tunel = spawn(
        "npx.cmd",
        ["--yes", "localtunnel", "--port", "8000"],
        { stdio: "inherit", shell: true }
    );

    function cerrar() {
        tunel.kill();
        servidor.kill();
        process.exit(0);
    }
    process.on("SIGINT", cerrar);
    process.on("SIGTERM", cerrar);
}, 2500);
