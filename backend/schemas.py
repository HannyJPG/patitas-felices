"""Modelos Pydantic de solicitud y respuesta para OpenAPI / FastAPI."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# --- Contratos de entrada (request bodies) ---
class LoginRequest(BaseModel):
    email: str = Field(..., examples=["admin@patitasfelices.pe"])
    password: str = Field(..., examples=["admin123"])


class ItemCarritoRequest(BaseModel):
    producto_id: int = Field(..., examples=[1])
    cantidad: int = Field(..., ge=1, examples=[2])


class CheckoutRequest(BaseModel):
    cliente_nombre: Optional[str] = Field(default="", max_length=120, examples=["Lucía Fernández"])
    tipo_documento: Optional[str] = Field(default="DNI", examples=["DNI"])
    cliente_documento: str = Field(..., min_length=8, max_length=15, examples=["74859632"])
    metodo_pago: str = Field(default="Tarjeta / Yape", examples=["Yape / Plin"])
    items: List[ItemCarritoRequest]


class ActualizarDocumentoRequest(BaseModel):
    tipo_documento: str = Field(default="DNI", examples=["DNI"])
    documento: str = Field(..., min_length=8, max_length=11, examples=["74859632"])


class CitaRequest(BaseModel):
    usuario_id: Optional[int] = Field(default=None, examples=[1])
    mascota_id: Optional[int] = Field(default=None, examples=[1])
    propietario: str = Field(..., min_length=2, max_length=80, examples=["Lucía Fernández"])
    telefono: str = Field(..., min_length=9, max_length=20, examples=["912345678"])
    mascota_nombre: str = Field(..., min_length=1, max_length=60, examples=["Luna"])
    servicio: str = Field(..., examples=["consulta-general"])
    fecha: str = Field(..., examples=["2026-10-30"])
    hora: str = Field(..., examples=["10:30"])
    motivo: str = Field(..., min_length=10, max_length=1000, examples=["Control general y revisión de vacunas anuales."])


class CrearMascotaRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=60, examples=["Toby"])
    especie: str = Field(default="Perro", max_length=40, examples=["Perro"])
    raza: str = Field(default="Mestizo", max_length=60, examples=["Labrador"])
    edad: int = Field(default=1, ge=0, le=40, examples=[3])
    peso_kg: float = Field(default=5.0, ge=0.1, le=200.0, examples=[18.5])
    sexo: Optional[str] = Field(default="H", max_length=10, examples=["H"])
    historial_resumen: Optional[str] = Field(default="", max_length=500, examples=["Vacunas al día."])


class ActualizarCitaDoctorRequest(BaseModel):
    estado: str = Field(..., examples=["atendida"])
    diagnostico: str = Field(default="", examples=["Paciente estable, sin fiebre."])
    tratamiento: str = Field(default="", examples=["Control en 15 días y dieta blanda."])


class CambiarEstadoUsuarioRequest(BaseModel):
    estado: str = Field(..., examples=["inactivo"])


class RegistroRequest(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100, examples=["Juan Pérez"])
    email: str = Field(..., min_length=5, max_length=120, examples=["juan@ejemplo.com"])
    password: str = Field(..., min_length=6, max_length=100, examples=["segura123"])
    telefono: Optional[str] = Field(default="", max_length=25, examples=["987654321"])


class CrearPersonalRequest(BaseModel):
    nombre: Optional[str] = Field(default=None, max_length=100, examples=["Dra. Andrea Morales"])
    nombres: Optional[str] = Field(default=None, max_length=80, examples=["Andrea"])
    apellidos: Optional[str] = Field(default=None, max_length=80, examples=["Morales"])
    email: str = Field(..., min_length=5, max_length=120, examples=["andrea@patitasfelices.pe"])
    password: str = Field(..., min_length=6, max_length=100, examples=["doctor123"])
    rol: str = Field(..., examples=["doctor"])
    telefono: Optional[str] = Field(default="", max_length=25, examples=["990112233"])
    cmvp: Optional[str] = Field(default="", max_length=30, examples=["CMVP-12345"])
    especialidad: Optional[str] = Field(default="Medicina General", max_length=100, examples=["Dermatología"])


class CambiarPasswordRequest(BaseModel):
    password_actual: str = Field(..., min_length=1)
    password_nueva: str = Field(..., min_length=6)


class SolicitarCambioMascotaRequest(BaseModel):
    tipo: str = Field(..., examples=["editar", "eliminar"])
    motivo: str = Field(..., min_length=5, examples=["Cambio de peso y datos de vacunación"])
    datos_nuevos: Optional[Dict[str, Any]] = None


class ResolverSolicitudMascotaRequest(BaseModel):
    accion: str = Field(..., examples=["aprobar", "rechazar"])


# --- Contratos de respuesta (OpenAPI response_model) ---
class _FlexModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class HealthResponse(_FlexModel):
    status: str
    clinica: str
    patrones_activos: List[str]
    adaptador_bd: str


class RbacInfo(_FlexModel):
    rol: str
    etiqueta: str
    ruta_principal: str
    ruta_espacio: str
    vistas_disponibles: List[Any]
    acciones: List[str]


class AuthResponse(_FlexModel):
    mensaje: str
    token: str
    usuario: Dict[str, Any]
    rbac: RbacInfo


class SesionResponse(_FlexModel):
    usuario: Dict[str, Any]
    rbac: RbacInfo


class CatalogoProductosResponse(_FlexModel):
    total: int
    productos: List[Dict[str, Any]]


class DisponibilidadHorariosResponse(_FlexModel):
    fecha: str
    capacidad_por_turno: int
    horarios: Dict[str, Any]


class TablasBDResponse(_FlexModel):
    total_tablas: int
    motor_bd: str
    tablas: Dict[str, List[Dict[str, Any]]]
