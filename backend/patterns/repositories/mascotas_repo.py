"""Repositorio de Mascotas, Razas, Especies y Solicitudes de Cambio (dbo.Paciente, dbo.Razas, dbo.Especie)."""
from __future__ import annotations

from datetime import date
import json
from typing import Any, Dict, List, Optional

from ..sqlserver_schema import SQLServerConnection, sql_lit

_SELECT_PACIENTES_BASE = """
    SELECT {top_clause}
        p.id_paciente AS id,
        d.usuario_id,
        p.nombre,
        e.Nombre AS especie,
        r.nombre AS raza,
        CASE
            WHEN p.fecha_nacimiento > CAST(SYSDATETIME() AS DATE) THEN 0
            ELSE DATEDIFF(YEAR, p.fecha_nacimiento, SYSDATETIME())
                 - CASE
                       WHEN DATEADD(YEAR, DATEDIFF(YEAR, p.fecha_nacimiento, SYSDATETIME()), p.fecha_nacimiento) > CAST(SYSDATETIME() AS DATE)
                       THEN 1 ELSE 0
                   END
        END AS edad,
        CAST(p.peso_kg AS FLOAT) AS peso_kg,
        COALESCE(p.historial_resumen, '') AS historial_resumen,
        p.sexo,
        CONVERT(VARCHAR(10), p.fecha_nacimiento, 23) AS fecha_nacimiento,
        p.estado,
        CONVERT(VARCHAR(19), p.fecha_registro, 120) AS creado_en,
        COALESCE(u.nombre, LTRIM(RTRIM(d.nombres + ' ' + d.apellidos))) AS propietario_nombre
    FROM dbo.Paciente p
    JOIN dbo.Dueno d ON d.id_dueno = p.id_dueno
    JOIN dbo.Razas r ON r.Id_raza = p.Id_raza
    JOIN dbo.Especie e ON e.Id_especie = r.Id_especie
    LEFT JOIN dbo.usuarios u ON u.id = d.usuario_id
    WHERE {where_sql}
    {order_sql}
"""


class MascotasRepositoryMixin:
    """Operaciones SQL Server para pacientes (mascotas) y solicitudes de modificación/eliminación."""

    conn: SQLServerConnection

    # --- Resolución de especies/razas y CRUD de pacientes ---
    def _resolve_raza_id(self, especie: str, raza: str, descripcion: str) -> int:
        species = (especie or "Perro").strip() or "Perro"
        breed = (raza or "Mestizo").strip() or "Mestizo"
        sp = self.conn.query_one(
            f"SELECT TOP 1 Id_especie FROM dbo.Especie WHERE LOWER(Nombre) = LOWER({sql_lit(species)})"
        )
        if sp:
            species_id = int(sp["Id_especie"])
        else:
            species_id = int(
                self.conn.scalar(
                    f"""
                    INSERT INTO dbo.Especie (Nombre, Descripcion)
                    OUTPUT INSERTED.Id_especie
                    VALUES ({sql_lit(species)}, {sql_lit(descripcion)})
                    """
                )
            )
        rz = self.conn.query_one(
            f"SELECT TOP 1 Id_raza FROM dbo.Razas WHERE Id_especie = {species_id} AND LOWER(nombre) = LOWER({sql_lit(breed)})"
        )
        if rz:
            return int(rz["Id_raza"])
        return int(
            self.conn.scalar(
                f"""
                INSERT INTO dbo.Razas (Id_especie, nombre, Descripcion)
                OUTPUT INSERTED.Id_raza
                VALUES ({species_id}, {sql_lit(breed)}, {sql_lit(descripcion)})
                """
            )
        )

    def _mascota_row(self, mascota_id: int) -> Optional[Dict[str, Any]]:
        sql = _SELECT_PACIENTES_BASE.format(
            top_clause="TOP 1",
            where_sql=f"p.id_paciente = {int(mascota_id)}",
            order_sql="",
        )
        return self.conn.query_one(sql)

    def listar_mascotas(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        where_extra = f" AND d.usuario_id = {int(usuario_id)}" if usuario_id is not None else ""
        sql = _SELECT_PACIENTES_BASE.format(
            top_clause="",
            where_sql=f"p.estado <> 'Eliminado'{where_extra}",
            order_sql="ORDER BY p.id_paciente ASC",
        )
        return self.conn.query_json(sql)

    def crear_mascota(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        uid = int(datos["usuario_id"])
        owner_id = self._owner_id_for_user(uid)
        race_id = self._resolve_raza_id(
            str(datos.get("especie", "Perro")),
            str(datos.get("raza", "Mestizo")),
            "Registrada desde perfil de cliente",
        )
        age = max(0, int(datos.get("edad", 1)))
        birth = str(datos.get("fecha_nacimiento") or f"{max(1900, date.today().year - age):04d}-01-01")[:10]
        nombre = str(datos["nombre"]).strip()
        sexo = str(datos.get("sexo", "H")).strip()[:1].upper() or "H"
        peso = float(datos.get("peso_kg", 5.0))
        hist = str(datos.get("historial_resumen", "")).strip()
        pet_id = int(
            self.conn.scalar(
                f"""
                INSERT INTO dbo.Paciente (id_dueno, Id_raza, nombre, sexo, fecha_nacimiento, peso_kg, historial_resumen, estado)
                OUTPUT INSERTED.id_paciente
                VALUES ({owner_id}, {race_id}, {sql_lit(nombre)}, {sql_lit(sexo)}, {sql_lit(birth)}, {peso}, {sql_lit(hist)}, 'Activo')
                """
            )
        )
        return self._mascota_row(pet_id) or {"id": pet_id}

    def eliminar_mascota(self, mascota_id: int, usuario_id: Optional[int] = None) -> bool:
        if usuario_id is None:
            updated = self.conn.scalar(
                f"""
                UPDATE dbo.Paciente
                SET estado = 'Eliminado'
                OUTPUT INSERTED.id_paciente
                WHERE id_paciente = {int(mascota_id)} AND estado <> 'Eliminado'
                """
            )
        else:
            updated = self.conn.scalar(
                f"""
                UPDATE dbo.Paciente
                SET estado = 'Eliminado'
                OUTPUT INSERTED.id_paciente
                WHERE id_paciente = {int(mascota_id)}
                  AND id_dueno = (SELECT TOP 1 id_dueno FROM dbo.Dueno WHERE usuario_id = {int(usuario_id)})
                  AND estado <> 'Eliminado'
                """
            )
        return bool(updated.strip())

    # --- Flujo de solicitudes de edición/eliminación (Cliente -> Admin) ---
    def crear_solicitud_mascota(
        self,
        usuario_id: int,
        mascota_id: int,
        tipo: str,
        motivo: str,
        datos_nuevos: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        owner = self._owner_id_for_user(usuario_id, create=False)
        pet = self.conn.query_one(
            f"SELECT TOP 1 id_dueno, solicitud_estado FROM dbo.Paciente WHERE id_paciente = {int(mascota_id)}"
        )
        if not pet or int(pet["id_dueno"]) != int(owner or -1):
            raise LookupError("Mascota no encontrada para este usuario.")
        if pet.get("solicitud_estado") == "pendiente":
            raise ValueError("La mascota ya tiene una solicitud pendiente.")
        datos_json = json.dumps(datos_nuevos, ensure_ascii=False) if datos_nuevos else None
        self.conn.execute(
            f"""
            UPDATE dbo.Paciente
            SET solicitud_tipo = {sql_lit(tipo)},
                solicitud_datos_nuevos = {sql_lit(datos_json)},
                solicitud_motivo = {sql_lit(motivo.strip())},
                solicitud_estado = 'pendiente',
                solicitud_creado_en = SYSDATETIME()
            WHERE id_paciente = {int(mascota_id)}
            """
        )
        return next(
            item
            for item in self.listar_solicitudes_mascota(usuario_id)
            if int(item["id"]) == int(mascota_id)
        )

    def listar_solicitudes_mascota(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        where_extra = f" AND d.usuario_id = {int(usuario_id)}" if usuario_id is not None else ""
        result = self.conn.query_json(
            f"""
            SELECT
                p.id_paciente AS id,
                p.id_paciente AS mascota_id,
                d.usuario_id,
                p.solicitud_tipo AS tipo,
                p.solicitud_datos_nuevos AS datos_nuevos,
                p.solicitud_motivo AS motivo,
                p.solicitud_estado AS estado,
                CONVERT(VARCHAR(19), p.solicitud_creado_en, 120) AS creado_en,
                COALESCE(u.nombre, LTRIM(RTRIM(d.nombres + ' ' + d.apellidos))) AS propietario_nombre,
                COALESCE(u.email, '') AS propietario_email,
                p.nombre AS mascota_nombre,
                e.Nombre AS mascota_especie,
                r.nombre AS mascota_raza
            FROM dbo.Paciente p
            JOIN dbo.Dueno d ON d.id_dueno = p.id_dueno
            LEFT JOIN dbo.usuarios u ON u.id = d.usuario_id
            JOIN dbo.Razas r ON r.Id_raza = p.Id_raza
            JOIN dbo.Especie e ON e.Id_especie = r.Id_especie
            WHERE p.solicitud_tipo IS NOT NULL{where_extra}
            ORDER BY p.solicitud_creado_en DESC, p.id_paciente DESC
            """
        )
        for item in result:
            if item.get("datos_nuevos") and isinstance(item["datos_nuevos"], str):
                try:
                    item["datos_nuevos"] = json.loads(item["datos_nuevos"])
                except (ValueError, TypeError):
                    pass
        return result

    def resolver_solicitud_mascota(self, solicitud_id: int, accion: str) -> Dict[str, Any]:
        row = self.conn.query_one(
            f"SELECT TOP 1 * FROM dbo.Paciente WHERE id_paciente = {int(solicitud_id)} AND solicitud_tipo IS NOT NULL"
        )
        if not row:
            raise LookupError("Solicitud no encontrada.")
        if row.get("solicitud_estado") != "pendiente":
            raise ValueError("Esta solicitud ya fue resuelta previamente.")
        action = accion.lower().strip()
        if action not in ("aprobar", "rechazar"):
            raise ValueError("La accion debe ser 'aprobar' o 'rechazar'.")
        status = "aprobada" if action == "aprobar" else "rechazada"
        if action == "aprobar" and row.get("solicitud_tipo") == "eliminar":
            self.conn.execute(
                f"UPDATE dbo.Paciente SET estado = 'Eliminado' WHERE id_paciente = {int(solicitud_id)}"
            )
        elif action == "aprobar" and row.get("solicitud_tipo") == "editar" and row.get("solicitud_datos_nuevos"):
            new = (
                json.loads(row["solicitud_datos_nuevos"])
                if isinstance(row["solicitud_datos_nuevos"], str)
                else row["solicitud_datos_nuevos"]
            )
            if new.get("especie") or new.get("raza"):
                cur_rz = self.conn.query_one(
                    f"""
                    SELECT TOP 1 e.Nombre AS especie, r.nombre AS raza
                    FROM dbo.Razas r
                    JOIN dbo.Especie e ON e.Id_especie = r.Id_especie
                    WHERE r.Id_raza = {int(row['Id_raza'])}
                    """
                )
                sp_default = cur_rz["especie"] if cur_rz else "Perro"
                rz_default = cur_rz["raza"] if cur_rz else "Mestizo"
                race_id = self._resolve_raza_id(
                    str(new.get("especie") or sp_default),
                    str(new.get("raza") or rz_default),
                    "Registrada desde solicitud",
                )
            else:
                race_id = int(row["Id_raza"])
            birth_str = str(row.get("fecha_nacimiento") or "2023-05-10")[:10]
            current_age = max(0, date.today().year - int(birth_str[:4])) if birth_str[:4].isdigit() else 1
            raw_age = new.get("edad")
            age = max(0, int(raw_age if raw_age is not None else current_age))
            new_birth = f"{max(1900, date.today().year - age):04d}-01-01" if raw_age is not None else birth_str
            raw_peso = new.get("peso_kg")
            peso_final = float(raw_peso if raw_peso is not None else row.get("peso_kg") or 5.0)
            nuevo_nombre = str(new.get("nombre") or row["nombre"]).strip()
            nuevo_hist = (
                new.get("historial_resumen")
                if new.get("historial_resumen") is not None
                else (row.get("historial_resumen") or "")
            )
            self.conn.execute(
                f"""
                UPDATE dbo.Paciente
                SET Id_raza = {race_id},
                    nombre = {sql_lit(nuevo_nombre)},
                    fecha_nacimiento = {sql_lit(new_birth)},
                    peso_kg = {peso_final},
                    historial_resumen = {sql_lit(nuevo_hist)}
                WHERE id_paciente = {int(solicitud_id)}
                """
            )
        self.conn.execute(
            f"UPDATE dbo.Paciente SET solicitud_estado = {sql_lit(status)} WHERE id_paciente = {int(solicitud_id)}"
        )
        return next(
            item for item in self.listar_solicitudes_mascota() if int(item["id"]) == int(solicitud_id)
        )
