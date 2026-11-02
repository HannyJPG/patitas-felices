# Unificación de Base de Datos SQLite (16 Tablas) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unificar el diagrama ERD (`prueba_1.erd.json`), el guion DDL (`schema_sqlite.sql`) y el motor en vivo (`patitas_felices.db` vía `SQLiteDatabaseAdapter`) bajo las 16 tablas relacionales canónicas en 3FN, eliminando las 4 tablas paralelas duplicadas y los scripts SQL obsoletos.

**Architecture:** `backend/patterns/sqlite_schema.py` define el DDL y seed de las 16 tablas canónicas. `SQLiteDatabaseAdapter` en `backend/patterns/adapter.py` ejecuta todas las lecturas y escrituras sobre esas 16 tablas manteniendo el contrato de diccionarios consumido por FastAPI y el frontend Astro.

**Tech Stack:** Python 3.14, SQLite3, FastAPI, Pytest, ERD Editor JSON Schema v3.0.0.

**Spec:** `docs/superpowers/specs/2026-11-02-sqlite-16-tablas-design.md`

## Global Constraints

- Exactamente 16 tablas de usuario en SQLite: `usuarios`, `Dueno`, `Especie`, `Razas`, `Paciente`, `Especialidad`, `Veterinario`, `Servicios`, `Cita`, `Detalle_servicios`, `Historial_clinico`, `Receta`, `Factura`, `Pago`, `productos`, `detalle_ventas`.
- Cero tablas paralelas (`mascotas`, `citas`, `ventas`, `solicitudes_mascota` deben ser migradas/eliminadas).
- La carpeta `database/` solo debe contener `prueba_1.erd.json`, `patitas_felices.db` y `schema_sqlite.sql`.

## Review Focus

- Creación de mascota con especie/raza nueva que aún no existe en `Especie`/`Razas` debe registrarla automáticamente y vincular `Paciente.Id_raza`.
- Atención médica de cita por el doctor (`actualizar_cita_doctor`) debe persistir diagnóstico y tratamiento en `Historial_clinico` y `Receta`, y reflejarlos al listar citas.
- Compra en tienda (`registrar_venta_y_detalles`) debe insertar en `Factura`, `detalle_ventas` y `Pago`, y `listar_ventas` / `listar_compras_usuario` deben devolver `detalles` con `venta_id` e `id`.
- Solicitudes de edición/eliminación de mascota deben almacenarse en las columnas de solicitud de `Paciente` y resolverse sin tabla `solicitudes_mascota`.
- Base de datos existente `database/patitas_felices.db` con las 4 tablas antiguas debe migrar sus filas y eliminar las 4 tablas obsoletas al inicializar el esquema.

---

### Task 1: Fase 1 — Limpieza de `database/`, `schema_sqlite.sql` y `prueba_1.erd.json`

**Files:**
- Delete: `database/schema_mysql.sql`
- Delete: `database/schema_supabase_postgres.sql`
- Create: `database/schema_sqlite.sql`
- Modify: `database/prueba_1.erd.json`
- Test: `backend/tests/test_patterns_and_api.py`

**Interfaces:**
- Produces: `database/schema_sqlite.sql` (16 tablas con `CREATE TABLE` y `FOREIGN KEY`), `database/prueba_1.erd.json` (16 `tableIds` y 16 `relationshipIds` sin espacios en nombres de tablas/columnas).

- [ ] **Step 1: Eliminar `database/schema_mysql.sql` y `database/schema_supabase_postgres.sql`**
- [ ] **Step 2: Crear `database/schema_sqlite.sql` con las 16 tablas canónicas, claves foráneas y datos semilla**
- [ ] **Step 3: Actualizar `database/prueba_1.erd.json` limpiando espacios en nombres, corrigiendo tipos (`Factura`, `Pago`, `Dueno`, `Veterinario`, `Paciente`) y declarando las 16 relaciones (`FK`)**

---

### Task 2: Fase 2 — Unificación de `SQLiteDatabaseAdapter` y `patitas_felices.db` en 16 tablas

**Files:**
- Modify: `backend/patterns/sqlite_schema.py`
- Modify: `backend/patterns/adapter.py`
- Modify: `database/patitas_felices.db`
- Test: `backend/tests/test_patterns_and_api.py`

**Interfaces:**
- Consumes: `SQLITE_SCHEMA` y `migrate_sqlite_schema` de `backend/patterns/sqlite_schema.py`
- Produces: `SQLiteDatabaseAdapter` operando exclusivamente sobre las 16 tablas canónicas.

- [ ] **Step 1: Conectar `SQLiteDatabaseAdapter.inicializar_esquema()` a `migrate_sqlite_schema` y eliminar tablas paralelas (`mascotas`, `citas`, `ventas`, `solicitudes_mascota`)**
- [ ] **Step 2: Actualizar métodos de mascotas y solicitudes (`listar_mascotas`, `crear_mascota`, `eliminar_mascota`, `crear_solicitud_mascota`, `listar_solicitudes_mascota`, `resolver_solicitud_mascota`) para operar sobre `Paciente`, `Dueno`, `Razas` y `Especie`**
- [ ] **Step 3: Actualizar métodos de citas e historial (`crear_cita`, `listar_citas`, `actualizar_cita_doctor`, `obtener_disponibilidad_horarios`) para operar sobre `Cita`, `Detalle_servicios`, `Historial_clinico`, `Receta` y `Servicios`**
- [ ] **Step 4: Actualizar métodos de facturación y ventas (`registrar_venta_y_detalles`, `listar_ventas`, `listar_compras_usuario`) para operar sobre `Factura`, `detalle_ventas` y `Pago`**

---

### Task 3: Fase 3 — Verificación Integral de las 16 Tablas y Suite de Pruebas

**Files:**
- Modify: `backend/tests/test_patterns_and_api.py`

- [ ] **Step 1: Agregar aserción de verificación de las 16 tablas exactas en SQLite (sin tablas duplicadas) y ejecutar `pytest backend/tests/test_patterns_and_api.py -v`**
- [ ] **Step 2: Ejecutar `npm run build` y `node scripts/verificar-migracion.mjs`**
