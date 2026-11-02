"""Canonical SQLite schema for the academic 16-table clinic model."""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, Callable

SQLITE_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS Especie (
    Id_especie INTEGER PRIMARY KEY AUTOINCREMENT,
    Nombre TEXT NOT NULL UNIQUE,
    Descripcion TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS Razas (
    Id_raza INTEGER PRIMARY KEY AUTOINCREMENT,
    Id_especie INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    Descripcion TEXT,
    UNIQUE (Id_especie, nombre),
    FOREIGN KEY (Id_especie) REFERENCES Especie(Id_especie)
);
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
CREATE TABLE IF NOT EXISTS Especialidad (
    Id_especialidad INTEGER PRIMARY KEY AUTOINCREMENT,
    Nombre TEXT NOT NULL UNIQUE,
    Descripcion TEXT NOT NULL
);
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
CREATE TABLE IF NOT EXISTS Servicios (
    Id_servicios INTEGER PRIMARY KEY AUTOINCREMENT,
    Nombre TEXT NOT NULL UNIQUE,
    Precio REAL NOT NULL,
    Estado TEXT NOT NULL DEFAULT 'Activo'
);
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
CREATE TABLE IF NOT EXISTS Detalle_servicios (
    Id_cita INTEGER NOT NULL,
    Id_servicios INTEGER NOT NULL,
    precio_aplicado REAL NOT NULL,
    PRIMARY KEY (Id_cita, Id_servicios),
    FOREIGN KEY (Id_cita) REFERENCES Cita(Id_cita) ON DELETE CASCADE,
    FOREIGN KEY (Id_servicios) REFERENCES Servicios(Id_servicios)
);
CREATE TABLE IF NOT EXISTS Historial_clinico (
    Id_historial INTEGER PRIMARY KEY AUTOINCREMENT,
    Id_cita INTEGER NOT NULL,
    Fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    Diagnostico TEXT NOT NULL DEFAULT '',
    Tratamiento TEXT NOT NULL DEFAULT '',
    Observaciones TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (Id_cita) REFERENCES Cita(Id_cita) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS Receta (
    Id_receta INTEGER PRIMARY KEY AUTOINCREMENT,
    Id_historial INTEGER NOT NULL,
    medicamento TEXT NOT NULL,
    Dosis TEXT NOT NULL,
    duracion_dias INTEGER NOT NULL,
    indicaciones TEXT NOT NULL,
    FOREIGN KEY (Id_historial) REFERENCES Historial_clinico(Id_historial) ON DELETE CASCADE
);
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
"""


def seed_sqlite(conn: sqlite3.Connection, db_path: str, hash_password: Callable[[str], str]) -> None:
    cur = conn.cursor()
    if cur.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
        users = [("Dra. Melany Díaz (Admin)", "admin@patitasfelices.pe", "admin123", "admin", "activo", "990853697")]
        if db_path == ":memory:":
            users.extend([
                ("Dr. Carlos Mendoza (Veterinario)", "doctor@patitasfelices.pe", "doctor123", "doctor", "activo", "987654321"),
                ("Lucía Fernández (Cliente)", "cliente@patitasfelices.pe", "cliente123", "cliente", "activo", "912345678"),
                ("Usuario Suspendido (Prueba Proxy)", "inactivo@patitasfelices.pe", "inactivo123", "cliente", "inactivo", "900000000"),
            ])
        cur.executemany("INSERT INTO usuarios (nombre,email,password_hash,rol,estado,telefono) VALUES (?,?,?,?,?,?)", [(n,e,hash_password(p),r,s,t) for n,e,p,r,s,t in users])
    if cur.execute("SELECT COUNT(*) FROM Dueno").fetchone()[0] == 0:
        user = cur.execute("SELECT id FROM usuarios WHERE email='cliente@patitasfelices.pe'").fetchone()
        cur.executemany("INSERT INTO Dueno (usuario_id,dni,tipo_documento,correo,nombres,apellidos,telefono) VALUES (?,?,?,?,?,?,?)", [
            (user[0] if user else None,"74859632","DNI","cliente@patitasfelices.pe","Lucía","Fernández","912345678"),
            (None,"45896321","DNI","jorge.ramirez@correo.pe","Jorge","Ramírez","987112233"),
        ])
    if cur.execute("SELECT COUNT(*) FROM Especie").fetchone()[0] == 0:
        cur.executemany("INSERT INTO Especie (Nombre,Descripcion) VALUES (?,?)", [("Perro","Especie canina"),("Gato","Especie felina"),("Ave","Aves domésticas"),("Conejo","Lagomorfos domésticos"),("Otro","Otras especies")])
    if cur.execute("SELECT COUNT(*) FROM Razas").fetchone()[0] == 0:
        cur.executemany("INSERT INTO Razas (Id_especie,nombre,Descripcion) VALUES (?,?,?)", [(1,"Golden Retriever","Raza canina"),(2,"Siamés","Raza felina"),(1,"Mestizo","Sin clasificación específica"),(2,"Mestizo","Sin clasificación específica")])
    if cur.execute("SELECT COUNT(*) FROM Especialidad").fetchone()[0] == 0:
        cur.executemany("INSERT INTO Especialidad (Nombre,Descripcion) VALUES (?,?)", [("Medicina General e Interna","Diagnóstico clínico y prevención"),("Dermatología y Cirugía Menor","Atención de piel y tejidos")])
    if cur.execute("SELECT COUNT(*) FROM Veterinario").fetchone()[0] == 0:
        doctor = cur.execute("SELECT id FROM usuarios WHERE email='doctor@patitasfelices.pe'").fetchone()
        cur.execute("INSERT INTO Veterinario (usuario_id,Id_especialidad,numero_colegiatura,nombres,Apellidos,Telefono,correo,Fecha_contratacion) VALUES (?,?,?,?,?,?,?,?)", (doctor[0] if doctor else None,1,"CMVP-10452","Carlos","Mendoza","987654321","doctor@patitasfelices.pe","2024-01-15"))
        cur.execute("INSERT INTO Veterinario (usuario_id,Id_especialidad,numero_colegiatura,nombres,Apellidos,Telefono,correo,Fecha_contratacion) VALUES (?,?,?,?,?,?,?,?)", (None,2,"CMVP-11890","Melany","Díaz Marín","990853697","admin@patitasfelices.pe","2023-08-01"))
    if cur.execute("SELECT COUNT(*) FROM Servicios").fetchone()[0] == 0:
        cur.executemany("INSERT INTO Servicios (Nombre,Precio,Estado) VALUES (?,?,?)", [("Consulta general",60,"Activo"),("Vacunación",75,"Activo"),("Desparasitación",45,"Activo"),("Control y seguimiento",40,"Activo")])
    if cur.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
        cur.executemany("INSERT INTO productos (codigo,nombre,categoria,descripcion,precio,stock,activo) VALUES (?,?,?,?,?,?,?)", [
            ("VET-001","Antipulgas Bravecto Chewable 10-20kg","Farmacia","Protección por 12 semanas contra pulgas y garrapatas.",145,25,1),
            ("VET-002","Alimento Clínico Renal Canine 2kg","Nutrición","Dieta terapéutica de soporte renal e hidratación.",89.5,18,1),
            ("VET-003","Shampoo Dermatológico Clorhexidina 250ml","Higiene","Fórmula hipoalergénica antiséptica para piel sensible.",48,30,1),
            ("VET-004","Suplemento Omega 3 & Vitaminas Pelaje","Suplementos","Cápsulas blandas para articulaciones y pelaje.",65,20,1),
            ("VET-005","Collar Isabelino Ajustable Acolchado","Accesorios","Recuperación postoperatoria cómoda.",35,15,1),
            ("VET-006","Kit Dental Enzimático Veterinario","Higiene","Pasta enzimática y cepillo veterinario.",42,12,1),
        ])
    if cur.execute("SELECT COUNT(*) FROM Paciente").fetchone()[0] == 0:
        owner = cur.execute("SELECT id_dueno FROM Dueno WHERE correo='cliente@patitasfelices.pe'").fetchone()
        if owner:
            cur.executemany("INSERT INTO Paciente (id_dueno,Id_raza,nombre,sexo,fecha_nacimiento,edad,peso_kg,historial_resumen,estado) VALUES (?,?,?,?,?,?,?,?,?)", [(owner[0],1,"Luna","H","2023-03-15",3,24.5,"Vacunación vigente.","Activo"),(owner[0],2,"Michi","M","2024-06-10",2,4.2,"Control preventivo al día.","Activo")])
    if cur.execute("SELECT COUNT(*) FROM Cita").fetchone()[0] == 0:
        vet = cur.execute("SELECT Id_veterinario FROM Veterinario ORDER BY Id_veterinario LIMIT 1").fetchone()
        pets = cur.execute("SELECT id_paciente,nombre FROM Paciente ORDER BY id_paciente LIMIT 2").fetchall()
        if vet and pets:
            cur.executemany("INSERT INTO Cita (Id_veterinario,id_paciente,fecha,hora,motivo,estado,propietario,telefono,mascota_nombre,servicio) VALUES (?,?,?,?,?,?,?,?,?,?)", [(vet[0],pets[0][0],"2026-10-30","10:00","Control general.","Confirmada","Lucía Fernández","912345678",pets[0][1],"consulta-general"),(vet[0],pets[1][0] if len(pets)>1 else pets[0][0],"2026-10-31","11:30","Refuerzo de vacuna.","Pendiente","Lucía Fernández","912345678",pets[1][1] if len(pets)>1 else pets[0][1],"vacunacion")])
            services = cur.execute("SELECT Id_servicios FROM Servicios ORDER BY Id_servicios LIMIT 2").fetchall()
            for cita_id, service in zip((1,2), services):
                cur.execute("INSERT OR IGNORE INTO Detalle_servicios (Id_cita,Id_servicios,precio_aplicado) VALUES (?,?,?)", (cita_id,service[0],60 if cita_id==1 else 75))
    if cur.execute("SELECT COUNT(*) FROM Historial_clinico").fetchone()[0] == 0 and cur.execute("SELECT COUNT(*) FROM Cita").fetchone()[0]:
        cur.execute("INSERT INTO Historial_clinico (Id_cita,Diagnostico,Tratamiento,Observaciones) VALUES (1,'Dermatitis leve controlada.','Baño medicado cada 7 días.','Paciente estable.')")
    if cur.execute("SELECT COUNT(*) FROM Receta").fetchone()[0] == 0 and cur.execute("SELECT COUNT(*) FROM Historial_clinico").fetchone()[0]:
        hist = cur.execute("SELECT Id_historial FROM Historial_clinico ORDER BY Id_historial LIMIT 1").fetchone()
        cur.execute("INSERT INTO Receta (Id_historial,medicamento,Dosis,duracion_dias,indicaciones) VALUES (?,?,?,?,?)", (hist[0],"Shampoo Dermatológico Clorhexidina 250ml","Aplicación tópica",21,"Secar con toalla limpia."))
    if cur.execute("SELECT COUNT(*) FROM Factura").fetchone()[0] == 0:
        owner = cur.execute("SELECT id_dueno FROM Dueno ORDER BY id_dueno LIMIT 1").fetchone()
        cita = cur.execute("SELECT Id_cita FROM Cita ORDER BY Id_cita LIMIT 1").fetchone()
        if owner:
            cur.execute("INSERT INTO Factura (Id_cita,id_dueno,tipo,serie,numero,numero_boleta,cliente_nombre,cliente_documento,subtotal,igv,total,metodo_pago,estado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (cita[0] if cita else None,owner[0],"Factura","F001",1,"F001-000001","Lucía Fernández","74859632",50.85,9.15,60,"Yape","Pagado"))
            invoice = cur.lastrowid
            cur.execute("INSERT INTO Pago (id_factura,metodo_pago,monto,estado) VALUES (?,?,?,'Pagado')", (invoice,"Yape",60))
    if cur.execute("SELECT COUNT(*) FROM detalle_ventas").fetchone()[0] == 0:
        inv = cur.execute("SELECT id_factura FROM Factura ORDER BY id_factura LIMIT 1").fetchone()
        prod = cur.execute("SELECT id, nombre, precio FROM productos WHERE codigo='VET-003' OR id=3 LIMIT 1").fetchone()
        if inv and prod:
            cur.execute("INSERT INTO detalle_ventas (id_factura,producto_id,producto_nombre,cantidad,precio_unitario,subtotal) VALUES (?,?,?,?,?,?)", (inv[0],prod[0],prod[1],1,float(prod[2]),float(prod[2])))


def migrate_sqlite_schema(conn: sqlite3.Connection, db_path: str, hash_password: Callable[[str], str]) -> None:
    """Rebuild the older mixed schema into the canonical 16 tables, retaining its data."""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    old_names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )]
    expected_names = {
        "Dueno", "Especie", "Razas", "Paciente", "Especialidad", "Veterinario",
        "Servicios", "Cita", "Detalle_servicios", "Historial_clinico", "Receta",
        "Factura", "Pago", "usuarios", "productos", "detalle_ventas",
    }
    if set(old_names) == expected_names:
        required_columns = {
            "Paciente": {"solicitud_tipo", "edad", "peso_kg"},
            "Dueno": {"usuario_id", "tipo_documento"},
            "Veterinario": {"usuario_id"},
            "Cita": {"hora", "whatsapp_url"},
            "Factura": {"numero_boleta", "total", "pdf_url"},
            "Pago": {"id_factura", "metodo_pago", "monto"},
            "detalle_ventas": {"id_factura", "producto_id"},
        }
        ready = all(
            columns.issubset({r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')})
            for table, columns in required_columns.items()
        )
        if ready:
            seed_sqlite(conn, db_path, hash_password)
            conn.commit()
            return
    legacy: dict[str, list[dict[str, Any]]] = {}
    for name in old_names:
        legacy[name] = [dict(r) for r in conn.execute(f' SELECT * FROM "{name}"')]

    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        for name in old_names:
            cur.execute(f'ALTER TABLE "{name}" RENAME TO "__legacy_{name}"')
        for statement in SQLITE_SCHEMA.split(";"):
            if statement.strip():
                cur.execute(statement)

        def rows(table: str) -> list[dict[str, Any]]:
            return legacy.get(table, [])

        def by_id(table: str, key: str) -> dict[int, dict[str, Any]]:
            return {int(r[key]): r for r in rows(table) if r.get(key) is not None}

        users = by_id("usuarios", "id")
        for u in rows("usuarios"):
            cur.execute(
                "INSERT INTO usuarios (id,nombre,email,password_hash,rol,estado,telefono,tipo_documento,documento,creado_en) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (u["id"],u["nombre"],u["email"],u["password_hash"],u.get("rol","cliente"),u.get("estado","activo"),u.get("telefono"),u.get("tipo_documento") or "DNI",u.get("documento"),u.get("creado_en") or u.get("fecha_registro")),
            )

        old_owners = by_id("Dueno", "id_dueno")
        owner_map: dict[int, int] = {}
        owner_by_user: dict[int, int] = {}
        user_by_email = {str(u["email"]).lower(): int(uid) for uid,u in users.items()}
        for owner in rows("Dueno"):
            uid = user_by_email.get(str(owner.get("correo", "")).lower())
            cur.execute(
                "INSERT INTO Dueno (id_dueno,usuario_id,dni,tipo_documento,correo,nombres,apellidos,telefono,fecha_registro) VALUES (?,?,?,?,?,?,?,?,?)",
                (owner["id_dueno"],uid,owner.get("dni") or f"CLI{owner['id_dueno']:05d}",owner.get("tipo_documento") or "DNI",owner.get("correo") or f"dueno{owner['id_dueno']}@local.invalid",owner.get("nombres") or "Cliente",owner.get("apellidos") or "",owner.get("telefono") or "",owner.get("fecha_registro")),
            )
            owner_map[int(owner["id_dueno"])] = int(owner["id_dueno"])
            if uid:
                owner_by_user[uid] = int(owner["id_dueno"])

        species_names: dict[str, int] = {}
        for s in rows("Especie"):
            name = str(s.get("Nombre") or "Otro")
            cur.execute("INSERT INTO Especie (Id_especie,Nombre,Descripcion) VALUES (?,?,?)", (s["Id_especie"],name,s.get("Descripcion") or ""))
            species_names[name.casefold()] = int(s["Id_especie"])
        def species_id(name: str) -> int:
            normalized = {"perro":"perro", "canino":"perro", "gato":"gato", "felino":"gato", "ave":"ave", "conejo":"conejo"}.get(name.strip().casefold(), name.strip().casefold())
            for existing, eid in species_names.items():
                key = {"canino":"perro", "felino":"gato"}.get(existing, existing)
                if key == normalized:
                    return eid
            cur.execute("INSERT INTO Especie (Nombre,Descripcion) VALUES (?,?)", (name.strip() or "Otro", "Migrado desde datos de mascotas"))
            eid = int(cur.lastrowid)
            species_names[(name.strip() or "Otro").casefold()] = eid
            return eid

        race_ids: dict[tuple[int,str], int] = {}
        for race in rows("Razas"):
            especie = int(race.get("Id_especie") or 1)
            name = str(race.get("nombre") or "Mestizo")
            cur.execute("INSERT INTO Razas (Id_raza,Id_especie,nombre,Descripcion) VALUES (?,?,?,?)", (race["Id_raza"],especie,name,race.get("Descripcion")))
            race_ids[(especie,name.casefold())] = int(race["Id_raza"])
        def race_id(species: str, name: str) -> int:
            eid = species_id(species)
            race_name = name.strip() or "Mestizo"
            found = race_ids.get((eid,race_name.casefold()))
            if found:
                return found
            cur.execute("INSERT INTO Razas (Id_especie,nombre,Descripcion) VALUES (?,?,?)", (eid,race_name,"Migrada desde el registro de la mascota"))
            rid = int(cur.lastrowid)
            race_ids[(eid,race_name.casefold())] = rid
            return rid

        for table, pk, columns in [
            ("Especialidad","Id_especialidad",("Nombre","Descripcion")),
            ("Servicios","Id_servicios",("Nombre","Precio","Estado")),
            ("productos","id",("codigo","nombre","categoria","descripcion","precio","stock","activo")),
        ]:
            for r in rows(table):
                values = [r.get(pk)] + [r.get(col) for col in columns]
                cur.execute(f'INSERT INTO "{table}" ({",".join([pk,*columns])}) VALUES ({",".join("?" for _ in values)})', values)

        for vet in rows("Veterinario"):
            uid = user_by_email.get(str(vet.get("correo", "")).lower())
            cur.execute("INSERT INTO Veterinario (Id_veterinario,usuario_id,Id_especialidad,numero_colegiatura,nombres,Apellidos,Telefono,correo,Fecha_contratacion) VALUES (?,?,?,?,?,?,?,?,?)", (vet["Id_veterinario"],uid,vet.get("Id_especialidad") or 1,vet.get("numero_colegiatura") or f"MIG-{vet['Id_veterinario']}",vet.get("nombres") or "Veterinario",vet.get("Apellidos") or "",vet.get("Telefono") or "",vet.get("correo") or f"vet{vet['Id_veterinario']}@local.invalid",vet.get("Fecha_contratacion") or date.today().isoformat()))

        patient_map: dict[int,int] = {}
        patients_by_owner_name: dict[tuple[int,str],int] = {}
        def add_patient(source: dict[str,Any], source_kind: str, fallback_owner: int | None = None) -> int:
            if source_kind == "Paciente":
                old_id = int(source["id_paciente"])
                owner_id = int(source.get("id_dueno") or fallback_owner or 0)
                rid = int(source.get("Id_raza") or race_id("Otro",source.get("raza","Mestizo")))
                species = next((k for k,v in race_ids.items() if v == rid), None)
                age = source.get("edad")
                if age is None:
                    birth = str(source.get("fecha_nacimiento") or "2023-01-01")[:10]
                    try: age = max(0, date.today().year-int(birth[:4]))
                    except (ValueError,IndexError): age = 1
                values = (old_id,owner_id,rid,source.get("nombre") or "Mascota",source.get("sexo") or "H",source.get("fecha_nacimiento") or "2023-01-01",int(age),float(source.get("peso_kg") or 5),source.get("historial_resumen"),source.get("estado") or "Activo",source.get("fecha_registro"),source.get("solicitud_tipo"),source.get("solicitud_datos_nuevos"),source.get("solicitud_motivo"),source.get("solicitud_estado"),source.get("solicitud_creado_en"))
                cur.execute("INSERT INTO Paciente (id_paciente,id_dueno,Id_raza,nombre,sexo,fecha_nacimiento,edad,peso_kg,historial_resumen,estado,fecha_registro,solicitud_tipo,solicitud_datos_nuevos,solicitud_motivo,solicitud_estado,solicitud_creado_en) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
                pid=old_id
            else:
                uid=int(source.get("usuario_id") or 0)
                owner_id=owner_by_user.get(uid, fallback_owner or 0)
                if not owner_id:
                    return 0
                name=str(source.get("nombre") or "Mascota")
                key=(owner_id,name.casefold())
                if key in patients_by_owner_name:
                    pid=patients_by_owner_name[key]
                    cur.execute("UPDATE Paciente SET edad=?,peso_kg=?,historial_resumen=? WHERE id_paciente=?", (int(source.get("edad") or 1),float(source.get("peso_kg") or 5),source.get("historial_resumen"),pid))
                    return pid
                rid=race_id(str(source.get("especie") or "Perro"),str(source.get("raza") or "Mestizo"))
                birth=f"{date.today().year-int(source.get('edad') or 1):04d}-01-01"
                cur.execute("INSERT INTO Paciente (id_dueno,Id_raza,nombre,sexo,fecha_nacimiento,edad,peso_kg,historial_resumen,estado,fecha_registro) VALUES (?,?,?,?,?,?,?,?,?,?)", (owner_id,rid,name,str(source.get("sexo") or "H")[:1].upper(),birth,int(source.get("edad") or 1),float(source.get("peso_kg") or 5),source.get("historial_resumen"),"Activo",source.get("creado_en")))
                pid=int(cur.lastrowid)
            patients_by_owner_name[(owner_id,str(source.get("nombre") or "").casefold())]=pid
            return pid
        for p in rows("Paciente"):
            pid=add_patient(p,"Paciente")
            patient_map[int(p["id_paciente"])]=pid
        pet_map: dict[int,int]={}
        for m in rows("mascotas"):
            uid=int(m.get("usuario_id") or 0)
            pid=add_patient(m,"mascotas")
            if pid: pet_map[int(m["id"])]=pid

        old_vets=by_id("Veterinario","Id_veterinario")
        def vet_for_user(uid: Any) -> int:
            if uid is not None:
                user=users.get(int(uid))
                if user:
                    found=cur.execute("SELECT Id_veterinario FROM Veterinario WHERE lower(correo)=lower(?)",(user.get("email"),)).fetchone()
                    if found:return int(found[0])
            found=cur.execute("SELECT Id_veterinario FROM Veterinario ORDER BY Id_veterinario LIMIT 1").fetchone()
            return int(found[0]) if found else 1
        cita_map: dict[int,int]={}
        for c in rows("Cita"):
            raw=str(c.get("fecha") or date.today().isoformat())
            fecha=raw[:10]; hora=str(c.get("hora") or (raw[11:16] if len(raw)>10 else "09:00"))[:5]
            pid=patient_map.get(int(c.get("id_paciente") or 0),int(c.get("id_paciente") or 0))
            cur.execute("INSERT INTO Cita (Id_cita,Id_veterinario,id_paciente,fecha,hora,motivo,estado,propietario,telefono,mascota_nombre,servicio) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (c["Id_cita"],c.get("Id_veterinario") or vet_for_user(None),pid,fecha,hora,c.get("motivo") or "",c.get("estado") or "Pendiente","","","",""))
            cita_map[int(c["Id_cita"])]=int(c["Id_cita"])
        service_alias={"consulta-general":"Consulta general","vacunacion":"Vacunación","desparasitacion":"Desparasitación","control":"Control y seguimiento"}
        for c in rows("citas"):
            uid=int(c.get("usuario_id") or 0)
            pid=pet_map.get(int(c.get("mascota_id") or 0))
            if pid is None:
                owner=owner_by_user.get(uid)
                if owner:
                    pid=next((p_id for (o_id,_),p_id in patients_by_owner_name.items() if o_id==owner),None)
            fecha=str(c.get("fecha") or date.today().isoformat())[:10]
            servicio=service_alias.get(str(c.get("servicio") or "").casefold(),str(c.get("servicio") or ""))
            service=cur.execute("SELECT Id_servicios FROM Servicios WHERE lower(Nombre)=lower(?) LIMIT 1",(servicio,)).fetchone()
            servicio_id=int(service[0]) if service else (int(cur.execute("SELECT Id_servicios FROM Servicios ORDER BY Id_servicios LIMIT 1").fetchone()[0]) if rows("Servicios") else None)
            vet_id=vet_for_user(c.get("doctor_id"))
            cur.execute("INSERT INTO Cita (Id_veterinario,id_paciente,fecha,hora,motivo,estado,propietario,telefono,mascota_nombre,servicio,whatsapp_url) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (vet_id,pid,fecha,str(c.get("hora") or "09:00")[:5],c.get("motivo") or "",c.get("estado") or "Pendiente",c.get("propietario") or "",c.get("telefono") or "",c.get("mascota_nombre") or "",str(c.get("servicio") or ""),c.get("whatsapp_url") or ""))
            new_cita=int(cur.lastrowid)
            cita_map[int(c["id"])]=new_cita
            if servicio_id:
                price=cur.execute("SELECT Precio FROM Servicios WHERE Id_servicios=?",(servicio_id,)).fetchone()[0]
                cur.execute("INSERT OR IGNORE INTO Detalle_servicios (Id_cita,Id_servicios,precio_aplicado) VALUES (?,?,?)",(new_cita,servicio_id,price))
            if c.get("diagnostico") or c.get("tratamiento"):
                cur.execute("INSERT INTO Historial_clinico (Id_cita,Diagnostico,Tratamiento,Observaciones) VALUES (?,?,?,?)",(new_cita,c.get("diagnostico") or "",c.get("tratamiento") or "",""))
        for d in rows("Detalle_servicios"):
            cita_id=cita_map.get(int(d.get("Id_cita") or 0),int(d.get("Id_cita") or 0))
            cur.execute("INSERT OR IGNORE INTO Detalle_servicios (Id_cita,Id_servicios,precio_aplicado) VALUES (?,?,?)",(cita_id,d.get("Id_servicios"),d.get("precio_aplicado") or 0))
        for h in rows("Historial_clinico"):
            cita_id=cita_map.get(int(h.get("Id_cita") or 0),int(h.get("Id_cita") or 0))
            cur.execute("INSERT INTO Historial_clinico (Id_historial,Id_cita,Fecha,Diagnostico,Tratamiento,Observaciones) VALUES (?,?,?,?,?,?)",(h["Id_historial"],cita_id,h.get("Fecha"),h.get("Diagnostico") or "",h.get("Tratamiento") or "",h.get("Observaciones") or ""))
        for rec in rows("Receta"):
            cur.execute("INSERT INTO Receta (Id_receta,Id_historial,medicamento,Dosis,duracion_dias,indicaciones) VALUES (?,?,?,?,?,?)",(rec["Id_receta"],rec.get("Id_historial"),rec.get("medicamento") or "",rec.get("Dosis") or "",int(rec.get("duracion_dias") or 1),rec.get("indicaciones") or ""))

        invoice_map: dict[int,int]={}; used_numbers: dict[str,set[int]]={}
        def add_invoice(v: dict[str,Any], kind: str) -> int:
            if kind=="Factura":
                serie=str(v.get("serie") or "B001"); numero=int(v.get("numero") or 1)
                owner_id=v.get("id_dueno")
                cita_id=cita_map.get(int(v.get("Id_cita") or 0)) if v.get("Id_cita") else None
                subtotal=float(v.get("subtotal") or 0); igv=float(v.get("igv") or 0)
                total=subtotal+igv; tipo=str(v.get("tipo") or "Boleta"); created=v.get("fecha_emision")
                pdf=v.get("xml_url")
                owner=old_owners.get(int(owner_id or 0),{})
                cliente= f"{owner.get('nombres','')} {owner.get('apellidos','')}".strip() or "Cliente"
                doc=str(owner.get("dni") or "")
                old_id=v.get("id_factura")
            else:
                old_number=str(v.get("numero_boleta") or "B001-000001")
                serie,_,suffix=old_number.partition("-"); serie=serie or "B001"
                numero=int(suffix or "1")
                while numero in used_numbers.setdefault(serie,set()): numero+=1
                uid=int(v.get("usuario_id") or 0); owner_id=owner_by_user.get(uid)
                cita_id=None; subtotal=float(v.get("subtotal") or 0); igv=float(v.get("igv") or 0); total=float(v.get("total") or subtotal+igv)
                tipo="Boleta"; created=v.get("creado_en"); pdf=None; cliente=str(v.get("cliente_nombre") or "Cliente"); doc=str(v.get("cliente_documento") or ""); old_id=v.get("id")
            if numero in used_numbers.setdefault(serie,set()):
                numero=max(used_numbers[serie] or {0})+1
            used_numbers[serie].add(numero)
            display=f"{serie}-{numero:06d}"
            cur.execute("INSERT INTO Factura (Id_cita,id_dueno,tipo,serie,numero,numero_boleta,fecha_emision,cliente_nombre,cliente_documento,subtotal,igv,total,metodo_pago,estado,pdf_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(cita_id,owner_id,tipo,serie,numero,display,created or date.today().isoformat(),cliente,doc,subtotal,igv,total,str(v.get("metodo_pago") or "Tarjeta / Yape"),str(v.get("estado") or "Pagado"),pdf))
            return int(cur.lastrowid)
        for v in rows("Factura"):
            invoice_map[int(v["id_factura"])]=add_invoice(v,"Factura")
        sale_map: dict[int,int]={}
        for v in rows("ventas"):
            sale_map[int(v["id"])]=add_invoice(v,"ventas")
        for d in rows("detalle_ventas"):
            inv_id=sale_map.get(int(d.get("venta_id") or 0))
            if inv_id:
                cur.execute("INSERT INTO detalle_ventas (id_factura,producto_id,producto_nombre,cantidad,precio_unitario,subtotal) VALUES (?,?,?,?,?,?)",(inv_id,d.get("producto_id"),d.get("producto_nombre") or "Producto",int(d.get("cantidad") or 1),float(d.get("precio_unitario") or 0),float(d.get("subtotal") or 0)))
        for pay in rows("Pago"):
            service_id=pay.get("Id_servicios")
            cita=cur.execute("SELECT Id_cita FROM Detalle_servicios WHERE Id_servicios=? ORDER BY Id_cita LIMIT 1",(service_id,)).fetchone() if service_id else None
            invoice=cur.execute("SELECT id_factura,total,metodo_pago FROM Factura WHERE Id_cita=? ORDER BY id_factura LIMIT 1",(cita[0],)).fetchone() if cita else None
            desc=str(pay.get("descripcioon") or "")
            method=next((m for m in ("Yape","Efectivo","Tarjeta","Transferencia") if m.casefold() in desc.casefold()), "Migrado")
            cur.execute("INSERT INTO Pago (id_factura,metodo_pago,monto,estado,referencia) VALUES (?,?,?,?,?)",(invoice[0] if invoice else None,method,float(invoice[1]) if invoice else 0,"Pagado",desc or f"Cantidad histórica: {pay.get('cantidad',1)}"))

        solicitudes = rows("solicitudes_mascota")
        for s in solicitudes:
            pid=pet_map.get(int(s.get("mascota_id") or 0))
            if pid:
                cur.execute("UPDATE Paciente SET solicitud_tipo=?,solicitud_datos_nuevos=?,solicitud_motivo=?,solicitud_estado=?,solicitud_creado_en=? WHERE id_paciente=?",(s.get("tipo"),s.get("datos_nuevos"),s.get("motivo"),s.get("estado"),s.get("creado_en"),pid))

        seed_sqlite(conn, db_path, hash_password)
        for name in old_names:
            cur.execute(f'DROP TABLE "__legacy_{name}"')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
