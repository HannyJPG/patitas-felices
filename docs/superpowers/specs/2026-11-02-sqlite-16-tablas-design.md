# Diseño de Unificación de Base de Datos SQLite (Modelo Académico de 16 Tablas)

## 1. Propósito y Alcance
Unificar el modelo de datos de **Clínica Veterinaria Patitas Felices** para que el entregable académico (`prueba_1.erd.json` y `schema_sqlite.sql`) y la base de datos operativa en vivo (`patitas_felices.db` vía `SQLiteDatabaseAdapter`) utilicen **exactamente las mismas 16 tablas relacionales en 3FN**, sin tablas paralelas duplicadas ni scripts de otros motores no utilizados.

## 2. Archivos de la Carpeta `database/`
- **Conservar y actualizar:**
  1. `database/prueba_1.erd.json`: Diagrama Entidad-Relación con las 16 tablas, nombres sin espacios sobrantes, tipos de datos corregidos y las 16 relaciones (`FOREIGN KEY`) completas.
  2. `database/patitas_felices.db`: Base de datos SQLite en vivo con las 16 tablas pobladas con datos coherentes y sin las 4 tablas redundantes (`mascotas`, `citas`, `ventas`, `solicitudes_mascota`).
  3. `database/schema_sqlite.sql`: Guion DDL/DML en texto plano con los `CREATE TABLE`, `FOREIGN KEY` y `INSERT` semilla de las 16 tablas para revisión docente directa.
- **Eliminar:**
  1. `database/schema_mysql.sql` (esquema antiguo de 6 tablas en MySQL).
  2. `database/schema_supabase_postgres.sql` (esquema antiguo de 6 tablas en Supabase).

## 3. Las 16 Tablas Canónicas y su Rol Funcional en la Web
1. **`usuarios`**: Autenticación PBKDF2-SHA256, roles RBAC (`cliente`, `doctor`, `admin`) y estado (`activo`/`inactivo`) validado por `SecurityProxy`.
2. **`Dueno`**: Datos del propietario (`id_dueno`, `usuario_id` FK → `usuarios`, `dni`, `tipo_documento`, `nombres`, `apellidos`, `correo`, `telefono`).
3. **`Especie`**: Catálogo taxonómico (`Id_especie`, `Nombre`, `Descripcion`).
4. **`Razas`**: Catálogo de razas (`Id_raza`, `Id_especie` FK → `Especie`, `nombre`, `Descripcion`).
5. **`Paciente`**: Mascotas registradas (`id_paciente`, `id_dueno` FK → `Dueno`, `Id_raza` FK → `Razas`, `nombre`, `sexo`, `fecha_nacimiento`, `edad`, `peso_kg`, `historial_resumen`, `estado` y campos de solicitud de modificación/baja). Reemplaza a `mascotas` y `solicitudes_mascota`.
6. **`Especialidad`**: Catálogo de especialidades médicas (`Id_especialidad`, `Nombre`, `Descripcion`).
7. **`Veterinario`**: Médicos veterinarios (`Id_veterinario`, `usuario_id` FK → `usuarios`, `Id_especialidad` FK → `Especialidad`, `numero_colegiatura`, `nombres`, `Apellidos`, `Telefono`, `correo`, `Fecha_contratacion`).
8. **`Servicios`**: Catálogo de servicios clínicos y precios (`Id_servicios`, `Nombre`, `Precio`, `Estado`).
9. **`Cita`**: Agenda médica y turnos (`Id_cita`, `Id_veterinario` FK → `Veterinario`, `id_paciente` FK → `Paciente`, `fecha`, `hora`, `motivo`, `estado`, `propietario`, `telefono`, `mascota_nombre`, `servicio`, `whatsapp_url`). Reemplaza a `citas`.
10. **`Detalle_servicios`**: Desglose de servicios aplicados por cita (`Id_cita` FK → `Cita`, `Id_servicios` FK → `Servicios`, `precio_aplicado`).
11. **`Historial_clinico`**: Evaluación médica registrada por el doctor al atender una cita (`Id_historial`, `Id_cita` FK → `Cita`, `Fecha`, `Diagnostico`, `Tratamiento`, `Observaciones`).
12. **`Receta`**: Prescripción farmacológica e indicaciones (`Id_receta`, `Id_historial` FK → `Historial_clinico`, `medicamento`, `Dosis`, `duracion_dias`, `indicaciones`).
13. **`Factura`**: Comprobantes electrónicos Boleta/Factura generados en tienda o consulta (`id_factura`, `Id_cita` FK opcional → `Cita`, `id_dueno` FK → `Dueno`, `tipo`, `serie`, `numero`, `numero_boleta`, `cliente_nombre`, `cliente_documento`, `subtotal`, `igv`, `total`, `metodo_pago`, `estado`, `pdf_url`). Reemplaza a `ventas`.
14. **`Pago`**: Registro de transacción de pago asociada al comprobante (`id_pago`, `id_factura` FK → `Factura`, `metodo_pago`, `monto`, `estado`, `fecha_pago`, `referencia`).
15. **`productos`**: Catálogo de tienda y farmacia (`id`, `codigo`, `nombre`, `categoria`, `descripcion`, `precio`, `stock`, `activo`).
16. **`detalle_ventas`**: Ítems de productos vendidos en cada comprobante (`id`, `id_factura` FK → `Factura`, `producto_id` FK → `productos`, `producto_nombre`, `cantidad`, `precio_unitario`, `subtotal`).

## 4. Compatibilidad de Contratos API
- `SQLiteDatabaseAdapter` ejecutará todas las lecturas y escrituras sobre las 16 tablas canónicas, proyectando los alias necesarios (`id`, `usuario_id`, `venta_id`, etc.) para mantener compatibilidad al 100% con el frontend Astro y con la suite de 20 pruebas automatizadas (`test_patterns_and_api.py`).
