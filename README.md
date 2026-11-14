# Clínica Veterinaria Patitas Felices — Sistema Web Integral

Sistema de gestión y portal web para clínica veterinaria con arquitectura de software orientada a servicios.

## Stack Tecnológico

1. **Frontend:** Astro con HTML5, Bootstrap 5 y JavaScript.
   * Portal institucional con catálogo de servicios y agendamiento de citas médicas.
   * Tienda y checkout con generación de boletas PDF.
   * Portal unificado, control a acceso de usuario  (Cliente, Doctor, Administrador).
2. **Backend:** Python con FastAPI, Pydantic y Uvicorn.
   * Arquitectura basada en patrones GoF (Strategy, Facade, Proxy, Adapter).
   * Generación de comprobantes en memoria y autenticación JWT.
3. **Base de Datos:** Microsoft SQL Server (`PatitasFelices_DB`) con esquema relacional normalizado en 3FN de 16 tablas .

## Variables de Entorno Requeridas

- `DB_ENGINE`: `sqlserver`
- `SQLSERVER_SERVER`: `localhost`
- `SQLSERVER_DATABASE`: `PatitasFelices_DB`
- `SQLSERVER_DRIVER`: `ODBC Driver 17 for SQL Server`
- `JWT_SECRET`: Clave de firma para sesiones JWT
- `CLINICA_WHATSAPP`: Número telefónico para atención por WhatsApp 
