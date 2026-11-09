"""Canonical 3NF schema (16 tables, zero redundant columns, indexed FKs) for SQLite & SQL Server."""
from __future__ import annotations

import ctypes
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Callable, Optional

_SCHEMA_SQL_FILE = Path(__file__).resolve().parents[2] / "database" / "schema_sqlite.sql"
SQLITE_SCHEMA = "\n".join(
    line
    for line in _SCHEMA_SQL_FILE.read_text(encoding="utf-8").split("-- DATOS SEMILLA")[0].splitlines()
    if not line.strip().startswith("--")
)

TABLE_SYNC_SPECS: list[tuple[str, Optional[str], list[str]]] = [
    ("usuarios", "id", ["id", "nombre", "email", "password_hash", "rol", "estado", "telefono", "creado_en"]),
    ("Dueno", "id_dueno", ["id_dueno", "usuario_id", "dni", "tipo_documento", "nombres", "apellidos", "telefono", "fecha_registro"]),
    ("Especie", "Id_especie", ["Id_especie", "Nombre", "Descripcion"]),
    ("Razas", "Id_raza", ["Id_raza", "Id_especie", "nombre", "Descripcion"]),
    (
        "Paciente",
        "id_paciente",
        [
            "id_paciente", "id_dueno", "Id_raza", "nombre", "sexo", "fecha_nacimiento",
            "peso_kg", "historial_resumen", "estado", "fecha_registro", "solicitud_tipo",
            "solicitud_datos_nuevos", "solicitud_motivo", "solicitud_estado", "solicitud_creado_en",
        ],
    ),
    ("Especialidad", "Id_especialidad", ["Id_especialidad", "Nombre", "Descripcion"]),
    (
        "Veterinario",
        "Id_veterinario",
        ["Id_veterinario", "usuario_id", "Id_especialidad", "numero_colegiatura", "nombres", "Apellidos", "Telefono", "Fecha_contratacion"],
    ),
    ("Servicios", "Id_servicios", ["Id_servicios", "Nombre", "Precio", "Estado"]),
    ("Cita", "Id_cita", ["Id_cita", "Id_veterinario", "id_paciente", "fecha", "hora", "motivo", "estado", "whatsapp_url", "fecha_registro"]),
    ("Detalle_servicios", None, ["Id_cita", "Id_servicios", "precio_aplicado"]),
    ("Historial_clinico", "Id_historial", ["Id_historial", "Id_cita", "Fecha", "Diagnostico", "Tratamiento", "Observaciones"]),
    ("Receta", "Id_receta", ["Id_receta", "Id_historial", "medicamento", "Dosis", "duracion_dias", "indicaciones"]),
    (
        "Factura",
        "id_factura",
        ["id_factura", "Id_cita", "id_dueno", "tipo", "serie", "numero", "fecha_emision", "subtotal", "igv", "total", "estado", "pdf_url"],
    ),
    ("Pago", "id_pago", ["id_pago", "id_factura", "metodo_pago", "monto", "estado", "fecha_pago", "referencia"]),
    ("productos", "id", ["id", "codigo", "nombre", "categoria", "descripcion", "precio", "stock", "activo"]),
    ("detalle_ventas", "id", ["id", "id_factura", "producto_id", "cantidad", "precio_unitario", "subtotal"]),
]


def _sql_literal(val: Any) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, (int, float)):
        return str(val)
    text = str(val).replace("'", "''")
    return f"N'{text}'"


def _open_odbc_sqlserver(server: Optional[str] = None, database: Optional[str] = None) -> tuple[Any, Any, Any]:
    """Open an in-process Windows ODBC connection to local SQL Server (PatitasFelices_DB)."""
    if os.name != "nt" or os.getenv("DISABLE_SQLSERVER_SYNC") == "1":
        return None, None, None
    try:
        odbc = ctypes.windll.odbc32
        henv = ctypes.c_void_p()
        hdbc = ctypes.c_void_p()
        if odbc.SQLAllocHandle(1, None, ctypes.byref(henv)) not in (0, 1):
            return None, None, None
        odbc.SQLSetEnvAttr(henv, 200, 3, 0)
        if odbc.SQLAllocHandle(2, henv, ctypes.byref(hdbc)) not in (0, 1):
            odbc.SQLFreeHandle(1, henv)
            return None, None, None
        srv = (server or os.getenv("SQLSERVER_SERVER", "localhost")).strip()
        db_name = (database or os.getenv("SQLSERVER_DATABASE", "PatitasFelices_DB")).strip()
        driver = os.getenv("SQLSERVER_DRIVER", "ODBC Driver 17 for SQL Server")
        conn_str = f"Driver={{{driver}}};Server={srv};Database={db_name};Trusted_Connection=yes;"
        out_buf = ctypes.create_unicode_buffer(1024)
        out_len = ctypes.c_short()
        rc = odbc.SQLDriverConnectW(hdbc, None, conn_str, len(conn_str), out_buf, 1024, ctypes.byref(out_len), 0)
        if rc not in (0, 1):
            odbc.SQLFreeHandle(2, hdbc)
            odbc.SQLFreeHandle(1, henv)
            return None, None, None
        return odbc, henv, hdbc
    except Exception:
        return None, None, None


def _close_odbc_sqlserver(odbc: Any, henv: Any, hdbc: Any) -> None:
    if not odbc:
        return
    try:
        odbc.SQLDisconnect(hdbc)
        odbc.SQLFreeHandle(2, hdbc)
        odbc.SQLFreeHandle(1, henv)
    except Exception:
        pass


def _exec_odbc_scalar(odbc: Any, hdbc: Any, sql: str) -> str:
    hstmt = ctypes.c_void_p()
    odbc.SQLAllocHandle(3, hdbc, ctypes.byref(hstmt))
    try:
        rc = odbc.SQLExecDirectW(hstmt, sql, len(sql))
        if rc not in (0, 1):
            return ""
        chunks: list[str] = []
        while odbc.SQLFetch(hstmt) in (0, 1):
            buf = ctypes.create_unicode_buffer(65536)
            ind = ctypes.c_ssize_t()
            rc_data = odbc.SQLGetData(hstmt, 1, -8, buf, 65536 * 2, ctypes.byref(ind))
            if rc_data in (0, 1) and ind.value > 0:
                chunks.append(buf.value)
        return "".join(chunks)
    finally:
        odbc.SQLFreeHandle(3, hstmt)


def pull_from_sqlserver(
    conn: sqlite3.Connection,
    db_path: str,
    server: Optional[str] = None,
    database: Optional[str] = None,
) -> bool:
    """Restore any registered users and records from SQL Server (PatitasFelices_DB) into SQLite."""
    if db_path == ":memory:":
        return False
    odbc, henv, hdbc = _open_odbc_sqlserver(server=server, database=database)
    if not odbc:
        return False
    prev_fk = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = OFF")
        for table, pk, cols in TABLE_SYNC_SPECS:
            raw_json = _exec_odbc_scalar(
                odbc,
                hdbc,
                f"SELECT (SELECT {', '.join(cols)} FROM dbo.{table} FOR JSON PATH, INCLUDE_NULL_VALUES) AS j",
            )
            if not raw_json:
                continue
            rows = json.loads(raw_json)
            if not isinstance(rows, list):
                continue
            placeholders = ",".join("?" for _ in cols)
            col_list = ",".join(cols)
            for row in rows:
                values = [1 if val is True else (0 if val is False else val) for val in (row.get(c) for c in cols)]
                cur.execute(
                    f"INSERT OR IGNORE INTO {table} ({col_list}) VALUES ({placeholders})",
                    tuple(values),
                )
                if pk and row.get(pk) is not None and table == "usuarios":
                    cur.execute(
                        "UPDATE usuarios SET nombre=?, password_hash=?, rol=?, estado=?, telefono=? WHERE id=?",
                        (
                            row.get("nombre"),
                            row.get("password_hash"),
                            row.get("rol"),
                            row.get("estado"),
                            row.get("telefono") or "",
                            row.get("id"),
                        ),
                    )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.execute(f"PRAGMA foreign_keys = {'ON' if prev_fk else 'OFF'}")
        _close_odbc_sqlserver(odbc, henv, hdbc)


def push_to_sqlserver(
    conn: sqlite3.Connection,
    db_path: str,
    server: Optional[str] = None,
    database: Optional[str] = None,
) -> bool:
    """Synchronize all 16 normalized tables from runtime into SQL Server (PatitasFelices_DB)."""
    if db_path == ":memory:":
        return False
    odbc, henv, hdbc = _open_odbc_sqlserver(server=server, database=database)
    if not odbc:
        return False
    try:
        statements: list[str] = ["SET ANSI_NULLS ON;", "SET QUOTED_IDENTIFIER ON;"]
        for table, pk, cols in TABLE_SYNC_SPECS:
            rows = conn.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
            if not rows:
                continue
            if pk:
                statements.append(f"SET IDENTITY_INSERT dbo.{table} ON;")
            for r in rows:
                row_dict = dict(r)
                ins_cols = ", ".join(cols)
                ins_vals = ", ".join(_sql_literal(row_dict[c]) for c in cols)
                if pk:
                    pk_val = _sql_literal(row_dict[pk])
                    update_cols = [c for c in cols if c != pk]
                    set_clause = ", ".join(f"{c} = {_sql_literal(row_dict[c])}" for c in update_cols)
                    if table == "usuarios":
                        cond = f"{pk} = {pk_val} OR LOWER(email) = LOWER({_sql_literal(row_dict['email'])})"
                    elif table == "Dueno":
                        cond = f"{pk} = {pk_val} OR dni = {_sql_literal(row_dict['dni'])}"
                    elif table == "Veterinario":
                        cond = f"{pk} = {pk_val} OR LOWER(numero_colegiatura) = LOWER({_sql_literal(row_dict['numero_colegiatura'])})"
                    else:
                        cond = f"{pk} = {pk_val}"
                    statements.append(
                        f"IF EXISTS (SELECT 1 FROM dbo.{table} WHERE {cond}) "
                        f"UPDATE dbo.{table} SET {set_clause} WHERE {cond}; "
                        f"ELSE INSERT INTO dbo.{table} ({ins_cols}) VALUES ({ins_vals});"
                    )
                else:
                    c1, c2, c3 = cols[0], cols[1], cols[2]
                    v1, v2, v3 = _sql_literal(row_dict[c1]), _sql_literal(row_dict[c2]), _sql_literal(row_dict[c3])
                    statements.append(
                        f"IF EXISTS (SELECT 1 FROM dbo.{table} WHERE {c1} = {v1} AND {c2} = {v2}) "
                        f"UPDATE dbo.{table} SET {c3} = {v3} WHERE {c1} = {v1} AND {c2} = {v2}; "
                        f"ELSE INSERT INTO dbo.{table} ({ins_cols}) VALUES ({ins_vals});"
                    )
            if pk:
                statements.append(f"SET IDENTITY_INSERT dbo.{table} OFF;")
        if len(statements) > 2:
            batch_sql = "\n".join(statements)
            hstmt = ctypes.c_void_p()
            odbc.SQLAllocHandle(3, hdbc, ctypes.byref(hstmt))
            try:
                rc = odbc.SQLExecDirectW(hstmt, batch_sql, len(batch_sql))
                return rc in (0, 1)
            finally:
                odbc.SQLFreeHandle(3, hstmt)
        return True
    except Exception:
        return False
    finally:
        _close_odbc_sqlserver(odbc, henv, hdbc)


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
        cur.executemany(
            "INSERT INTO usuarios (nombre,email,password_hash,rol,estado,telefono) VALUES (?,?,?,?,?,?)",
            [(n, e, hash_password(p), r, s, t) for n, e, p, r, s, t in users],
        )
    if cur.execute("SELECT COUNT(*) FROM Dueno").fetchone()[0] == 0:
        user = cur.execute("SELECT id FROM usuarios WHERE email='cliente@patitasfelices.pe'").fetchone()
        cur.executemany(
            "INSERT INTO Dueno (usuario_id,dni,tipo_documento,nombres,apellidos,telefono) VALUES (?,?,?,?,?,?)",
            [
                (user[0] if user else None, "74859632", "DNI", "Lucía", "Fernández", "912345678"),
                (None, "45896321", "DNI", "Jorge", "Ramírez", "987112233"),
            ],
        )
    if cur.execute("SELECT COUNT(*) FROM Especie").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO Especie (Nombre,Descripcion) VALUES (?,?)",
            [
                ("Perro", "Especie canina"),
                ("Gato", "Especie felina"),
                ("Ave", "Aves domésticas"),
                ("Conejo", "Lagomorfos domésticos"),
                ("Otro", "Otras especies"),
            ],
        )
    if cur.execute("SELECT COUNT(*) FROM Razas").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO Razas (Id_especie,nombre,Descripcion) VALUES (?,?,?)",
            [
                (1, "Golden Retriever", "Raza canina"),
                (2, "Siamés", "Raza felina"),
                (1, "Mestizo", "Sin clasificación específica"),
                (2, "Mestizo", "Sin clasificación específica"),
            ],
        )
    if cur.execute("SELECT COUNT(*) FROM Especialidad").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO Especialidad (Nombre,Descripcion) VALUES (?,?)",
            [
                ("Medicina General e Interna", "Diagnóstico clínico y prevención"),
                ("Dermatología y Cirugía Menor", "Atención de piel y tejidos"),
            ],
        )
    if cur.execute("SELECT COUNT(*) FROM Veterinario").fetchone()[0] == 0:
        doctor = cur.execute("SELECT id FROM usuarios WHERE email='doctor@patitasfelices.pe'").fetchone()
        admin_u = cur.execute("SELECT id FROM usuarios WHERE email='admin@patitasfelices.pe'").fetchone()
        cur.execute(
            "INSERT INTO Veterinario (usuario_id,Id_especialidad,numero_colegiatura,nombres,Apellidos,Telefono,Fecha_contratacion) VALUES (?,?,?,?,?,?,?)",
            (doctor[0] if doctor else None, 1, "CMVP-10452", "Carlos", "Mendoza", "987654321", "2024-01-15"),
        )
        cur.execute(
            "INSERT INTO Veterinario (usuario_id,Id_especialidad,numero_colegiatura,nombres,Apellidos,Telefono,Fecha_contratacion) VALUES (?,?,?,?,?,?,?)",
            (admin_u[0] if admin_u and not doctor else None, 2, "CMVP-11890", "Melany", "Díaz Marín", "990853697", "2023-08-01"),
        )
    if cur.execute("SELECT COUNT(*) FROM Servicios").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO Servicios (Nombre,Precio,Estado) VALUES (?,?,?)",
            [
                ("Consulta general", 60, "Activo"),
                ("Vacunación", 75, "Activo"),
                ("Desparasitación", 45, "Activo"),
                ("Control y seguimiento", 40, "Activo"),
            ],
        )
    if cur.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO productos (codigo,nombre,categoria,descripcion,precio,stock,activo) VALUES (?,?,?,?,?,?,?)",
            [
                ("VET-001", "Antipulgas Bravecto Chewable 10-20kg", "Farmacia", "Protección por 12 semanas contra pulgas y garrapatas.", 145, 25, 1),
                ("VET-002", "Alimento Clínico Renal Canine 2kg", "Nutrición", "Dieta terapéutica de soporte renal e hidratación.", 89.5, 18, 1),
                ("VET-003", "Shampoo Dermatológico Clorhexidina 250ml", "Higiene", "Fórmula hipoalergénica antiséptica para piel sensible.", 48, 30, 1),
                ("VET-004", "Suplemento Omega 3 & Vitaminas Pelaje", "Suplementos", "Cápsulas blandas para articulaciones y pelaje.", 65, 20, 1),
                ("VET-005", "Collar Isabelino Ajustable Acolchado", "Accesorios", "Recuperación postoperatoria cómoda.", 35, 15, 1),
                ("VET-006", "Kit Dental Enzimático Veterinario", "Higiene", "Pasta enzimática y cepillo veterinario.", 42, 12, 1),
            ],
        )
    if cur.execute("SELECT COUNT(*) FROM Paciente").fetchone()[0] == 0:
        owner = cur.execute("SELECT id_dueno FROM Dueno ORDER BY id_dueno LIMIT 1").fetchone()
        if owner:
            cur.executemany(
                "INSERT INTO Paciente (id_dueno,Id_raza,nombre,sexo,fecha_nacimiento,peso_kg,historial_resumen,estado) VALUES (?,?,?,?,?,?,?,?)",
                [
                    (owner[0], 1, "Luna", "H", "2023-03-15", 24.5, "Vacunación vigente.", "Activo"),
                    (owner[0], 2, "Michi", "M", "2024-06-10", 4.2, "Control preventivo al día.", "Activo"),
                ],
            )
    if cur.execute("SELECT COUNT(*) FROM Cita").fetchone()[0] == 0:
        vet = cur.execute("SELECT Id_veterinario FROM Veterinario ORDER BY Id_veterinario LIMIT 1").fetchone()
        pets = cur.execute("SELECT id_paciente FROM Paciente ORDER BY id_paciente LIMIT 2").fetchall()
        if vet and pets:
            cur.executemany(
                "INSERT INTO Cita (Id_veterinario,id_paciente,fecha,hora,motivo,estado) VALUES (?,?,?,?,?,?)",
                [
                    (vet[0], pets[0][0], "2026-10-30", "10:00", "Control general.", "confirmada"),
                    (vet[0], pets[1][0] if len(pets) > 1 else pets[0][0], "2026-10-31", "11:30", "Refuerzo de vacuna.", "pendiente"),
                ],
            )
            services = cur.execute("SELECT Id_servicios FROM Servicios ORDER BY Id_servicios LIMIT 2").fetchall()
            for cita_id, service in zip((1, 2), services):
                cur.execute(
                    "INSERT OR IGNORE INTO Detalle_servicios (Id_cita,Id_servicios,precio_aplicado) VALUES (?,?,?)",
                    (cita_id, service[0], 60 if cita_id == 1 else 75),
                )
    if cur.execute("SELECT COUNT(*) FROM Historial_clinico").fetchone()[0] == 0 and cur.execute("SELECT COUNT(*) FROM Cita").fetchone()[0]:
        cur.execute(
            "INSERT INTO Historial_clinico (Id_cita,Diagnostico,Tratamiento,Observaciones) VALUES (1,'Dermatitis leve controlada.','Baño medicado cada 7 días.','Paciente estable.')"
        )
    if cur.execute("SELECT COUNT(*) FROM Receta").fetchone()[0] == 0 and cur.execute("SELECT COUNT(*) FROM Historial_clinico").fetchone()[0]:
        hist = cur.execute("SELECT Id_historial FROM Historial_clinico ORDER BY Id_historial LIMIT 1").fetchone()
        cur.execute(
            "INSERT INTO Receta (Id_historial,medicamento,Dosis,duracion_dias,indicaciones) VALUES (?,?,?,?,?)",
            (hist[0], "Shampoo Dermatológico Clorhexidina 250ml", "Aplicación tópica", 21, "Secar con toalla limpia."),
        )
    if cur.execute("SELECT COUNT(*) FROM Factura").fetchone()[0] == 0:
        owner = cur.execute("SELECT id_dueno FROM Dueno ORDER BY id_dueno LIMIT 1").fetchone()
        cita = cur.execute("SELECT Id_cita FROM Cita ORDER BY Id_cita LIMIT 1").fetchone()
        if owner:
            cur.execute(
                "INSERT INTO Factura (Id_cita,id_dueno,tipo,serie,numero,subtotal,igv,total,estado) VALUES (?,?,?,?,?,?,?,?,?)",
                (cita[0] if cita else None, owner[0], "Factura", "F001", 1, 50.85, 9.15, 60.0, "Pagado"),
            )
            invoice = cur.lastrowid
            cur.execute("INSERT INTO Pago (id_factura,metodo_pago,monto,estado) VALUES (?,?,?,'Pagado')", (invoice, "Yape", 60.0))
    if cur.execute("SELECT COUNT(*) FROM detalle_ventas").fetchone()[0] == 0:
        inv = cur.execute("SELECT id_factura FROM Factura ORDER BY id_factura LIMIT 1").fetchone()
        prod = cur.execute("SELECT id, precio FROM productos WHERE codigo='VET-003' OR id=3 LIMIT 1").fetchone()
        if inv and prod:
            cur.execute(
                "INSERT INTO detalle_ventas (id_factura,producto_id,cantidad,precio_unitario,subtotal) VALUES (?,?,?,?,?)",
                (inv[0], prod[0], 1, float(prod[1]), float(prod[1])),
            )


def _copy_legacy_table(
    cur: sqlite3.Cursor,
    table: str,
    cols: list[str],
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    today_iso = date.today().isoformat()
    placeholders = ",".join("?" for _ in cols)
    col_sql = ",".join(cols)
    seen_cita: set[int] = set()
    seen_num: set[tuple[str, int]] = set()
    for row in rows:
        r = dict(row)
        if table == "Factura":
            cid = r.get("Id_cita")
            if cid is not None and int(cid) in seen_cita:
                r["Id_cita"] = None
            elif cid is not None:
                seen_cita.add(int(cid))
            serie = str(r.get("serie") or "B001")
            num = int(r.get("numero") or r.get("id_factura") or 1)
            while (serie, num) in seen_num:
                num += 1
            seen_num.add((serie, num))
            r["serie"], r["numero"] = serie, num
        elif table == "Pago" and r.get("id_factura") is None:
            continue
        elif table == "Cita":
            r["hora"] = str(r.get("hora") or "09:00")[:5]
            r["estado"] = str(r.get("estado") or "pendiente").lower()
        defaults: dict[str, Any] = {
            "rol": "cliente", "estado": "Activo" if table != "usuarios" else "activo",
            "telefono": "", "Telefono": "", "creado_en": today_iso, "fecha_registro": today_iso,
            "Fecha_contratacion": today_iso, "Fecha": today_iso, "fecha_emision": today_iso,
            "fecha_pago": today_iso, "fecha_nacimiento": "2023-05-10", "tipo_documento": "DNI",
            "nombres": "Cliente", "apellidos": "", "Apellidos": "", "Descripcion": "",
            "sexo": "H", "peso_kg": 5.0, "historial_resumen": "", "motivo": "", "whatsapp_url": "",
            "Diagnostico": "", "Tratamiento": "", "Observaciones": "", "tipo": "Boleta",
            "metodo_pago": "Yape", "activo": 1, "Id_especie": 1, "Id_especialidad": 1,
        }
        vals = [r.get(c) if r.get(c) is not None else defaults.get(c) for c in cols]
        cur.execute(f"INSERT OR IGNORE INTO {table} ({col_sql}) VALUES ({placeholders})", tuple(vals))


def migrate_sqlite_schema(
    conn: sqlite3.Connection,
    db_path: str,
    hash_password: Callable[[str], str],
    server: Optional[str] = None,
    database: Optional[str] = None,
) -> None:
    """Ensure the canonical 3NF 16-table schema is in place while preserving existing user data."""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    old_names = [
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    ]
    expected_names = {t for t, _, _ in TABLE_SYNC_SPECS}
    if set(old_names) == expected_names:
        forbidden = {
            "Cita": "propietario", "Factura": "cliente_nombre", "detalle_ventas": "producto_nombre",
            "Paciente": "edad", "usuarios": "documento", "Dueno": "correo", "Veterinario": "correo",
        }
        if all(col not in {r[1] for r in conn.execute(f'PRAGMA table_info("{tbl}")')} for tbl, col in forbidden.items()):
            pull_from_sqlserver(conn, db_path, server=server, database=database)
            seed_sqlite(conn, db_path, hash_password)
            conn.commit()
            push_to_sqlserver(conn, db_path, server=server, database=database)
            conn.execute("PRAGMA foreign_keys = ON")
            return

    legacy = {name: [dict(r) for r in conn.execute(f'SELECT * FROM "{name}"')] for name in old_names}
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        for name in old_names:
            cur.execute(f'ALTER TABLE "{name}" RENAME TO "__legacy_{name}"')
        for statement in SQLITE_SCHEMA.split(";"):
            if statement.strip():
                cur.execute(statement)

        for table, _, cols in TABLE_SYNC_SPECS:
            _copy_legacy_table(cur, table, cols, legacy.get(table, []))

        existing_dueno_uids = {int(r[0]) for r in cur.execute("SELECT usuario_id FROM Dueno WHERE usuario_id IS NOT NULL")}
        for u in legacy.get("usuarios", []):
            uid = int(u["id"])
            if uid not in existing_dueno_uids and (u.get("rol") == "cliente" or u.get("documento")):
                parts = str(u.get("nombre") or "Cliente").strip().split(" ", 1)
                cur.execute(
                    "INSERT OR IGNORE INTO Dueno (usuario_id,dni,tipo_documento,nombres,apellidos,telefono) VALUES (?,?,?,?,?,?)",
                    (uid, u.get("documento") or f"CLI{uid:05d}", u.get("tipo_documento") or "DNI", parts[0], parts[1] if len(parts) > 1 else "", u.get("telefono") or ""),
                )

        pull_from_sqlserver(conn, db_path, server=server, database=database)
        cur.execute("PRAGMA foreign_keys = OFF")
        seed_sqlite(conn, db_path, hash_password)
        for name in old_names:
            cur.execute(f'DROP TABLE "__legacy_{name}"')
        conn.commit()
        push_to_sqlserver(conn, db_path, server=server, database=database)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
