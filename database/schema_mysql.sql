-- =============================================================================
-- CLÍNICA VETERINARIA PATITAS FELICES - ESQUEMA MYSQL
-- Tablas clave: usuarios, mascotas, citas, productos, ventas, detalle_ventas
-- =============================================================================

CREATE DATABASE IF NOT EXISTS patitas_felices CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE patitas_felices;

-- 1. Tabla: usuarios (con rol RBAC y estado activo/inactivo para el Patrón Proxy)
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol ENUM('cliente', 'doctor', 'admin') NOT NULL DEFAULT 'cliente',
    estado ENUM('activo', 'inactivo') NOT NULL DEFAULT 'activo',
    telefono VARCHAR(20) NULL,
    creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. Tabla: mascotas (vinculada al propietario/cliente)
CREATE TABLE IF NOT EXISTS mascotas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    nombre VARCHAR(60) NOT NULL,
    especie VARCHAR(40) NOT NULL DEFAULT 'Perro',
    raza VARCHAR(60) NOT NULL DEFAULT 'Mestizo',
    edad INT NOT NULL DEFAULT 1,
    peso_kg DECIMAL(5,2) NOT NULL DEFAULT 5.00,
    historial_resumen VARCHAR(500) NULL,
    creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_mascotas_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 3. Tabla: citas (Agenda del Doctor y solicitudes de Clientes conectadas a WhatsApp Adapter)
CREATE TABLE IF NOT EXISTS citas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NULL,
    mascota_id INT NULL,
    doctor_id INT NULL,
    propietario VARCHAR(80) NOT NULL,
    telefono VARCHAR(20) NOT NULL,
    mascota_nombre VARCHAR(60) NOT NULL,
    servicio VARCHAR(50) NOT NULL,
    fecha DATE NOT NULL,
    hora TIME NOT NULL,
    motivo VARCHAR(1000) NOT NULL,
    estado ENUM('pendiente', 'confirmada', 'atendida', 'cancelada') NOT NULL DEFAULT 'pendiente',
    diagnostico VARCHAR(500) NULL,
    tratamiento VARCHAR(500) NULL,
    whatsapp_url VARCHAR(600) NULL,
    creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_citas_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
    CONSTRAINT fk_citas_mascota FOREIGN KEY (mascota_id) REFERENCES mascotas(id) ON DELETE SET NULL,
    CONSTRAINT fk_citas_doctor FOREIGN KEY (doctor_id) REFERENCES usuarios(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- 4. Tabla: productos (Catálogo de la Tienda Veterinaria y control de stock para TiendaFacade)
CREATE TABLE IF NOT EXISTS productos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(30) NOT NULL UNIQUE,
    nombre VARCHAR(120) NOT NULL,
    categoria VARCHAR(60) NOT NULL,
    descripcion VARCHAR(300) NOT NULL,
    precio DECIMAL(10,2) NOT NULL,
    stock INT NOT NULL DEFAULT 0,
    activo TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB;

-- 5. Tabla: ventas (Cabecera de Boleta y registro CRM generado por TiendaFacade)
CREATE TABLE IF NOT EXISTS ventas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    numero_boleta VARCHAR(30) NOT NULL UNIQUE,
    usuario_id INT NOT NULL,
    cliente_nombre VARCHAR(100) NOT NULL,
    cliente_documento VARCHAR(20) NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL,
    igv DECIMAL(10,2) NOT NULL,
    total DECIMAL(10,2) NOT NULL,
    metodo_pago VARCHAR(40) NOT NULL DEFAULT 'Tarjeta / Yape',
    estado VARCHAR(30) NOT NULL DEFAULT 'pagado',
    creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ventas_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;

-- 6. Tabla: detalle_ventas (Ítems de cada venta procesada por TiendaFacade)
CREATE TABLE IF NOT EXISTS detalle_ventas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    venta_id INT NOT NULL,
    producto_id INT NOT NULL,
    producto_nombre VARCHAR(120) NOT NULL,
    cantidad INT NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL,
    CONSTRAINT fk_detalle_venta FOREIGN KEY (venta_id) REFERENCES ventas(id) ON DELETE CASCADE,
    CONSTRAINT fk_detalle_producto FOREIGN KEY (producto_id) REFERENCES productos(id)
) ENGINE=InnoDB;

-- =============================================================================
-- DATOS SEMILLA (SEED DATA) PARA DEMOSTRACIÓN POR ROL
-- =============================================================================
INSERT INTO usuarios (nombre, email, password_hash, rol, estado, telefono) VALUES
('Dra. Melany Díaz (Admin)', 'admin@patitasfelices.pe', 'admin123', 'admin', 'activo', '990853697'),
('Dr. Carlos Mendoza (Veterinario)', 'doctor@patitasfelices.pe', 'doctor123', 'doctor', 'activo', '987654321'),
('Lucía Fernández (Cliente)', 'cliente@patitasfelices.pe', 'cliente123', 'cliente', 'activo', '912345678'),
('Usuario Suspendido (Prueba Proxy)', 'inactivo@patitasfelices.pe', 'inactivo123', 'cliente', 'inactivo', '900000000');

INSERT INTO mascotas (usuario_id, nombre, especie, raza, edad, peso_kg, historial_resumen) VALUES
(3, 'Luna', 'Perro', 'Golden Retriever', 3, 24.50, 'Vacunación séxtuple al día. Sin alergias conocidas.'),
(3, 'Michi', 'Gato', 'Siamés', 2, 4.20, 'Control preventivo anual completado.');

INSERT INTO productos (codigo, nombre, categoria, descripcion, precio, stock, activo) VALUES
('VET-001', 'Antipulgas Bravecto Chewable 10-20kg', 'Farmacia', 'Protección por 12 semanas contra pulgas y garrapatas.', 145.00, 25, 1),
('VET-002', 'Alimento Clínico Renal Canine 2kg', 'Nutrición', 'Fórmula veterinaria de soporte renal e hidratación.', 89.50, 18, 1),
('VET-003', 'Shampoo Dermatológico Clorhexidina 250ml', 'Higiene', 'Cuidado antiséptico hipoalergénico para piel sensible.', 48.00, 30, 1),
('VET-004', 'Suplemento Omega 3 & Vitaminas Pelaje', 'Suplementos', 'Cápsulas blandas para fortalecer articulaciones y pelaje.', 65.00, 20, 1),
('VET-005', 'Collar Isabelino Ajustable acolchado', 'Accesorios', 'Recuperación postoperatoria cómoda y segura.', 35.00, 15, 1),
('VET-006', 'Kit Dental Enzimático Veterinario', 'Higiene', 'Pasta enzimática y cepillo de doble cabezal.', 42.00, 12, 1);
