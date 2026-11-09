-- =============================================================================
-- ESQUEMA CANÓNICO EN TERCERA FORMA NORMAL (3FN) - 16 TABLAS (0 REDUNDANCIAS)
-- Motor: Microsoft SQL Server (T-SQL)
-- Base de Datos: PatitasFelices_DB
-- Clínica Veterinaria Patitas Felices
-- =============================================================================

IF DB_ID(N'PatitasFelices_DB') IS NULL
BEGIN
    CREATE DATABASE [PatitasFelices_DB];
END
GO

USE [PatitasFelices_DB];
GO
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- Eliminar restricciones UNIQUE en línea sobre columnas anulables si existían de una versión previa
DECLARE @drop_uq_sql NVARCHAR(MAX) = N'';
SELECT @drop_uq_sql += N'ALTER TABLE dbo.' + QUOTENAME(t.name) + N' DROP CONSTRAINT ' + QUOTENAME(kc.name) + N';'
FROM sys.key_constraints kc
JOIN sys.tables t ON kc.parent_object_id = t.object_id
JOIN sys.index_columns ic ON kc.parent_object_id = ic.object_id AND kc.unique_index_id = ic.index_id
JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
WHERE kc.type = 'UQ'
  AND (
      (t.name = 'Dueno' AND c.name = 'usuario_id')
      OR (t.name = 'Veterinario' AND c.name = 'usuario_id')
      OR (t.name = 'Factura' AND c.name = 'Id_cita')
  );
IF LEN(@drop_uq_sql) > 0
    EXEC sp_executesql @drop_uq_sql;
GO

-- 1. usuarios (8 columnas)
IF OBJECT_ID(N'dbo.usuarios', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.usuarios (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        nombre NVARCHAR(120) NOT NULL,
        email VARCHAR(150) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        rol VARCHAR(20) NOT NULL CHECK (rol IN ('cliente', 'doctor', 'admin')),
        estado VARCHAR(20) NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'inactivo')),
        telefono VARCHAR(30) NOT NULL DEFAULT '',
        creado_en DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
    );
END
GO

-- 2. Dueno (8 columnas)
IF OBJECT_ID(N'dbo.Dueno', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Dueno (
        id_dueno INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        usuario_id INT NULL,
        dni VARCHAR(20) NOT NULL UNIQUE,
        tipo_documento VARCHAR(10) NOT NULL DEFAULT 'DNI',
        nombres NVARCHAR(80) NOT NULL,
        apellidos NVARCHAR(80) NOT NULL,
        telefono VARCHAR(30) NOT NULL,
        fecha_registro DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
        CONSTRAINT FK_Dueno_usuarios FOREIGN KEY (usuario_id) REFERENCES dbo.usuarios(id) ON DELETE SET NULL
    );
END
GO

-- 3. Especie (3 columnas)
IF OBJECT_ID(N'dbo.Especie', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Especie (
        Id_especie INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Nombre NVARCHAR(60) NOT NULL UNIQUE,
        Descripcion NVARCHAR(255) NOT NULL
    );
END
GO

-- 4. Razas (4 columnas)
IF OBJECT_ID(N'dbo.Razas', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Razas (
        Id_raza INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Id_especie INT NOT NULL,
        nombre NVARCHAR(80) NOT NULL,
        Descripcion NVARCHAR(255) NOT NULL DEFAULT '',
        CONSTRAINT UQ_Razas_Especie_Nombre UNIQUE (Id_especie, nombre),
        CONSTRAINT FK_Razas_Especie FOREIGN KEY (Id_especie) REFERENCES dbo.Especie(Id_especie)
    );
END
GO

-- 5. Paciente (15 columnas - sin edad redundante; se calcula desde fecha_nacimiento)
IF OBJECT_ID(N'dbo.Paciente', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Paciente (
        id_paciente INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        id_dueno INT NOT NULL,
        Id_raza INT NOT NULL,
        nombre NVARCHAR(80) NOT NULL,
        sexo CHAR(1) NOT NULL DEFAULT 'H',
        fecha_nacimiento DATE NOT NULL DEFAULT '2023-05-10',
        peso_kg DECIMAL(6,2) NOT NULL DEFAULT 5.00,
        historial_resumen NVARCHAR(MAX) NULL DEFAULT '',
        estado VARCHAR(20) NOT NULL DEFAULT 'Activo',
        fecha_registro DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
        solicitud_tipo VARCHAR(20) NULL CHECK (solicitud_tipo IN ('editar', 'eliminar')),
        solicitud_datos_nuevos NVARCHAR(MAX) NULL,
        solicitud_motivo NVARCHAR(500) NULL,
        solicitud_estado VARCHAR(20) NULL CHECK (solicitud_estado IN ('pendiente', 'aprobada', 'rechazada')),
        solicitud_creado_en DATETIME2(0) NULL,
        CONSTRAINT FK_Paciente_Dueno FOREIGN KEY (id_dueno) REFERENCES dbo.Dueno(id_dueno),
        CONSTRAINT FK_Paciente_Razas FOREIGN KEY (Id_raza) REFERENCES dbo.Razas(Id_raza)
    );
END
GO

-- 6. Especialidad (3 columnas)
IF OBJECT_ID(N'dbo.Especialidad', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Especialidad (
        Id_especialidad INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Nombre NVARCHAR(100) NOT NULL UNIQUE,
        Descripcion NVARCHAR(255) NOT NULL
    );
END
GO

-- 7. Veterinario (8 columnas - sin correo redundante; se obtiene desde usuarios.email)
IF OBJECT_ID(N'dbo.Veterinario', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Veterinario (
        Id_veterinario INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        usuario_id INT NULL,
        Id_especialidad INT NOT NULL,
        numero_colegiatura VARCHAR(30) NOT NULL UNIQUE,
        nombres NVARCHAR(80) NOT NULL,
        Apellidos NVARCHAR(80) NOT NULL,
        Telefono VARCHAR(30) NOT NULL,
        Fecha_contratacion DATE NOT NULL,
        CONSTRAINT FK_Veterinario_usuarios FOREIGN KEY (usuario_id) REFERENCES dbo.usuarios(id) ON DELETE SET NULL,
        CONSTRAINT FK_Veterinario_Especialidad FOREIGN KEY (Id_especialidad) REFERENCES dbo.Especialidad(Id_especialidad)
    );
END
GO

-- 8. Servicios (4 columnas)
IF OBJECT_ID(N'dbo.Servicios', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Servicios (
        Id_servicios INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Nombre NVARCHAR(100) NOT NULL UNIQUE,
        Precio DECIMAL(10,2) NOT NULL,
        Estado VARCHAR(20) NOT NULL DEFAULT 'Activo'
    );
END
GO

-- 9. Cita (9 columnas - sin propietario, telefono, mascota_nombre ni servicio redundantes)
IF OBJECT_ID(N'dbo.Cita', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Cita (
        Id_cita INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Id_veterinario INT NOT NULL,
        id_paciente INT NULL,
        fecha DATE NOT NULL,
        hora VARCHAR(10) NOT NULL,
        motivo NVARCHAR(500) NOT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
        whatsapp_url NVARCHAR(1000) NOT NULL DEFAULT '',
        fecha_registro DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
        CONSTRAINT FK_Cita_Veterinario FOREIGN KEY (Id_veterinario) REFERENCES dbo.Veterinario(Id_veterinario),
        CONSTRAINT FK_Cita_Paciente FOREIGN KEY (id_paciente) REFERENCES dbo.Paciente(id_paciente) ON DELETE SET NULL
    );
END
GO

-- 10. Detalle_servicios (3 columnas)
IF OBJECT_ID(N'dbo.Detalle_servicios', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Detalle_servicios (
        Id_cita INT NOT NULL,
        Id_servicios INT NOT NULL,
        precio_aplicado DECIMAL(10,2) NOT NULL,
        CONSTRAINT PK_Detalle_servicios PRIMARY KEY (Id_cita, Id_servicios),
        CONSTRAINT FK_Detalle_servicios_Cita FOREIGN KEY (Id_cita) REFERENCES dbo.Cita(Id_cita) ON DELETE CASCADE,
        CONSTRAINT FK_Detalle_servicios_Servicios FOREIGN KEY (Id_servicios) REFERENCES dbo.Servicios(Id_servicios)
    );
END
GO

-- 11. Historial_clinico (6 columnas)
IF OBJECT_ID(N'dbo.Historial_clinico', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Historial_clinico (
        Id_historial INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Id_cita INT NOT NULL,
        Fecha DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
        Diagnostico NVARCHAR(MAX) NOT NULL DEFAULT '',
        Tratamiento NVARCHAR(MAX) NOT NULL DEFAULT '',
        Observaciones NVARCHAR(MAX) NOT NULL DEFAULT '',
        CONSTRAINT FK_Historial_clinico_Cita FOREIGN KEY (Id_cita) REFERENCES dbo.Cita(Id_cita) ON DELETE CASCADE
    );
END
GO

-- 12. Receta (6 columnas)
IF OBJECT_ID(N'dbo.Receta', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Receta (
        Id_receta INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Id_historial INT NOT NULL,
        medicamento NVARCHAR(150) NOT NULL,
        Dosis NVARCHAR(100) NOT NULL,
        duracion_dias INT NOT NULL,
        indicaciones NVARCHAR(500) NOT NULL,
        CONSTRAINT FK_Receta_Historial_clinico FOREIGN KEY (Id_historial) REFERENCES dbo.Historial_clinico(Id_historial) ON DELETE CASCADE
    );
END
GO

-- 13. Factura (12 columnas - sin numero_boleta, cliente_nombre, cliente_documento ni metodo_pago redundantes)
IF OBJECT_ID(N'dbo.Factura', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Factura (
        id_factura INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Id_cita INT NULL,
        id_dueno INT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'Boleta',
        serie VARCHAR(10) NOT NULL DEFAULT 'B001',
        numero INT NOT NULL,
        fecha_emision DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
        subtotal DECIMAL(10,2) NOT NULL,
        igv DECIMAL(10,2) NOT NULL,
        total DECIMAL(10,2) NOT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'Pagado',
        pdf_url NVARCHAR(500) NULL,
        CONSTRAINT UQ_Factura_Serie_Numero UNIQUE (serie, numero),
        CONSTRAINT FK_Factura_Cita FOREIGN KEY (Id_cita) REFERENCES dbo.Cita(Id_cita) ON DELETE SET NULL,
        CONSTRAINT FK_Factura_Dueno FOREIGN KEY (id_dueno) REFERENCES dbo.Dueno(id_dueno) ON DELETE SET NULL
    );
END
GO

-- 14. Pago (7 columnas)
IF OBJECT_ID(N'dbo.Pago', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Pago (
        id_pago INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        id_factura INT NOT NULL,
        metodo_pago VARCHAR(50) NOT NULL,
        monto DECIMAL(10,2) NOT NULL DEFAULT 0,
        estado VARCHAR(20) NOT NULL DEFAULT 'Pagado',
        fecha_pago DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
        referencia VARCHAR(100) NULL,
        CONSTRAINT FK_Pago_Factura FOREIGN KEY (id_factura) REFERENCES dbo.Factura(id_factura) ON DELETE CASCADE
    );
END
GO

-- 15. productos (8 columnas)
IF OBJECT_ID(N'dbo.productos', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.productos (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        codigo VARCHAR(30) NOT NULL UNIQUE,
        nombre NVARCHAR(150) NOT NULL,
        categoria NVARCHAR(60) NOT NULL,
        descripcion NVARCHAR(500) NOT NULL,
        precio DECIMAL(10,2) NOT NULL,
        stock INT NOT NULL DEFAULT 0,
        activo BIT NOT NULL DEFAULT 1
    );
END
GO

-- 16. detalle_ventas (6 columnas - sin producto_nombre redundante)
IF OBJECT_ID(N'dbo.detalle_ventas', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.detalle_ventas (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        id_factura INT NOT NULL,
        producto_id INT NOT NULL,
        cantidad INT NOT NULL,
        precio_unitario DECIMAL(10,2) NOT NULL,
        subtotal DECIMAL(10,2) NOT NULL,
        CONSTRAINT FK_detalle_ventas_Factura FOREIGN KEY (id_factura) REFERENCES dbo.Factura(id_factura) ON DELETE CASCADE,
        CONSTRAINT FK_detalle_ventas_productos FOREIGN KEY (producto_id) REFERENCES dbo.productos(id)
    );
END
GO

-- Índices únicos filtrados (permiten múltiples NULL en SQL Server conforme al estándar ANSI SQL)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UQ_Dueno_usuario' AND object_id = OBJECT_ID(N'dbo.Dueno'))
    CREATE UNIQUE INDEX UQ_Dueno_usuario ON dbo.Dueno(usuario_id) WHERE usuario_id IS NOT NULL;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UQ_Veterinario_usuario' AND object_id = OBJECT_ID(N'dbo.Veterinario'))
    CREATE UNIQUE INDEX UQ_Veterinario_usuario ON dbo.Veterinario(usuario_id) WHERE usuario_id IS NOT NULL;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UQ_Factura_cita' AND object_id = OBJECT_ID(N'dbo.Factura'))
    CREATE UNIQUE INDEX UQ_Factura_cita ON dbo.Factura(Id_cita) WHERE Id_cita IS NOT NULL;

-- Índices de rendimiento sobre llaves foráneas y búsquedas frecuentes
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Dueno_usuario' AND object_id = OBJECT_ID(N'dbo.Dueno'))
    CREATE INDEX IX_Dueno_usuario ON dbo.Dueno(usuario_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Razas_especie' AND object_id = OBJECT_ID(N'dbo.Razas'))
    CREATE INDEX IX_Razas_especie ON dbo.Razas(Id_especie);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Paciente_dueno' AND object_id = OBJECT_ID(N'dbo.Paciente'))
    CREATE INDEX IX_Paciente_dueno ON dbo.Paciente(id_dueno);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Paciente_raza' AND object_id = OBJECT_ID(N'dbo.Paciente'))
    CREATE INDEX IX_Paciente_raza ON dbo.Paciente(Id_raza);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Veterinario_especialidad' AND object_id = OBJECT_ID(N'dbo.Veterinario'))
    CREATE INDEX IX_Veterinario_especialidad ON dbo.Veterinario(Id_especialidad);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Cita_fecha_hora' AND object_id = OBJECT_ID(N'dbo.Cita'))
    CREATE INDEX IX_Cita_fecha_hora ON dbo.Cita(fecha, hora);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Cita_paciente' AND object_id = OBJECT_ID(N'dbo.Cita'))
    CREATE INDEX IX_Cita_paciente ON dbo.Cita(id_paciente);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Cita_veterinario' AND object_id = OBJECT_ID(N'dbo.Cita'))
    CREATE INDEX IX_Cita_veterinario ON dbo.Cita(Id_veterinario);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Historial_cita' AND object_id = OBJECT_ID(N'dbo.Historial_clinico'))
    CREATE INDEX IX_Historial_cita ON dbo.Historial_clinico(Id_cita);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Receta_historial' AND object_id = OBJECT_ID(N'dbo.Receta'))
    CREATE INDEX IX_Receta_historial ON dbo.Receta(Id_historial);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Factura_dueno' AND object_id = OBJECT_ID(N'dbo.Factura'))
    CREATE INDEX IX_Factura_dueno ON dbo.Factura(id_dueno);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Pago_factura' AND object_id = OBJECT_ID(N'dbo.Pago'))
    CREATE INDEX IX_Pago_factura ON dbo.Pago(id_factura);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_detalle_ventas_factura' AND object_id = OBJECT_ID(N'dbo.detalle_ventas'))
    CREATE INDEX IX_detalle_ventas_factura ON dbo.detalle_ventas(id_factura);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_detalle_ventas_producto' AND object_id = OBJECT_ID(N'dbo.detalle_ventas'))
    CREATE INDEX IX_detalle_ventas_producto ON dbo.detalle_ventas(producto_id);
GO
