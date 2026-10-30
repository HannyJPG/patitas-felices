# Clínica Veterinaria Patitas Felices — Sistema Web Integral

Sistema de gestión y portal web para clínica veterinaria con arquitectura de software orientada a servicios.

## Stack Tecnológico

1. **Frontend:** Astro con HTML5, Bootstrap 5 y JavaScript.
   * Portal institucional con catálogo de servicios y agendamiento de citas médicas.
   * Tienda y checkout con generación de boletas PDF.
   * Portal unificado (`/perfil`) con control de accesos basado en roles (Cliente, Doctor, Administrador).
2. **Backend:** Python con FastAPI, Pydantic y Uvicorn.
   * Arquitectura basada en patrones GoF (Strategy, Facade, Proxy, Adapter).
   * Generación de comprobantes en memoria y autenticación JWT.
3. **Base de Datos:** PostgreSQL en la nube (Supabase) con esquema relacional de 16 tablas.

## Despliegue en Producción

El proyecto incluye un `Dockerfile` optimizado en dos fases:
- **Fase 1 (Frontend):** Compilación de activos estáticos con Astro.
- **Fase 2 (Backend):** Servidor FastAPI sirviendo la API REST y las vistas web estáticas unificadas en el puerto asignado.

### Variables de Entorno Requeridas

- `DB_ENGINE`: `supabase`
- `SUPABASE_URL`: URL del proyecto en Supabase
- `SUPABASE_KEY`: Clave pública (anon key)
- `JWT_SECRET`: Clave de firma para sesiones JWT
- `CLINICA_WHATSAPP`: Número telefónico para atención por WhatsApp (ej. `51990853697`)
