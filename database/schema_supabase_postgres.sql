-- =============================================================================
-- CLÍNICA VETERINARIA PATITAS FELICES - ESQUEMA SUPABASE (POSTGRESQL)
-- Tablas clave con RLS abierto para API pública / anónima
-- =============================================================================

-- 1. Tabla: usuarios (con rol RBAC y estado activo/inactivo para el Patrón Proxy)
CREATE TABLE IF NOT EXISTS public.usuarios (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol VARCHAR(20) NOT NULL DEFAULT 'cliente' CHECK (rol IN ('cliente', 'doctor', 'admin')),
    estado VARCHAR(20) NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'inactivo')),
    telefono VARCHAR(20),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Tabla: mascotas
CREATE TABLE IF NOT EXISTS public.mascotas (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL REFERENCES public.usuarios(id) ON DELETE CASCADE,
    nombre VARCHAR(60) NOT NULL,
    especie VARCHAR(40) NOT NULL DEFAULT 'Perro',
    raza VARCHAR(60) NOT NULL DEFAULT 'Mestizo',
    edad INT NOT NULL DEFAULT 1,
    peso_kg NUMERIC(5,2) NOT NULL DEFAULT 5.00,
    historial_resumen VARCHAR(500),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Tabla: citas
CREATE TABLE IF NOT EXISTS public.citas (
    id SERIAL PRIMARY KEY,
    usuario_id INT REFERENCES public.usuarios(id) ON DELETE SET NULL,
    mascota_id INT REFERENCES public.mascotas(id) ON DELETE SET NULL,
    doctor_id INT REFERENCES public.usuarios(id) ON DELETE SET NULL,
    propietario VARCHAR(80) NOT NULL,
    telefono VARCHAR(20) NOT NULL,
    mascota_nombre VARCHAR(60) NOT NULL,
    servicio VARCHAR(50) NOT NULL,
    fecha DATE NOT NULL,
    hora TIME NOT NULL,
    motivo VARCHAR(1000) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'confirmada', 'atendida', 'cancelada')),
    diagnostico VARCHAR(500),
    tratamiento VARCHAR(500),
    whatsapp_url VARCHAR(600),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Tabla: productos
CREATE TABLE IF NOT EXISTS public.productos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(30) NOT NULL UNIQUE,
    nombre VARCHAR(120) NOT NULL,
    categoria VARCHAR(60) NOT NULL,
    descripcion VARCHAR(300) NOT NULL,
    precio NUMERIC(10,2) NOT NULL,
    stock INT NOT NULL DEFAULT 0,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- 5. Tabla: ventas
CREATE TABLE IF NOT EXISTS public.ventas (
    id SERIAL PRIMARY KEY,
    numero_boleta VARCHAR(30) NOT NULL UNIQUE,
    usuario_id INT NOT NULL REFERENCES public.usuarios(id),
    cliente_nombre VARCHAR(100) NOT NULL,
    cliente_documento VARCHAR(20) NOT NULL,
    subtotal NUMERIC(10,2) NOT NULL,
    igv NUMERIC(10,2) NOT NULL,
    total NUMERIC(10,2) NOT NULL,
    metodo_pago VARCHAR(40) NOT NULL DEFAULT 'Tarjeta / Yape',
    estado VARCHAR(30) NOT NULL DEFAULT 'pagado',
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. Tabla: detalle_ventas
CREATE TABLE IF NOT EXISTS public.detalle_ventas (
    id SERIAL PRIMARY KEY,
    venta_id INT NOT NULL REFERENCES public.ventas(id) ON DELETE CASCADE,
    producto_id INT NOT NULL REFERENCES public.productos(id),
    producto_nombre VARCHAR(120) NOT NULL,
    cantidad INT NOT NULL,
    precio_unitario NUMERIC(10,2) NOT NULL,
    subtotal NUMERIC(10,2) NOT NULL
);

-- =============================================================================
-- POLÍTICAS DE ACCESO (PERMITIR LECTURA Y ESCRITURA MEDIANTE API ANON/SERVICE)
-- =============================================================================
ALTER TABLE public.usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mascotas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.citas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.productos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ventas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.detalle_ventas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Acceso total usuarios" ON public.usuarios;
CREATE POLICY "Acceso total usuarios" ON public.usuarios FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Acceso total mascotas" ON public.mascotas;
CREATE POLICY "Acceso total mascotas" ON public.mascotas FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Acceso total citas" ON public.citas;
CREATE POLICY "Acceso total citas" ON public.citas FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Acceso total productos" ON public.productos;
CREATE POLICY "Acceso total productos" ON public.productos FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Acceso total ventas" ON public.ventas;
CREATE POLICY "Acceso total ventas" ON public.ventas FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Acceso total detalle_ventas" ON public.detalle_ventas;
CREATE POLICY "Acceso total detalle_ventas" ON public.detalle_ventas FOR ALL USING (true) WITH CHECK (true);

-- =============================================================================
-- DATOS SEMILLA (SEED DATA)
-- =============================================================================
INSERT INTO public.usuarios (nombre, email, password_hash, rol, estado, telefono) VALUES
('Dra. Melany Díaz (Admin)', 'admin@patitasfelices.pe', 'admin123', 'admin', 'activo', '990853697'),
('Dr. Carlos Mendoza (Veterinario)', 'doctor@patitasfelices.pe', 'doctor123', 'doctor', 'activo', '987654321'),
('Lucía Fernández (Cliente)', 'cliente@patitasfelices.pe', 'cliente123', 'cliente', 'activo', '912345678'),
('Usuario Suspendido (Prueba Proxy)', 'inactivo@patitasfelices.pe', 'inactivo123', 'cliente', 'inactivo', '900000000')
ON CONFLICT (email) DO NOTHING;

INSERT INTO public.productos (codigo, nombre, categoria, descripcion, precio, stock, activo) VALUES
('VET-001', 'Antipulgas Bravecto Chewable 10-20kg', 'Farmacia', 'Protección por 12 semanas contra pulgas y garrapatas.', 145.00, 25, TRUE),
('VET-002', 'Alimento Clínico Renal Canine 2kg', 'Nutrición', 'Dieta terapéutica de soporte renal e hidratación.', 89.50, 18, TRUE),
('VET-003', 'Shampoo Dermatológico Clorhexidina 250ml', 'Higiene', 'Fórmula hipoalergénica antiséptica para piel sensible.', 48.00, 30, TRUE),
('VET-004', 'Suplemento Omega 3 & Vitaminas Pelaje', 'Suplementos', '60 cápsulas blandas para articulaciones y brillo.', 65.00, 20, TRUE),
('VET-005', 'Collar Isabelino Ajustable Acolchado', 'Accesorios', 'Recuperación postoperatoria cómoda sin roce.', 35.00, 15, TRUE),
('VET-006', 'Kit Dental Enzimático Veterinario', 'Higiene', 'Pasta enzimática y cepillo suave de doble cabezal.', 42.00, 12, TRUE)
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO public.mascotas (usuario_id, nombre, especie, raza, edad, peso_kg, historial_resumen) VALUES
(3, 'Luna', 'Perro', 'Golden Retriever', 3, 24.50, 'Vacunación séxtuple al día. Buen estado general.'),
(3, 'Michi', 'Gato', 'Siamés', 2, 4.20, 'Control preventivo y desparasitación anual.')
ON CONFLICT DO NOTHING;

INSERT INTO public.citas (usuario_id, mascota_id, doctor_id, propietario, telefono, mascota_nombre, servicio, fecha, hora, motivo, estado, diagnostico, tratamiento) VALUES
(3, 1, 2, 'Lucía Fernández', '912345678', 'Luna', 'consulta-general', '2026-10-30', '10:00:00', 'Control general de peso y piel.', 'confirmada', 'Dermatitis leve en tratamiento.', 'Baño medicado cada 7 días.'),
(3, 2, 2, 'Lucía Fernández', '912345678', 'Michi', 'vacunacion', '2026-10-31', '11:30:00', 'Refuerzo de vacuna triple felina.', 'pendiente', '', '')
ON CONFLICT DO NOTHING;
