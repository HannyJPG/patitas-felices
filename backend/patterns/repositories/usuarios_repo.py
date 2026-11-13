"""Repositorio de Usuarios, Dueños y Personal Veterinario (dbo.usuarios, dbo.Dueno, dbo.Veterinario)."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from ..sqlserver_schema import (
    ErrorConsultaSQLServer,
    ErrorRegistroDuplicadoSQLServer,
    SQLServerConnection,
)
from .shared import (
    _PBKDF2_PREFIX,
    es_email_valido,
    hashear_password,
    separar_nombres_apellidos,
    verificar_password,
)


class UsuariosRepositoryMixin:
    """Operaciones SQL Server para autenticación, usuarios, documentos y personal médico."""

    conn: SQLServerConnection

    def _owner_id_for_user(self, usuario_id: int, create: bool = True) -> Optional[int]:
        row = self.conn.query_one(
            f"SELECT TOP 1 id_dueno FROM dbo.Dueno WHERE usuario_id = {int(usuario_id)}"
        )
        if row:
            return int(row["id_dueno"])
        user = self.conn.query_one(
            f"SELECT TOP 1 id, nombre, telefono FROM dbo.usuarios WHERE id = {int(usuario_id)}"
        )
        if not user or not create:
            return None
        nombres, apellidos = separar_nombres_apellidos(
            str(user.get("nombre") or "Cliente"), default_nombre="Cliente"
        )
        doc = f"CLI{int(usuario_id):05d}"
        tel = user.get("telefono") or ""
        new_id = self.conn.scalar(
            """
            SET XACT_ABORT ON;
            BEGIN TRY
                BEGIN TRANSACTION;
                DECLARE @existing_id INT = (
                    SELECT TOP 1 id_dueno
                    FROM dbo.Dueno WITH (UPDLOCK, HOLDLOCK)
                    WHERE usuario_id = @uid
                );
                IF @existing_id IS NULL
                BEGIN
                    INSERT INTO dbo.Dueno (usuario_id, dni, tipo_documento, nombres, apellidos, telefono)
                    VALUES (@uid, @doc, 'DNI', @nombres, @apellidos, @tel);
                    SET @existing_id = CAST(SCOPE_IDENTITY() AS INT);
                END;
                COMMIT TRANSACTION;
                SELECT CAST(@existing_id AS VARCHAR(20)) AS id;
            END TRY
            BEGIN CATCH
                IF @@TRANCOUNT > 0
                    ROLLBACK TRANSACTION;
                THROW;
            END CATCH
            """,
            params={
                "uid": int(usuario_id),
                "doc": doc,
                "nombres": nombres,
                "apellidos": apellidos,
                "tel": tel,
            },
        )
        return int(new_id)

    def _user_row(
        self,
        where_sql: str,
        params: Optional[Dict[str, Any]] = None,
        include_password_hash: bool = False,
    ) -> Optional[Dict[str, Any]]:
        row = self.conn.query_one(
            f"""
            SELECT TOP 1
                u.id, u.nombre, u.email, u.password_hash, u.rol, u.estado, u.telefono,
                COALESCE(NULLIF(v.nombres, ''), NULLIF(d.nombres, ''), '') AS nombres,
                COALESCE(NULLIF(v.Apellidos, ''), NULLIF(d.apellidos, ''), '') AS apellidos,
                CONVERT(VARCHAR(19), u.creado_en, 120) AS creado_en,
                COALESCE(d.tipo_documento, 'DNI') AS tipo_documento,
                CASE WHEN d.dni LIKE 'CLI%' OR d.dni LIKE 'EXT%' THEN NULL ELSE d.dni END AS documento,
                v.Id_veterinario AS id_veterinario,
                v.numero_colegiatura AS cmvp,
                esp.Nombre AS especialidad,
                CONVERT(VARCHAR(10), v.Fecha_contratacion, 23) AS fecha_contratacion
            FROM dbo.usuarios u
            LEFT JOIN dbo.Dueno d ON d.usuario_id = u.id
            LEFT JOIN dbo.Veterinario v ON v.usuario_id = u.id
            LEFT JOIN dbo.Especialidad esp ON esp.Id_especialidad = v.Id_especialidad
            WHERE {where_sql}
            """,
            params=params,
        )
        if row and not include_password_hash:
            row.pop("password_hash", None)
        return row

    def obtener_usuario_por_email(self, email: str) -> Optional[Dict[str, Any]]:
        email_limpio = str(email or "").strip().lower()
        if not email_limpio:
            return None
        return self._user_row(
            "u.email = @email",
            params={"email": email_limpio},
            include_password_hash=True,
        )

    def crear_usuario(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        nombre = str(datos.get("nombre", "")).strip()
        email = str(datos.get("email", "")).strip().lower()
        rol = str(datos.get("rol", "cliente")).strip().lower()
        estado = str(datos.get("estado", "activo")).strip().lower()
        telefono = str(datos.get("telefono", "")).strip()
        doc_nuevo = str(datos.get("documento") or "").strip()
        raw_pwd = str(datos.get("password_hash") or datos.get("password") or "")

        if len(nombre) < 2:
            raise ValueError("El nombre del usuario debe tener al menos 2 caracteres.")
        if not es_email_valido(email):
            raise ValueError("El correo electrónico suministrado no tiene un formato válido.")
        if rol not in ("cliente", "doctor", "admin"):
            raise ValueError("El rol del usuario debe ser 'cliente', 'doctor' o 'admin'.")
        if estado not in ("activo", "inactivo"):
            raise ValueError("El estado del usuario debe ser 'activo' o 'inactivo'.")
        if not raw_pwd or (not raw_pwd.startswith(_PBKDF2_PREFIX) and len(raw_pwd) < 6):
            raise ValueError("La contraseña debe tener al menos 6 caracteres.")

        if self.obtener_usuario_por_email(email):
            raise ValueError("Ya existe una cuenta registrada con este correo electrónico.")

        if doc_nuevo:
            dup = self.conn.query_one(
                "SELECT TOP 1 1 AS ok FROM dbo.Dueno WHERE dni = @dni",
                params={"dni": doc_nuevo},
            )
            if dup:
                raise ValueError(
                    "El documento de identidad ingresado ya está registrado en otra cuenta."
                )

        pwd_hash = hashear_password(raw_pwd)
        nombres_dueno, apellidos_dueno = separar_nombres_apellidos(
            nombre, datos.get("nombres"), datos.get("apellidos"), default_nombre=nombre
        )
        tipo_doc = str(datos.get("tipo_documento") or ("RUC" if len(doc_nuevo) == 11 else "DNI")).strip()
        crear_dueno = 1 if (rol == "cliente" or bool(doc_nuevo)) else 0

        try:
            nuevo_id_str = self.conn.scalar(
                """
                SET XACT_ABORT ON;
                BEGIN TRY
                    BEGIN TRANSACTION;
                    DECLARE @new_uid INT;
                    INSERT INTO dbo.usuarios (nombre, email, password_hash, rol, estado, telefono)
                    VALUES (@nombre, @email, @pwd_hash, @rol, @estado, @telefono);
                    SET @new_uid = CAST(SCOPE_IDENTITY() AS INT);

                    IF @crear_dueno = 1
                    BEGIN
                        DECLARE @dni_final VARCHAR(20) = CASE
                            WHEN LEN(@doc_nuevo) > 0 THEN @doc_nuevo
                            ELSE 'CLI' + RIGHT('00000' + CAST(@new_uid AS VARCHAR(10)), 5)
                        END;
                        INSERT INTO dbo.Dueno (usuario_id, dni, tipo_documento, nombres, apellidos, telefono)
                        VALUES (@new_uid, @dni_final, @tipo_doc, @nombres, @apellidos, @telefono);
                    END;

                    COMMIT TRANSACTION;
                    SELECT CAST(@new_uid AS VARCHAR(20)) AS id;
                END TRY
                BEGIN CATCH
                    IF @@TRANCOUNT > 0
                        ROLLBACK TRANSACTION;
                    THROW;
                END CATCH;
                """,
                params={
                    "nombre": nombre,
                    "email": email,
                    "pwd_hash": pwd_hash,
                    "rol": rol,
                    "estado": estado,
                    "telefono": telefono,
                    "crear_dueno": crear_dueno,
                    "doc_nuevo": doc_nuevo,
                    "tipo_doc": tipo_doc,
                    "nombres": nombres_dueno,
                    "apellidos": apellidos_dueno,
                },
            )
        except ErrorRegistroDuplicadoSQLServer as exc:
            raise ValueError(
                "Ya existe una cuenta registrada con este correo electrónico o documento de identidad."
            ) from exc

        if not nuevo_id_str or not str(nuevo_id_str).strip().isdigit():
            raise ErrorConsultaSQLServer(
                "No se pudo completar la inserción del usuario en SQL Server."
            )

        nuevo_id = int(str(nuevo_id_str).strip())
        usuario_persistido = self.obtener_usuario_por_id(nuevo_id)
        if not usuario_persistido or int(usuario_persistido.get("id", 0)) != nuevo_id:
            raise ErrorConsultaSQLServer(
                "No se pudo verificar la persistencia del usuario recién registrado en SQL Server."
            )
        return usuario_persistido

    def validar_documento_disponible(self, usuario_id: int, documento: str) -> None:
        """Verifica en solo lectura que un DNI/RUC no pertenezca a otra cuenta antes de operar."""
        doc_limpio = str(documento or "").strip()
        if not doc_limpio:
            return
        dup = self.conn.query_one(
            "SELECT TOP 1 1 AS ok FROM dbo.Dueno WHERE dni = @dni AND (usuario_id IS NULL OR usuario_id <> @uid)",
            params={"dni": doc_limpio, "uid": int(usuario_id)},
        )
        if dup:
            raise ValueError(
                "El documento de identidad ingresado ya está registrado en otra cuenta."
            )

    def actualizar_documento_usuario(
        self, usuario_id: int, tipo_documento: str, documento: str
    ) -> Optional[Dict[str, Any]]:
        doc_limpio = documento.strip()
        self.validar_documento_disponible(usuario_id, doc_limpio)
        self._owner_id_for_user(usuario_id, create=True)
        self.conn.execute(
            "UPDATE dbo.Dueno SET dni = @dni, tipo_documento = @tipo WHERE usuario_id = @uid",
            params={"dni": doc_limpio, "tipo": tipo_documento.strip(), "uid": int(usuario_id)},
        )
        return self.obtener_usuario_por_id(int(usuario_id))

    def cambiar_password_usuario(
        self, usuario_id: int, password_actual: str, password_nueva: str
    ) -> bool:
        row = self.conn.query_one(
            "SELECT TOP 1 password_hash FROM dbo.usuarios WHERE id = @uid",
            params={"uid": int(usuario_id)},
        )
        if not row or not verificar_password(password_actual, row["password_hash"]):
            raise ValueError("La contraseña actual no es correcta.")
        nuevo_hash = hashear_password(password_nueva)
        self.conn.execute(
            "UPDATE dbo.usuarios SET password_hash = @pwd_hash WHERE id = @uid",
            params={"pwd_hash": nuevo_hash, "uid": int(usuario_id)},
        )
        return True

    def existe_colegiatura_veterinario(self, cmvp: str) -> bool:
        codigo = str(cmvp or "").strip()
        if not codigo:
            return False
        row = self.conn.query_one(
            "SELECT TOP 1 1 AS ok FROM dbo.Veterinario WHERE LOWER(numero_colegiatura) = LOWER(@cmvp)",
            params={"cmvp": codigo},
        )
        return row is not None

    def crear_doctor(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        cmvp = str(datos.get("cmvp") or "").strip()
        if not cmvp:
            raise ValueError(
                "El número de colegiatura CMVP es obligatorio para registrar un médico veterinario."
            )
        if self.existe_colegiatura_veterinario(cmvp):
            raise ValueError(
                f"El número de colegiatura '{cmvp}' ya está registrado para otro profesional veterinario."
            )
        email = str(datos.get("correo", datos.get("email", ""))).strip().lower()
        user = (
            self.conn.query_one(
                "SELECT TOP 1 id FROM dbo.usuarios WHERE LOWER(email) = LOWER(@email)",
                params={"email": email},
            )
            if email
            else None
        )
        spec_name = str(datos.get("especialidad") or "Medicina General").strip() or "Medicina General"
        spec_id_override = int(datos["especialidad_id"]) if datos.get("especialidad_id") else 0
        nombre_completo, apellidos = separar_nombres_apellidos(
            str(datos.get("nombre") or "Doctor"),
            datos.get("nombres"),
            datos.get("apellidos"),
            default_nombre="Doctor",
        )
        if not nombre_completo.strip() or not apellidos.strip():
            raise ValueError(
                "Los nombres y apellidos son obligatorios para registrar un médico veterinario."
            )
        uid_val = datos.get("usuario_id") or (user["id"] if user else None)
        tel_val = str(datos.get("telefono", "")).strip()
        fecha_cont = str(datos.get("fecha_contratacion", date.today().isoformat()))[:10]

        try:
            new_id_str = self.conn.scalar(
                """
                SET XACT_ABORT ON;
                BEGIN TRY
                    BEGIN TRANSACTION;
                    DECLARE @spec_id INT = @spec_id_override;
                    IF @spec_id IS NULL OR @spec_id <= 0
                    BEGIN
                        SELECT TOP 1 @spec_id = Id_especialidad
                        FROM dbo.Especialidad
                        WHERE LOWER(Nombre) = LOWER(@spec_name);

                        IF @spec_id IS NULL
                        BEGIN
                            INSERT INTO dbo.Especialidad (Nombre, Descripcion)
                            VALUES (@spec_name, N'Especialidad registrada desde panel administrativo');
                            SET @spec_id = CAST(SCOPE_IDENTITY() AS INT);
                        END;
                    END;

                    INSERT INTO dbo.Veterinario (
                        usuario_id, Id_especialidad, numero_colegiatura,
                        nombres, Apellidos, Telefono, Fecha_contratacion
                    )
                    VALUES (
                        @uid_val, @spec_id, @cmvp,
                        @nombres, @apellidos, @tel_val, @fecha_cont
                    );
                    DECLARE @new_vet_id INT = CAST(SCOPE_IDENTITY() AS INT);

                    COMMIT TRANSACTION;
                    SELECT CAST(@new_vet_id AS VARCHAR(20)) AS id;
                END TRY
                BEGIN CATCH
                    IF @@TRANCOUNT > 0
                        ROLLBACK TRANSACTION;
                    THROW;
                END CATCH;
                """,
                params={
                    "spec_id_override": spec_id_override,
                    "spec_name": spec_name,
                    "uid_val": int(uid_val) if uid_val is not None else None,
                    "cmvp": cmvp,
                    "nombres": nombre_completo,
                    "apellidos": apellidos,
                    "tel_val": tel_val,
                    "fecha_cont": fecha_cont,
                },
            )
        except ErrorRegistroDuplicadoSQLServer as exc:
            raise ValueError(
                f"El número de colegiatura '{cmvp}' o el usuario asignado ya está registrado en dbo.Veterinario."
            ) from exc

        if not new_id_str or not str(new_id_str).strip().isdigit():
            raise ErrorConsultaSQLServer(
                "No se pudo confirmar la inserción del médico veterinario en SQL Server."
            )
        new_id = int(str(new_id_str).strip())
        verificado = self.conn.query_one(
            """
            SELECT TOP 1
                v.Id_veterinario AS id,
                v.usuario_id,
                v.Id_especialidad AS especialidad_id,
                esp.Nombre AS especialidad,
                v.numero_colegiatura AS cmvp,
                v.nombres,
                v.Apellidos AS apellidos,
                v.Telefono AS telefono,
                CONVERT(VARCHAR(10), v.Fecha_contratacion, 23) AS fecha_contratacion
            FROM dbo.Veterinario v
            JOIN dbo.Especialidad esp ON esp.Id_especialidad = v.Id_especialidad
            WHERE v.Id_veterinario = @vid
            """,
            params={"vid": new_id},
        )
        if not verificado:
            raise ErrorConsultaSQLServer(
                "No se pudo verificar la persistencia del médico veterinario en dbo.Veterinario."
            )
        return {**datos, **verificado, "id": new_id}

    def crear_personal(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        """
        Registra de forma atómica y transaccional en SQL Server a un miembro del personal
        ('doctor' o 'admin'), insertando en dbo.usuarios y (si es doctor) en dbo.Especialidad
        y dbo.Veterinario dentro de una única transacción con verificación posterior SELECT.
        """
        nombres_input = str(datos.get("nombres") or "").strip()
        apellidos_input = str(datos.get("apellidos") or "").strip()
        nombre = str(datos.get("nombre") or "").strip()
        if not nombre and (nombres_input or apellidos_input):
            nombre = f"{nombres_input} {apellidos_input}".strip()
        email = str(datos.get("email", "")).strip().lower()
        rol = str(datos.get("rol", "")).strip().lower()
        estado = str(datos.get("estado", "activo")).strip().lower()
        telefono = str(datos.get("telefono", "")).strip()
        raw_pwd = str(datos.get("password_hash") or datos.get("password") or "")
        cmvp = str(datos.get("cmvp") or "").strip()
        spec_name = str(datos.get("especialidad") or "Medicina General").strip() or "Medicina General"
        fecha_cont = str(datos.get("fecha_contratacion", date.today().isoformat()))[:10]

        if len(nombre) < 2:
            raise ValueError("El nombre y apellido del personal deben tener al menos 2 caracteres.")
        if not es_email_valido(email):
            raise ValueError("El correo electrónico suministrado no tiene un formato válido.")
        if rol not in ("doctor", "admin"):
            raise ValueError("El rol asignado debe ser 'doctor' o 'admin'.")
        if not raw_pwd or (not raw_pwd.startswith(_PBKDF2_PREFIX) and len(raw_pwd) < 6):
            raise ValueError("La contraseña debe tener al menos 6 caracteres.")

        if self.obtener_usuario_por_email(email):
            raise ValueError("Ya existe una cuenta registrada con este correo electrónico.")

        if rol == "doctor":
            if not cmvp:
                raise ValueError(
                    "El número de colegiatura CMVP es obligatorio para registrar un médico veterinario."
                )
            if self.existe_colegiatura_veterinario(cmvp):
                raise ValueError(
                    f"El número de colegiatura '{cmvp}' ya está registrado para otro profesional veterinario."
                )

        pwd_hash = hashear_password(raw_pwd)
        nombres_vet, apellidos_vet = separar_nombres_apellidos(
            nombre, nombres_input, apellidos_input, default_nombre=nombre
        )
        if rol == "doctor" and (not nombres_vet.strip() or not apellidos_vet.strip()):
            raise ValueError(
                "Los nombres y apellidos son obligatorios para registrar un médico veterinario."
            )
        es_doctor = 1 if rol == "doctor" else 0

        try:
            nuevo_uid_str = self.conn.scalar(
                """
                SET XACT_ABORT ON;
                BEGIN TRY
                    BEGIN TRANSACTION;

                    INSERT INTO dbo.usuarios (nombre, email, password_hash, rol, estado, telefono)
                    VALUES (@nombre, @email, @pwd_hash, @rol, @estado, @telefono);
                    DECLARE @new_uid INT = CAST(SCOPE_IDENTITY() AS INT);

                    IF @es_doctor = 1
                    BEGIN
                        DECLARE @spec_id INT = (
                            SELECT TOP 1 Id_especialidad
                            FROM dbo.Especialidad
                            WHERE LOWER(Nombre) = LOWER(@spec_name)
                        );
                        IF @spec_id IS NULL
                        BEGIN
                            INSERT INTO dbo.Especialidad (Nombre, Descripcion)
                            VALUES (@spec_name, N'Especialidad registrada desde panel administrativo');
                            SET @spec_id = CAST(SCOPE_IDENTITY() AS INT);
                        END;

                        INSERT INTO dbo.Veterinario (
                            usuario_id, Id_especialidad, numero_colegiatura,
                            nombres, Apellidos, Telefono, Fecha_contratacion
                        )
                        VALUES (
                            @new_uid, @spec_id, @cmvp,
                            @nombres_vet, @apellidos_vet, @telefono, @fecha_cont
                        );
                    END;

                    COMMIT TRANSACTION;
                    SELECT CAST(@new_uid AS VARCHAR(20)) AS id;
                END TRY
                BEGIN CATCH
                    IF @@TRANCOUNT > 0
                        ROLLBACK TRANSACTION;
                    THROW;
                END CATCH;
                """,
                params={
                    "nombre": nombre,
                    "email": email,
                    "pwd_hash": pwd_hash,
                    "rol": rol,
                    "estado": estado,
                    "telefono": telefono,
                    "es_doctor": es_doctor,
                    "spec_name": spec_name,
                    "cmvp": cmvp,
                    "nombres_vet": nombres_vet,
                    "apellidos_vet": apellidos_vet,
                    "fecha_cont": fecha_cont,
                },
            )
        except ErrorRegistroDuplicadoSQLServer as exc:
            raise ValueError(
                "Ya existe un registro en SQL Server con ese correo electrónico o número de colegiatura CMVP."
            ) from exc

        if not nuevo_uid_str or not str(nuevo_uid_str).strip().isdigit():
            raise ErrorConsultaSQLServer(
                "No se pudo completar el registro transaccional del personal en SQL Server."
            )

        nuevo_uid = int(str(nuevo_uid_str).strip())
        usuario_persistido = self.obtener_usuario_por_id(nuevo_uid)
        if not usuario_persistido or int(usuario_persistido.get("id", 0)) != nuevo_uid:
            raise ErrorConsultaSQLServer(
                "No se pudo verificar la persistencia del nuevo personal en dbo.usuarios de SQL Server."
            )
        if rol == "doctor" and not usuario_persistido.get("cmvp"):
            raise ErrorConsultaSQLServer(
                "No se pudo verificar la persistencia del médico veterinario en dbo.Veterinario de SQL Server."
            )
        return usuario_persistido

    def obtener_usuario_por_id(self, usuario_id: int) -> Optional[Dict[str, Any]]:
        return self._user_row(
            "u.id = @uid",
            params={"uid": int(usuario_id)},
            include_password_hash=False,
        )

    def listar_usuarios(self) -> List[Dict[str, Any]]:
        return self.conn.query_json(
            """
            SELECT
                u.id, u.nombre, u.email, u.rol, u.estado, u.telefono,
                COALESCE(NULLIF(v.nombres, ''), NULLIF(d.nombres, ''), '') AS nombres,
                COALESCE(NULLIF(v.Apellidos, ''), NULLIF(d.apellidos, ''), '') AS apellidos,
                CONVERT(VARCHAR(19), u.creado_en, 120) AS creado_en,
                COALESCE(d.tipo_documento, 'DNI') AS tipo_documento,
                CASE WHEN d.dni LIKE 'CLI%' OR d.dni LIKE 'EXT%' THEN NULL ELSE d.dni END AS documento,
                v.Id_veterinario AS id_veterinario,
                v.numero_colegiatura AS cmvp,
                esp.Nombre AS especialidad,
                CONVERT(VARCHAR(10), v.Fecha_contratacion, 23) AS fecha_contratacion
            FROM dbo.usuarios u
            LEFT JOIN dbo.Dueno d ON d.usuario_id = u.id
            LEFT JOIN dbo.Veterinario v ON v.usuario_id = u.id
            LEFT JOIN dbo.Especialidad esp ON esp.Id_especialidad = v.Id_especialidad
            ORDER BY u.id ASC
            """
        )

    def listar_personal(self) -> List[Dict[str, Any]]:
        """
        Devuelve todo el personal médico y administrativo persistido en SQL Server,
        combinando dbo.usuarios (rol IN ('doctor', 'admin')) con dbo.Veterinario y dbo.Especialidad,
        incluyendo tanto los registros iniciales (SEED) como todo el personal registrado posteriormente.
        """
        return self.conn.query_json(
            """
            SELECT
                COALESCE(u.id, 10000 + v.Id_veterinario) AS id,
                u.id AS usuario_id,
                v.Id_veterinario AS id_veterinario,
                COALESCE(u.nombre, LTRIM(RTRIM(v.nombres + ' ' + v.Apellidos))) AS nombre,
                COALESCE(v.nombres, '') AS nombres,
                COALESCE(v.Apellidos, '') AS apellidos,
                COALESCE(u.email, '') AS email,
                COALESCE(u.rol, 'doctor') AS rol,
                COALESCE(u.estado, 'activo') AS estado,
                COALESCE(NULLIF(u.telefono, ''), v.Telefono, '') AS telefono,
                v.numero_colegiatura AS cmvp,
                COALESCE(
                    esp.Nombre,
                    CASE WHEN u.rol = 'admin' THEN N'Dirección y Administración Clínica' ELSE N'Medicina General' END
                ) AS especialidad,
                COALESCE(
                    CONVERT(VARCHAR(10), v.Fecha_contratacion, 23),
                    CONVERT(VARCHAR(10), u.creado_en, 23)
                ) AS fecha_contratacion,
                COALESCE(
                    CONVERT(VARCHAR(19), u.creado_en, 120),
                    CONVERT(VARCHAR(10), v.Fecha_contratacion, 23) + ' 09:00:00'
                ) AS creado_en
            FROM dbo.usuarios u
            FULL OUTER JOIN dbo.Veterinario v ON v.usuario_id = u.id
            LEFT JOIN dbo.Especialidad esp ON esp.Id_especialidad = v.Id_especialidad
            WHERE (u.rol IN ('doctor', 'admin')) OR (v.Id_veterinario IS NOT NULL)
            ORDER BY
                CASE WHEN u.id IS NOT NULL THEN 0 ELSE 1 END ASC,
                COALESCE(u.id, v.Id_veterinario) ASC
            """
        )

    def obtener_perfil_doctor(self, usuario_actual: Dict[str, Any]) -> Dict[str, Any]:
        """Obtiene desde SQL Server (dbo.Veterinario + dbo.Especialidad) el perfil real del médico autenticado."""
        uid = usuario_actual.get("id")
        row = None
        if uid is not None:
            row = self.conn.query_one(
                """
                SELECT TOP 1
                    v.Id_veterinario AS id_veterinario,
                    v.usuario_id,
                    v.numero_colegiatura AS colegiatura,
                    esp.Nombre AS especialidad,
                    LTRIM(RTRIM(v.nombres + ' ' + v.Apellidos)) AS nombre_veterinario,
                    v.Telefono AS telefono_veterinario,
                    CONVERT(VARCHAR(10), v.Fecha_contratacion, 23) AS fecha_contratacion
                FROM dbo.Veterinario v
                LEFT JOIN dbo.Especialidad esp ON esp.Id_especialidad = v.Id_especialidad
                WHERE v.usuario_id = @uid
                ORDER BY v.Id_veterinario ASC
                """,
                params={"uid": int(uid)},
            )
        es_doctor = str(usuario_actual.get("rol", "")).lower() == "doctor"
        if not row and es_doctor:
            colegiatura_fallback = usuario_actual.get("cmvp") or "Sin CMVP"
            especialidad_fallback = usuario_actual.get("especialidad") or "Medicina General"
        elif not row:
            colegiatura_fallback = "Dirección Clínica"
            especialidad_fallback = "Administración Veterinaria"
        else:
            colegiatura_fallback = row.get("colegiatura") or usuario_actual.get("cmvp") or "Sin CMVP"
            especialidad_fallback = row.get("especialidad") or usuario_actual.get("especialidad") or "Medicina General"
        return {
            "id": uid or (row.get("id_veterinario") if row else 1),
            "id_veterinario": row.get("id_veterinario") if row else None,
            "nombre": usuario_actual.get("nombre") or (row.get("nombre_veterinario") if row else "Médico Veterinario"),
            "email": usuario_actual.get("email") or "",
            "telefono": usuario_actual.get("telefono") or (row.get("telefono_veterinario") if row else ""),
            "colegiatura": colegiatura_fallback,
            "especialidad": especialidad_fallback,
            "horario_turno": "Lunes a Sábado · 09:00 a 18:00 (Lima)",
        }

    def actualizar_estado_usuario(
        self, usuario_id: int, nuevo_estado: str
    ) -> Optional[Dict[str, Any]]:
        self.conn.execute(
            "UPDATE dbo.usuarios SET estado = @estado WHERE id = @uid",
            params={"estado": nuevo_estado, "uid": int(usuario_id)},
        )
        return self.obtener_usuario_por_id(int(usuario_id))
