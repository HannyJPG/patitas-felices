-- =============================================================================
-- CLÍNICA VETERINARIA PATITAS FELICES - ESQUEMA RELACIONAL SQLITE (16 TABLAS)
-- Modelo normalizado en 3FN sincronizado con `prueba_1.erd.json` y `patitas_felices.db`
-- =============================================================================

PRAGMA foreign_keys = ON;

-- 1. Tabla: usuarios (Seguridad Proxy JWT y Roles RBAC: cliente, doctor, admin)
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('cliente', 'doctor', 'admin')),
    estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'inactivo')),
    telefono TEXT,
    tipo_documento TEXT DEFAULT 'DNI',
    documento TEXT UNIQUE,
    creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 2. Tabla: Dueno (Datos oficiales del propietario vinculado a su cuenta de usuario)
CREATE TABLE IF NOT EXISTS Dueno (
    id_dueno INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER UNIQUE,
    dni TEXT NOT NULL UNIQUE,
    tipo_documento TEXT NOT NULL DEFAULT 'DNI',
    correo TEXT NOT NULL UNIQUE,
    nombres TEXT NOT NULL,
    apellidos TEXT NOT NULL,
    telefono TEXT NOT NULL,
    fecha_registro TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
);

-- 3. Tabla: Especie (Catálogo taxonómico de especies atendidas)
CREATE TABLE IF NOT EXISTS Especie (
    Id_especie INTEGER PRIMARY KEY AUTOINCREMENT,
    Nombre TEXT NOT NULL UNIQUE,
    Descripcion TEXT NOT NULL
);

-- 4. Tabla: Razas (Catálogo de razas vinculado a Especie)
CREATE TABLE IF NOT EXISTS Razas (
    Id_raza INTEGER PRIMARY KEY AUTOINCREMENT,
    Id_especie INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    Descripcion TEXT,
    UNIQUE (Id_especie, nombre),
    FOREIGN KEY (Id_especie) REFERENCES Especie(Id_especie)
);

-- 5. Tabla: Paciente (Ficha clínica de mascotas y control de solicitudes del propietario)
CREATE TABLE IF NOT EXISTS Paciente (
    id_paciente INTEGER PRIMARY KEY AUTOINCREMENT,
    id_dueno INTEGER NOT NULL,
    Id_raza INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    sexo TEXT NOT NULL DEFAULT 'H',
    fecha_nacimiento TEXT NOT NULL DEFAULT '2023-05-10',
    edad INTEGER NOT NULL DEFAULT 1,
    peso_kg REAL NOT NULL DEFAULT 5.0,
    historial_resumen TEXT,
    estado TEXT NOT NULL DEFAULT 'Activo',
    fecha_registro TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    solicitud_tipo TEXT CHECK (solicitud_tipo IN ('editar', 'eliminar')),
    solicitud_datos_nuevos TEXT,
    solicitud_motivo TEXT,
    solicitud_estado TEXT CHECK (solicitud_estado IN ('pendiente', 'aprobada', 'rechazada')),
    solicitud_creado_en TEXT,
    FOREIGN KEY (id_dueno) REFERENCES Dueno(id_dueno),
    FOREIGN KEY (Id_raza) REFERENCES Razas(Id_raza)
);

-- 6. Tabla: Especialidad (Catálogo de especialidades médico-veterinarias)
CREATE TABLE IF NOT EXISTS Especialidad (
    Id_especialidad INTEGER PRIMARY KEY AUTOINCREMENT,
    Nombre TEXT NOT NULL UNIQUE,
    Descripcion TEXT NOT NULL
);

-- 7. Tabla: Veterinario (Personal médico colegiado CMVP vinculado a Especialidad y usuarios)
CREATE TABLE IF NOT EXISTS Veterinario (
    Id_veterinario INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER UNIQUE,
    Id_especialidad INTEGER NOT NULL,
    numero_colegiatura TEXT NOT NULL UNIQUE,
    nombres TEXT NOT NULL,
    Apellidos TEXT NOT NULL,
    Telefono TEXT NOT NULL,
    correo TEXT NOT NULL UNIQUE,
    Fecha_contratacion TEXT NOT NULL,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (Id_especialidad) REFERENCES Especialidad(Id_especialidad)
);

-- 8. Tabla: Servicios (Catálogo de servicios clínicos y tarifas)
CREATE TABLE IF NOT EXISTS Servicios (
    Id_servicios INTEGER PRIMARY KEY AUTOINCREMENT,
    Nombre TEXT NOT NULL UNIQUE,
    Precio REAL NOT NULL,
    Estado TEXT NOT NULL DEFAULT 'Activo'
);

-- 9. Tabla: Cita (Agenda médica de atención vinculada a Veterinario y Paciente)
CREATE TABLE IF NOT EXISTS Cita (
    Id_cita INTEGER PRIMARY KEY AUTOINCREMENT,
    Id_veterinario INTEGER NOT NULL,
    id_paciente INTEGER,
    fecha TEXT NOT NULL,
    hora TEXT NOT NULL,
    motivo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'Pendiente',
    propietario TEXT NOT NULL DEFAULT '',
    telefono TEXT NOT NULL DEFAULT '',
    mascota_nombre TEXT NOT NULL DEFAULT '',
    servicio TEXT NOT NULL DEFAULT '',
    whatsapp_url TEXT NOT NULL DEFAULT '',
    fecha_registro TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (Id_veterinario) REFERENCES Veterinario(Id_veterinario),
    FOREIGN KEY (id_paciente) REFERENCES Paciente(id_paciente) ON DELETE SET NULL
);

-- 10. Tabla: Detalle_servicios (Relación N:M entre Cita y Servicios aplicados)
CREATE TABLE IF NOT EXISTS Detalle_servicios (
    Id_cita INTEGER NOT NULL,
    Id_servicios INTEGER NOT NULL,
    precio_aplicado REAL NOT NULL,
    PRIMARY KEY (Id_cita, Id_servicios),
    FOREIGN KEY (Id_cita) REFERENCES Cita(Id_cita) ON DELETE CASCADE,
    FOREIGN KEY (Id_servicios) REFERENCES Servicios(Id_servicios)
);

-- 11. Tabla: Historial_clinico (Evaluaciones médicas, diagnóstico y tratamiento por Cita)
CREATE TABLE IF NOT EXISTS Historial_clinico (
    Id_historial INTEGER PRIMARY KEY AUTOINCREMENT,
    Id_cita INTEGER NOT NULL,
    Fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    Diagnostico TEXT NOT NULL DEFAULT '',
    Tratamiento TEXT NOT NULL DEFAULT '',
    Observaciones TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (Id_cita) REFERENCES Cita(Id_cita) ON DELETE CASCADE
);

-- 12. Tabla: Receta (Prescripción de medicamentos e indicaciones por Historial_clinico)
CREATE TABLE IF NOT EXISTS Receta (
    Id_receta INTEGER PRIMARY KEY AUTOINCREMENT,
    Id_historial INTEGER NOT NULL,
    medicamento TEXT NOT NULL,
    Dosis TEXT NOT NULL,
    duracion_dias INTEGER NOT NULL,
    indicaciones TEXT NOT NULL,
    FOREIGN KEY (Id_historial) REFERENCES Historial_clinico(Id_historial) ON DELETE CASCADE
);

-- 13. Tabla: Factura (Comprobantes electrónicos Boleta/Factura de tienda y clínica)
CREATE TABLE IF NOT EXISTS Factura (
    id_factura INTEGER PRIMARY KEY AUTOINCREMENT,
    Id_cita INTEGER,
    id_dueno INTEGER,
    tipo TEXT NOT NULL DEFAULT 'Boleta',
    serie TEXT NOT NULL DEFAULT 'B001',
    numero INTEGER NOT NULL,
    numero_boleta TEXT NOT NULL UNIQUE,
    fecha_emision TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    cliente_nombre TEXT NOT NULL,
    cliente_documento TEXT NOT NULL,
    subtotal REAL NOT NULL,
    igv REAL NOT NULL,
    total REAL NOT NULL,
    metodo_pago TEXT NOT NULL DEFAULT 'Tarjeta / Yape',
    estado TEXT NOT NULL DEFAULT 'Pagado',
    pdf_url TEXT,
    UNIQUE (serie, numero),
    FOREIGN KEY (Id_cita) REFERENCES Cita(Id_cita) ON DELETE SET NULL,
    FOREIGN KEY (id_dueno) REFERENCES Dueno(id_dueno) ON DELETE SET NULL
);

-- 14. Tabla: Pago (Registro de transacciones de pago por Factura)
CREATE TABLE IF NOT EXISTS Pago (
    id_pago INTEGER PRIMARY KEY AUTOINCREMENT,
    id_factura INTEGER,
    metodo_pago TEXT NOT NULL,
    monto REAL NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'Pagado',
    fecha_pago TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    referencia TEXT,
    FOREIGN KEY (id_factura) REFERENCES Factura(id_factura) ON DELETE CASCADE
);

-- 15. Tabla: productos (Catálogo de tienda veterinaria y farmacia)
CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    categoria TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    precio REAL NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1
);

-- 16. Tabla: detalle_ventas (Ítems de productos vendidos por Factura)
CREATE TABLE IF NOT EXISTS detalle_ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_factura INTEGER NOT NULL,
    producto_id INTEGER NOT NULL,
    producto_nombre TEXT NOT NULL,
    cantidad INTEGER NOT NULL,
    precio_unitario REAL NOT NULL,
    subtotal REAL NOT NULL,
    FOREIGN KEY (id_factura) REFERENCES Factura(id_factura) ON DELETE CASCADE,
    FOREIGN KEY (producto_id) REFERENCES productos(id)
);

-- =============================================================================
-- DATOS SEMILLA DEMOSTRATIVOS DE LAS 16 TABLAS
-- =============================================================================

INSERT OR IGNORE INTO Especie (Id_especie, Nombre, Descripcion) VALUES
(1, 'Perro', 'Especie canina doméstica'),
(2, 'Gato', 'Especie felina doméstica'),
(3, 'Ave', 'Aves domésticas y ornamentales'),
(4, 'Conejo', 'Lagomorfos domésticos'),
(5, 'Otro', 'Otras especies de compañía');

INSERT OR IGNORE INTO Razas (Id_raza, Id_especie, nombre, Descripcion) VALUES
(1, 1, 'Golden Retriever', 'Raza canina mediana-grande de temperamento dócil'),
(2, 2, 'Siamés', 'Raza felina de pelaje corto y ojos azules'),
(3, 1, 'Mestizo', 'Canino sin clasificación racial específica'),
(4, 2, 'Mestizo', 'Felino sin clasificación racial específica');

INSERT OR IGNORE INTO Especialidad (Id_especialidad, Nombre, Descripcion) VALUES
(1, 'Medicina General e Interna', 'Diagnóstico clínico primario y medicina preventiva'),
(2, 'Dermatología y Cirugía Menor', 'Cuidado especializado de piel y tejidos blandos');

INSERT OR IGNORE INTO Servicios (Id_servicios, Nombre, Precio, Estado) VALUES
(1, 'Consulta general', 60.00, 'Activo'),
(2, 'Vacunación', 75.00, 'Activo'),
(3, 'Desparasitación', 45.00, 'Activo'),
(4, 'Control y seguimiento', 40.00, 'Activo');

INSERT OR IGNORE INTO productos (id, codigo, nombre, categoria, descripcion, precio, stock, activo) VALUES
(1, 'VET-001', 'Antipulgas Bravecto Chewable 10-20kg', 'Farmacia', 'Protección oral por 12 semanas contra pulgas y garrapatas.', 145.00, 25, 1),
(2, 'VET-002', 'Alimento Clínico Renal Canine 2kg', 'Nutrición', 'Dieta terapéutica de soporte renal e hidratación.', 89.50, 18, 1),
(3, 'VET-003', 'Shampoo Dermatológico Clorhexidina 250ml', 'Higiene', 'Fórmula hipoalergénica antiséptica para piel sensible.', 48.00, 30, 1),
(4, 'VET-004', 'Suplemento Omega 3 & Vitaminas Pelaje', 'Suplementos', '60 cápsulas blandas para articulaciones y brillo.', 65.00, 20, 1),
(5, 'VET-005', 'Collar Isabelino Ajustable Acolchado', 'Accesorios', 'Recuperación postoperatoria cómoda sin roce.', 35.00, 15, 1),
(6, 'VET-006', 'Kit Dental Enzimático Veterinario', 'Higiene', 'Pasta enzimática y cepillo suave de doble cabezal.', 42.00, 12, 1);
