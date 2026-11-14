"""Repositorio de Citas Médicas, Disponibilidad e Historial Clínico (dbo.Cita, dbo.Historial_clinico)."""
from __future__ import annotations

from datetime import date
import secrets
from typing import Any, Dict, List, Optional

from ..sqlserver_schema import ErrorConsultaSQLServer, SQLServerConnection, sql_lit
from .shared import WhatsAppAdapter, separar_nombres_apellidos


class CitasRepositoryMixin:
    """Operaciones SQL Server para agendamiento transaccional, rotación médica y diagnósticos."""

    conn: SQLServerConnection

    # --- Consultas de citas y disponibilidad horaria ---
    def _query_citas(self, where_order_sql: str) -> List[Dict[str, Any]]:
        rows = self.conn.query_json(
            f"""
            SELECT
                c.Id_cita AS id,
                d.usuario_id,
                c.id_paciente AS mascota_id,
                COALESCE(v.usuario_id, v.Id_veterinario) AS doctor_id,
                COALESCE(u.nombre, LTRIM(RTRIM(d.nombres + ' ' + d.apellidos)), '') AS propietario,
                COALESCE(NULLIF(d.telefono, ''), u.telefono, '') AS telefono,
                COALESCE(p.nombre, '') AS mascota_nombre,
                COALESCE(s.Nombre, '') AS servicio,
                CONVERT(VARCHAR(10), c.fecha, 23) AS fecha,
                c.hora,
                c.motivo,
                LOWER(c.estado) AS estado,
                c.whatsapp_url,
                COALESCE(h.Diagnostico, '') AS diagnostico,
                COALESCE(h.Tratamiento, '') AS tratamiento
            FROM dbo.Cita c
            JOIN dbo.Veterinario v ON v.Id_veterinario = c.Id_veterinario
            LEFT JOIN dbo.Paciente p ON p.id_paciente = c.id_paciente
            LEFT JOIN dbo.Dueno d ON d.id_dueno = p.id_dueno
            LEFT JOIN dbo.usuarios u ON u.id = d.usuario_id
            LEFT JOIN dbo.Detalle_servicios ds ON ds.Id_cita = c.Id_cita
            LEFT JOIN dbo.Servicios s ON s.Id_servicios = ds.Id_servicios
            LEFT JOIN dbo.Historial_clinico h ON h.Id_historial = (
                SELECT MAX(h2.Id_historial) FROM dbo.Historial_clinico h2 WHERE h2.Id_cita = c.Id_cita
            )
            {where_order_sql}
            """
        )
        results: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["servicio"] = WhatsAppAdapter.SERVICIOS_CODIGOS.get(
                item["servicio"], item["servicio"]
            )
            results.append(item)
        return results

    def _cita_row(self, cita_id: int) -> Optional[Dict[str, Any]]:
        items = self._query_citas(f"WHERE c.Id_cita = {int(cita_id)}")
        return items[0] if items else None

    def obtener_disponibilidad_horarios(self, fecha: str) -> Dict[str, Any]:
        horarios = ["08:30", "10:00", "11:30", "13:00", "15:30", "17:00", "18:30"]
        rows = self.conn.query_json(
            f"""
            SELECT LEFT(hora, 5) AS hora, COUNT(*) AS ocupados
            FROM dbo.Cita
            WHERE fecha = {sql_lit(fecha[:10])} AND LOWER(estado) <> 'cancelada'
            GROUP BY LEFT(hora, 5)
            """
        )
        counts = {str(r["hora"])[:5]: int(r["ocupados"]) for r in rows}
        return {
            "fecha": fecha,
            "capacidad_por_turno": 3,
            "horarios": {
                h: {
                    "ocupados": counts.get(h, 0),
                    "capacidad_maxima": 3,
                    "disponible": counts.get(h, 0) < 3,
                }
                for h in horarios
            },
        }

    def _resolve_cita_paciente(self, datos: Dict[str, Any]) -> int:
        pet_id = datos.get("mascota_id")
        if pet_id is not None:
            pet = self.conn.query_one(
                f"""
                SELECT TOP 1 p.id_paciente, d.usuario_id, d.id_dueno
                FROM dbo.Paciente p
                JOIN dbo.Dueno d ON d.id_dueno = p.id_dueno
                WHERE p.id_paciente = {int(pet_id)} AND p.estado <> 'Eliminado'
                """
            )
            if pet:
                if datos.get("usuario_id") is not None and int(pet.get("usuario_id") or -1) != int(
                    datos["usuario_id"]
                ):
                    raise ValueError("La mascota no pertenece al usuario de la cita.")
                telefono = str(datos.get("telefono", "")).strip()
                if telefono:
                    self.conn.execute(
                        f"UPDATE dbo.Dueno SET telefono = {sql_lit(telefono)} WHERE id_dueno = {int(pet['id_dueno'])} AND telefono = ''"
                    )
                return int(pet["id_paciente"])

        propietario = str(datos.get("propietario", "")).strip() or "Cliente"
        telefono = str(datos.get("telefono", "")).strip()
        mascota_nombre = str(datos.get("mascota_nombre") or datos.get("mascota") or "Mascota").strip()
        if datos.get("usuario_id") is not None:
            owner_id = self._owner_id_for_user(int(datos["usuario_id"]), create=True)
            if telefono and owner_id:
                self.conn.execute(
                    f"UPDATE dbo.Dueno SET telefono = {sql_lit(telefono)} WHERE id_dueno = {owner_id} AND telefono = ''"
                )
        else:
            nombres, apellidos = separar_nombres_apellidos(propietario, default_nombre="Cliente")
            existing_owner = self.conn.query_one(
                f"""
                SELECT TOP 1 id_dueno
                FROM dbo.Dueno
                WHERE LOWER(nombres) = LOWER({sql_lit(nombres)})
                  AND LOWER(apellidos) = LOWER({sql_lit(apellidos)})
                  AND telefono = {sql_lit(telefono)}
                """
            )
            if existing_owner:
                owner_id = int(existing_owner["id_dueno"])
            else:
                ext_dni = f"EXT{secrets.token_hex(4).upper()}"
                owner_id = int(
                    self.conn.scalar(
                        f"""
                        INSERT INTO dbo.Dueno (usuario_id, dni, tipo_documento, nombres, apellidos, telefono)
                        OUTPUT INSERTED.id_dueno
                        VALUES (NULL, {sql_lit(ext_dni)}, 'DNI', {sql_lit(nombres)}, {sql_lit(apellidos)}, {sql_lit(telefono)})
                        """
                    )
                )
        existing_pet = self.conn.query_one(
            f"SELECT TOP 1 id_paciente FROM dbo.Paciente WHERE id_dueno = {owner_id} AND LOWER(nombre) = LOWER({sql_lit(mascota_nombre)}) AND estado <> 'Eliminado'"
        )
        if existing_pet:
            return int(existing_pet["id_paciente"])
        raza = self.conn.query_one("SELECT TOP 1 Id_raza FROM dbo.Razas ORDER BY Id_raza")
        raza_id = int(raza["Id_raza"]) if raza else 1
        today_str = date.today().isoformat()
        return int(
            self.conn.scalar(
                f"""
                INSERT INTO dbo.Paciente (id_dueno, Id_raza, nombre, sexo, fecha_nacimiento, peso_kg, historial_resumen, estado)
                OUTPUT INSERTED.id_paciente
                VALUES ({owner_id}, {raza_id}, {sql_lit(mascota_nombre)}, 'H', {sql_lit(today_str)}, 5.0, '', 'Activo')
                """
            )
        )

    # --- Registro transaccional de citas con control de 3 cupos y rotación médica ---
    def crear_cita(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        fecha = str(datos["fecha"]).strip()[:10]
        hora = str(datos["hora"]).strip()[:5]
        vet_id = None
        doctor = datos.get("doctor_id")
        if doctor is not None:
            found = self.conn.query_one(
                f"SELECT TOP 1 Id_veterinario FROM dbo.Veterinario WHERE usuario_id = {int(doctor)}"
            )
            if not found:
                found = self.conn.query_one(
                    f"SELECT TOP 1 Id_veterinario FROM dbo.Veterinario WHERE Id_veterinario = {int(doctor)}"
                )
            if found:
                vet_id = int(found["Id_veterinario"])
        if vet_id is None:
            found = self.conn.query_one(
                """
                SELECT TOP 1 v.Id_veterinario
                FROM dbo.Veterinario v
                LEFT JOIN dbo.Cita c
                    ON c.Id_veterinario = v.Id_veterinario
                    AND c.fecha = @fecha
                    AND LOWER(c.estado) <> 'cancelada'
                GROUP BY v.Id_veterinario
                ORDER BY
                    SUM(CASE WHEN c.hora = @hora OR LEFT(c.hora, 5) = @hora THEN 1 ELSE 0 END) ASC,
                    COUNT(c.Id_cita) ASC,
                    v.Id_veterinario ASC
                """,
                params={"fecha": fecha, "hora": hora},
            )
            if not found:
                raise ValueError("No hay veterinarios registrados para asignar la cita.")
            vet_id = int(found["Id_veterinario"])

        pet_id = self._resolve_cita_paciente(datos)
        service_key = str(datos.get("servicio", "")).strip()
        service_name = WhatsAppAdapter.SERVICIOS_NOMBRES.get(
            service_key, service_key or "Consulta general"
        )
        service = self.conn.query_one(
            f"SELECT TOP 1 Id_servicios, CAST(Precio AS FLOAT) AS Precio FROM dbo.Servicios WHERE LOWER(Nombre) = LOWER({sql_lit(service_name)})"
        )
        if not service:
            service = self.conn.query_one(
                "SELECT TOP 1 Id_servicios, CAST(Precio AS FLOAT) AS Precio FROM dbo.Servicios ORDER BY Id_servicios"
            )

        motivo = str(datos.get("motivo", "")).strip()
        estado = str(datos.get("estado", "pendiente")).lower()
        w_url = str(datos.get("whatsapp_url", "")).strip()
        diag = str(datos.get("diagnostico", "") or "")
        trat = str(datos.get("tratamiento", "") or "")
        has_service = 1 if service else 0
        service_id_val = int(service["Id_servicios"]) if service else 0
        service_price_val = float(service["Precio"]) if service else 0.0
        has_hist = 1 if (datos.get("diagnostico") or datos.get("tratamiento")) else 0

        try:
            cita_id = int(
                self.conn.scalar(
                    """
                    SET XACT_ABORT ON;
                    BEGIN TRY
                        BEGIN TRANSACTION;
                        -- Serializa reservas simultáneas del mismo turno (fecha + hora) para evitar deadlocks (1205) en rango vacío
                        DECLARE @lock_res NVARCHAR(128) = N'patitas_cita_' + @fecha + N'_' + @hora;
                        DECLARE @lock_rc INT;
                        EXEC @lock_rc = sys.sp_getapplock
                            @Resource = @lock_res,
                            @LockMode = N'Exclusive',
                            @LockOwner = N'Transaction',
                            @LockTimeout = 10000;
                        IF @lock_rc < 0
                            THROW 50002, N'LOCK_TIMEOUT', 1;

                        DECLARE @occ INT = (
                            SELECT COUNT(*)
                            FROM dbo.Cita
                            WHERE fecha = @fecha
                              AND (hora = @hora OR hora LIKE @hora + N'%')
                              AND LOWER(estado) <> 'cancelada'
                        );
                        IF @occ >= 3
                        BEGIN
                            ROLLBACK TRANSACTION;
                            THROW 50001, N'CUPO_LLENO', 1;
                        END;

                        INSERT INTO dbo.Cita (Id_veterinario, id_paciente, fecha, hora, motivo, estado, whatsapp_url)
                        VALUES (@vet_id, @pet_id, @fecha, @hora, @motivo, @estado, @w_url);
                        DECLARE @cita_id INT = CAST(SCOPE_IDENTITY() AS INT);

                        IF @has_service = 1
                        BEGIN
                            INSERT INTO dbo.Detalle_servicios (Id_cita, Id_servicios, precio_aplicado)
                            VALUES (@cita_id, @service_id, @service_price);
                        END;

                        IF @has_hist = 1
                        BEGIN
                            INSERT INTO dbo.Historial_clinico (Id_cita, Diagnostico, Tratamiento)
                            VALUES (@cita_id, @diag, @trat);
                        END;

                        COMMIT TRANSACTION;
                        SELECT CAST(@cita_id AS VARCHAR(20)) AS id;
                    END TRY
                    BEGIN CATCH
                        IF @@TRANCOUNT > 0
                            ROLLBACK TRANSACTION;
                        THROW;
                    END CATCH
                    """,
                    params={
                        "fecha": fecha,
                        "hora": hora,
                        "vet_id": vet_id,
                        "pet_id": pet_id,
                        "motivo": motivo,
                        "estado": estado,
                        "w_url": w_url,
                        "has_service": has_service,
                        "service_id": service_id_val,
                        "service_price": service_price_val,
                        "has_hist": has_hist,
                        "diag": diag,
                        "trat": trat,
                    },
                )
            )
        except ErrorConsultaSQLServer as exc:
            if getattr(exc, "native_err", 0) == 50001 or "CUPO_LLENO" in str(exc):
                raise ValueError(
                    f"El horario {hora} del {fecha} ya cuenta con sus 3 cupos médicos ocupados. Elige otro horario."
                ) from exc
            raise
        return self._cita_row(cita_id) or {"id": cita_id}

    def listar_citas(self, usuario_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if usuario_id is None:
            return self._query_citas("ORDER BY c.fecha, c.hora, c.Id_cita")
        return self._query_citas(
            f"WHERE d.usuario_id = {int(usuario_id)} ORDER BY c.fecha, c.hora, c.Id_cita"
        )

    # --- Actualización de estado e historial clínico por el médico ---
    def actualizar_cita_doctor(
        self,
        cita_id: int,
        estado: str,
        diagnostico: str,
        tratamiento: str,
        doctor_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        if doctor_id is None:
            updated = self.conn.scalar(
                f"UPDATE dbo.Cita SET estado = {sql_lit(estado)} OUTPUT INSERTED.Id_cita WHERE Id_cita = {int(cita_id)}"
            )
        else:
            vet = self.conn.query_one(
                f"SELECT TOP 1 Id_veterinario FROM dbo.Veterinario WHERE usuario_id = {int(doctor_id)}"
            )
            if not vet:
                vet = self.conn.query_one(
                    f"SELECT TOP 1 Id_veterinario FROM dbo.Veterinario WHERE Id_veterinario = {int(doctor_id)}"
                )
            vet_val = int(vet["Id_veterinario"]) if vet else None
            updated = self.conn.scalar(
                f"UPDATE dbo.Cita SET estado = {sql_lit(estado)}, Id_veterinario = COALESCE(Id_veterinario, {sql_lit(vet_val)}) OUTPUT INSERTED.Id_cita WHERE Id_cita = {int(cita_id)}"
            )
        if not updated.strip():
            return None
        diagnostico_limpio = diagnostico.strip()
        tratamiento_limpio = tratamiento.strip()
        hist = self.conn.query_one(
            f"SELECT TOP 1 Id_historial FROM dbo.Historial_clinico WHERE Id_cita = {int(cita_id)} ORDER BY Id_historial DESC"
        )
        if hist:
            if diagnostico_limpio or tratamiento_limpio:
                self.conn.execute(
                    f"UPDATE dbo.Historial_clinico SET Diagnostico = {sql_lit(diagnostico_limpio)}, Tratamiento = {sql_lit(tratamiento_limpio)} WHERE Id_historial = {int(hist['Id_historial'])}"
                )
        elif diagnostico_limpio or tratamiento_limpio:
            self.conn.execute(
                f"INSERT INTO dbo.Historial_clinico (Id_cita, Diagnostico, Tratamiento) VALUES ({int(cita_id)}, {sql_lit(diagnostico_limpio)}, {sql_lit(tratamiento_limpio)})"
            )
        return self._cita_row(cita_id)
