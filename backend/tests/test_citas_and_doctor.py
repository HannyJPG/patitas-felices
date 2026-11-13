"""Pruebas de agenda clínica, concurrencia de cupos, mascotas y panel médico."""

import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import crear_app
from backend.patterns import (
    AdminRoleStrategy,
    AuthSessionProxy,
    ClientRoleStrategy,
    DoctorRoleStrategy,
    ErrorProcesoVenta,
    ErrorSeguridadProxy,
    RBACContext,
    RealClinicController,
    SQLServerDatabaseAdapter,
    SubsistemaCRMTransacciones,
    TiendaFacade,
    WhatsAppAdapter,
    generar_token_jwt,
)


def test_cliente_crea_y_elimina_mascota(db_memoria: SQLServerDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    # Login como cliente existente
    res_login = client.post(
        "/api/auth/login",
        json={"email": "cliente@patitasfelices.pe", "password": "cliente123"},
    )
    assert res_login.status_code == 200
    token_cliente = res_login.json()["token"]

    # 1. Registrar una nueva mascota
    payload_mascota = {
        "nombre": "Boby",
        "especie": "Perro",
        "raza": "Beagle",
        "edad": 2,
        "peso_kg": 12.5,
        "sexo": "M",
        "historial_resumen": "Vacuna antirrábica aplicada.",
    }
    res_crear = client.post(
        "/api/cliente/mascotas",
        headers={"Authorization": f"Bearer {token_cliente}"},
        json=payload_mascota,
    )
    assert res_crear.status_code == 200, res_crear.text
    mascota_creada = res_crear.json()["mascota"]
    assert mascota_creada["nombre"] == "Boby"
    assert mascota_creada["raza"] == "Beagle"
    mascota_id = mascota_creada["id"]

    # 2. Consultar lista de mis mascotas
    res_listar = client.get(
        "/api/cliente/mis-mascotas",
        headers={"Authorization": f"Bearer {token_cliente}"},
    )
    assert res_listar.status_code == 200
    mascotas = res_listar.json()["mascotas"]
    assert any(m["id"] == mascota_id for m in mascotas)

    # 3. Eliminar la mascota creada
    res_eliminar = client.delete(
        f"/api/cliente/mascotas/{mascota_id}",
        headers={"Authorization": f"Bearer {token_cliente}"},
    )
    assert res_eliminar.status_code == 200
    assert res_eliminar.json()["eliminado"] is True

def test_flujo_solicitud_mascota_cliente_y_aprobacion_admin(db_memoria: SQLServerDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    # Cliente crea mascota
    res_login_c = client.post("/api/auth/login", json={"email": "cliente@patitasfelices.pe", "password": "cliente123"})
    token_cliente = res_login_c.json()["token"]

    res_m = client.post(
        "/api/cliente/mascotas",
        headers={"Authorization": f"Bearer {token_cliente}"},
        json={"nombre": "Pelusa", "especie": "Gato", "raza": "Angora", "edad": 2, "peso_kg": 3.5},
    )
    assert res_m.status_code == 200
    mascota_id = res_m.json()["mascota"]["id"]

    # Cliente solicita edición con justificación descriptiva
    payload_sol = {
        "tipo": "editar",
        "motivo": "Aumento de peso post-esterilización y cambio de dieta",
        "datos_nuevos": {
            "nombre": "Pelusa",
            "especie": "Gato",
            "raza": "Angora",
            "edad": 3,
            "peso_kg": 4.2,
            "historial_resumen": "Control de peso verificado",
        },
    }
    res_sol = client.post(
        f"/api/cliente/mascotas/{mascota_id}/solicitar-cambio",
        headers={"Authorization": f"Bearer {token_cliente}"},
        json=payload_sol,
    )
    assert res_sol.status_code == 200
    solicitud_id = res_sol.json()["solicitud"]["id"]

    # Cliente consulta sus solicitudes
    res_mis_sol = client.get("/api/cliente/solicitudes", headers={"Authorization": f"Bearer {token_cliente}"})
    assert res_mis_sol.status_code == 200
    assert any(s["id"] == solicitud_id for s in res_mis_sol.json()["solicitudes"])

    # Admin consulta la bandeja de solicitudes y la aprueba
    res_login_a = client.post("/api/auth/login", json={"email": "admin@patitasfelices.pe", "password": "admin123"})
    token_admin = res_login_a.json()["token"]

    res_admin_list = client.get("/api/admin/solicitudes-mascotas", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_admin_list.status_code == 200

    res_aprobar = client.post(
        f"/api/admin/solicitudes-mascotas/{solicitud_id}/resolver",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"accion": "aprobar"},
    )
    assert res_aprobar.status_code == 200
    assert res_aprobar.json()["solicitud"]["estado"] == "aprobada"

    # Verificar que los datos de Pelusa se actualizaron en la base de datos
    res_mascotas = client.get("/api/cliente/mis-mascotas", headers={"Authorization": f"Bearer {token_cliente}"})
    pelusa_actualizada = next(m for m in res_mascotas.json()["mascotas"] if m["id"] == mascota_id)
    assert pelusa_actualizada["peso_kg"] == 4.2
    assert pelusa_actualizada["edad"] == 3

def test_cliente_consulta_sus_compras(db_memoria: SQLServerDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    res_login_c = client.post("/api/auth/login", json={"email": "cliente@patitasfelices.pe", "password": "cliente123"})
    token_cliente = res_login_c.json()["token"]

    # Realizar compra
    client.post(
        "/api/tienda/checkout",
        headers={"Authorization": f"Bearer {token_cliente}"},
        json={
            "cliente_nombre": "Lucía Fernández",
            "tipo_documento": "DNI",
            "cliente_documento": "74859632",
            "metodo_pago": "Yape / Plin",
            "items": [{"producto_id": 1, "cantidad": 1}],
        },
    )

    # Consultar mis compras
    res_compras = client.get("/api/cliente/mis-compras", headers={"Authorization": f"Bearer {token_cliente}"})
    assert res_compras.status_code == 200
    compras = res_compras.json()["compras"]
    assert len(compras) >= 1
    assert "detalles" in compras[0]

def test_disponibilidad_horarios_y_limite_tres_doctores(db_memoria: SQLServerDatabaseAdapter) -> None:
    app = crear_app(db_adapter=db_memoria)
    client = TestClient(app)

    fecha_test = "2026-11-01"
    hora_test = "08:30"

    # 1. Consultar disponibilidad inicial (todos los cupos libres)
    res_disp = client.get(f"/api/citas/disponibilidad?fecha={fecha_test}")
    assert res_disp.status_code == 200
    horarios = res_disp.json()["horarios"]
    assert hora_test in horarios
    assert horarios[hora_test]["ocupados"] == 0
    assert horarios[hora_test]["disponible"] is True

    # 2. Registrar 3 citas para llenar los 3 doctores de ese turno
    for i in range(1, 4):
        res_cita = client.post(
            "/api/citas",
            json={
                "propietario": f"Paciente {i}",
                "telefono": f"98765432{i}",
                "mascota_nombre": f"Mascota {i}",
                "servicio": "consulta-general",
                "fecha": fecha_test,
                "hora": hora_test,
                "motivo": f"Control rutinario {i}",
            },
        )
        assert res_cita.status_code == 200, res_cita.text

    # 3. Verificar que la disponibilidad ahora marca 3 ocupados y no disponible
    res_disp_lleno = client.get(f"/api/citas/disponibilidad?fecha={fecha_test}")
    assert res_disp_lleno.status_code == 200
    horario_lleno = res_disp_lleno.json()["horarios"][hora_test]
    assert horario_lleno["ocupados"] == 3
    assert horario_lleno["disponible"] is False

    # 4. Intentar registrar una 4ta cita en el mismo turno debe fallar con 400
    res_cita_cuarta = client.post(
        "/api/citas",
        json={
            "propietario": "Paciente 4 (Sin cupo)",
            "telefono": "987654324",
            "mascota_nombre": "Mascota 4",
            "servicio": "consulta-general",
            "fecha": fecha_test,
            "hora": hora_test,
            "motivo": "Urgencia médica por malestar general",
        },
    )
    assert res_cita_cuarta.status_code == 400
    assert "3 cupos médicos" in res_cita_cuarta.json()["detail"]

def test_registro_doctor_nombres_apellidos_sin_prefijo_y_persistencia_reinicio():
    """
    Verifica separación limpia de honoríficos ('Dr. Mario Ruiz' -> nombres='Mario', Apellidos='Ruiz'),
    campos explícitos nombres/apellidos, email vacío en veterinario sin cuenta,
    aislamiento de perfil doctor y persistencia tras reinicio.
    """
    db1 = SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=True)
    app1 = crear_app(db_adapter=db1)
    client1 = TestClient(app1)

    res_admin = client1.post(
        "/api/auth/login",
        json={"email": "admin@patitasfelices.pe", "password": "admin123"},
    )
    assert res_admin.status_code == 200
    token_admin = res_admin.json()["token"]
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    # 1. Alta enviando solo nombre con prefijo honorífico 'Dr. Mario Ruiz'
    res_mario = client1.post(
        "/api/admin/personal",
        headers=headers_admin,
        json={
            "nombre": "Dr. Mario Ruiz",
            "email": "mario.audit@patitasfelices.pe",
            "password": "Doctor123!",
            "rol": "doctor",
            "telefono": "987654321",
            "cmvp": "CMVP-88001",
            "especialidad": "Cirugía",
        },
    )
    assert res_mario.status_code == 200, res_mario.text
    mario_id = res_mario.json()["usuario"]["id"]
    vet_mario = db1.conn.query_one(
        "SELECT nombres, Apellidos, numero_colegiatura FROM dbo.Veterinario WHERE usuario_id = @uid",
        params={"uid": mario_id},
    )
    assert vet_mario is not None
    assert vet_mario["nombres"] == "Mario"
    assert vet_mario["Apellidos"] == "Ruiz"

    # 2. Alta con nombres y apellidos explícitos
    res_andrea = client1.post(
        "/api/admin/personal",
        headers=headers_admin,
        json={
            "nombres": "Andrea Sofía",
            "apellidos": "Morales Vega",
            "email": "andrea.audit@patitasfelices.pe",
            "password": "Doctor123!",
            "rol": "doctor",
            "telefono": "999888777",
            "cmvp": "CMVP-88002",
            "especialidad": "Dermatología",
        },
    )
    assert res_andrea.status_code == 200, res_andrea.text
    andrea_id = res_andrea.json()["usuario"]["id"]
    vet_andrea = db1.conn.query_one(
        "SELECT nombres, Apellidos FROM dbo.Veterinario WHERE usuario_id = @uid",
        params={"uid": andrea_id},
    )
    assert vet_andrea["nombres"] == "Andrea Sofía"
    assert vet_andrea["Apellidos"] == "Morales Vega"

    # 3. Correo mal formado debe ser rechazado (400)
    res_bad_email = client1.post(
        "/api/auth/register",
        json={"nombre": "Test Invalido", "email": "@patitasfelices.pe", "password": "Clave123!"},
    )
    assert res_bad_email.status_code == 400

    # 4. Doctor seed sin cuenta web no debe mostrar correo falso en listar_personal()
    personal = db1.listar_personal()
    carlos = next((p for p in personal if p.get("cmvp") == "CMVP-10452"), None)
    assert carlos is not None
    assert carlos["email"] == ""

    # 5. Simular reinicio de aplicación sin borrar datos y verificar login + perfil propio
    db1.conn.close()
    db2 = SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=False)
    app2 = crear_app(db_adapter=db2)
    client2 = TestClient(app2)

    res_login_mario = client2.post(
        "/api/auth/login",
        json={"email": "mario.audit@patitasfelices.pe", "password": "Doctor123!"},
    )
    assert res_login_mario.status_code == 200
    token_mario = res_login_mario.json()["token"]

    res_agenda = client2.get(
        "/api/doctor/agenda",
        headers={"Authorization": f"Bearer {token_mario}"},
    )
    assert res_agenda.status_code == 200
    perfil_prof = res_agenda.json()["perfil_profesional"]
    assert perfil_prof["colegiatura"] == "CMVP-88001"
    assert "Mario" in perfil_prof["nombre"]

def test_cita_confirmar_no_sobrescribe_diagnostico_existente(
    db_memoria: SQLServerDatabaseAdapter, client: TestClient
):
    """Confirmar o cambiar estado con campos vacíos no debe borrar el historial clínico previo."""
    db = db_memoria

    res_doc = client.post(
        "/api/auth/login",
        json={"email": "doctor@patitasfelices.pe", "password": "doctor123"},
    )
    assert res_doc.status_code == 200
    headers_doc = {"Authorization": f"Bearer {res_doc.json()['token']}"}

    citas = db.listar_citas()
    assert len(citas) >= 1
    cita_id = int(citas[0]["id"])

    r1 = client.patch(
        f"/api/doctor/citas/{cita_id}",
        headers=headers_doc,
        json={
            "estado": "atendida",
            "diagnostico": "Otitis externa leve",
            "tratamiento": "Limpieza ótica cada 12 horas",
        },
    )
    assert r1.status_code == 200
    assert r1.json()["cita"]["diagnostico"] == "Otitis externa leve"

    # Ahora simular cambio de estado sin reenviar diagnóstico ni tratamiento
    r2 = client.patch(
        f"/api/doctor/citas/{cita_id}",
        headers=headers_doc,
        json={"estado": "confirmada", "diagnostico": "", "tratamiento": ""},
    )
    assert r2.status_code == 200
    assert r2.json()["cita"]["diagnostico"] == "Otitis externa leve"
    assert r2.json()["cita"]["tratamiento"] == "Limpieza ótica cada 12 horas"

def test_doctor_sin_apellidos_rechazado_en_personal_y_doctor():
    """No debe permitirse registrar un médico veterinario sin apellidos (evita 'Dr.' / 'Mario')."""
    db = SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=True, include_demo_users=True)
    app = crear_app(db_adapter=db)
    client = TestClient(app)

    login = client.post(
        "/api/auth/login",
        json={"email": "admin@patitasfelices.pe", "password": "admin123"},
    )
    assert login.status_code == 200
    token_admin = login.json()["token"]

    res_bad = client.post(
        "/api/admin/personal",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "nombre": "Dr. Mario",
            "nombres": "Dr. Mario",
            "apellidos": "",
            "email": "mario.sinapellido@patitasfelices.pe",
            "password": "Password123!",
            "rol": "doctor",
            "cmvp": "CMVP-88888",
            "especialidad": "Medicina General",
        },
    )
    assert res_bad.status_code == 400
    assert db.obtener_usuario_por_email("mario.sinapellido@patitasfelices.pe") is None

    with pytest.raises(ValueError):
        db.crear_doctor({"nombre": "Dr. Solo", "cmvp": "CMVP-88889"})

def test_crear_cita_concurrente_respeta_limite_3_cupos():
    """Múltiples hilos reservando el mismo horario nunca deben superar los 3 cupos médicos."""
    from concurrent.futures import ThreadPoolExecutor

    db = SQLServerDatabaseAdapter("PatitasFelices_Test_DB", reset_tables=True, include_demo_users=True)
    fecha = "2026-12-20"
    hora = "11:00"
    exitos = []
    rechazos = []

    def reservar(idx: int):
        try:
            cita = db.crear_cita(
                {
                    "usuario_id": 1,
                    "mascota_nombre": f"MascotaConc{idx}",
                    "propietario": f"Dueño {idx}",
                    "telefono": "999111222",
                    "servicio": "consulta",
                    "fecha": fecha,
                    "hora": hora,
                    "motivo": "Control concurrente",
                }
            )
            exitos.append(cita["id"])
        except ValueError as exc:
            rechazos.append(str(exc))

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(reservar, range(6)))

    assert len(exitos) == 3
    assert len(rechazos) == 3
