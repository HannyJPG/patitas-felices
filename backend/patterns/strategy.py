"""
PATRÓN STRATEGY + RBAC (Comportamiento - GoF)
Puntos de sustentación: 1, 5 y 6.
Propósito: Definir una familia de algoritmos de autorización según el rol del
Stakeholder (AdminRoleStrategy, DoctorRoleStrategy, ClientRoleStrategy).
Según quién inicie sesión, el contexto RBAC cambia dinámicamente qué acciones
puede ejecutar y qué vistas/menús le devuelve al Frontend Astro.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Set


class RoleAuthorizationStrategy(ABC):
    """Interfaz Strategy: Declara las operaciones comunes a todos los roles RBAC."""

    @abstractmethod
    def nombre_rol(self) -> str:
        pass

    @abstractmethod
    def permisos_permitidos(self) -> Set[str]:
        pass

    @abstractmethod
    def tiene_permiso(self, accion: str) -> bool:
        pass

    @abstractmethod
    def obtener_configuracion_vista(self) -> Dict[str, Any]:
        pass


class ClientRoleStrategy(RoleAuthorizationStrategy):
    """
    Estrategia concreta para el Cliente (Propietario de mascota):
    Acceso a Landing/Tienda, compra con Boleta PDF y agendamiento de citas.
    """

    PERMISOS: Set[str] = {
        "ver_tienda",
        "comprar_productos",
        "agendar_cita",
        "ver_mis_citas",
        "ver_mis_mascotas",
        "crear_mascota_cliente",
        "eliminar_mascota_cliente",
        "actualizar_documento_cliente",
        "cambiar_password",
        "ver_mis_compras",
        "solicitar_cambio_mascota",
        "ver_mis_solicitudes",
    }

    def nombre_rol(self) -> str:
        return "cliente"

    def permisos_permitidos(self) -> Set[str]:
        return set(self.PERMISOS)

    def tiene_permiso(self, accion: str) -> bool:
        return accion in self.PERMISOS

    def obtener_configuracion_vista(self) -> Dict[str, Any]:
        return {
            "rol": "cliente",
            "etiqueta": "Cliente / Propietario",
            "ruta_principal": "/tienda",
            "ruta_espacio": "/cliente",
            "vistas_disponibles": [
                {"nombre": "Mi perfil, mascotas y citas", "ruta": "/cliente"},
                {"nombre": "Tienda y farmacia", "ruta": "/tienda"},
                {"nombre": "Agendar cita", "ruta": "/agendar-cita"},
            ],
            "acciones": sorted(self.PERMISOS),
        }


class DoctorRoleStrategy(RoleAuthorizationStrategy):
    """
    Estrategia concreta para el Médico Veterinario (Doctor):
    Acceso a la Agenda Médica, Historial Clínico de pacientes y actualización de diagnósticos.
    """

    PERMISOS: Set[str] = {
        "ver_agenda_doctor",
        "ver_historial_clinico",
        "actualizar_diagnostico",
        "cambiar_estado_cita",
        "ver_tienda",
        "cambiar_password",
    }

    def nombre_rol(self) -> str:
        return "doctor"

    def permisos_permitidos(self) -> Set[str]:
        return set(self.PERMISOS)

    def tiene_permiso(self, accion: str) -> bool:
        return accion in self.PERMISOS

    def obtener_configuracion_vista(self) -> Dict[str, Any]:
        return {
            "rol": "doctor",
            "etiqueta": "Médico Veterinario",
            "ruta_principal": "/doctor",
            "ruta_espacio": "/doctor",
            "vistas_disponibles": [
                {"nombre": "Perfil profesional, agenda y pacientes", "ruta": "/doctor"},
                {"nombre": "Catálogo clínico", "ruta": "/tienda"},
            ],
            "acciones": sorted(self.PERMISOS),
        }


class AdminRoleStrategy(RoleAuthorizationStrategy):
    """
    Estrategia concreta para el Administrador de la Clínica:
    Control total del CRM/Dashboard, métricas financieras, usuarios (activar/inactivar),
    inventario, agenda médica y tienda.
    """

    PERMISOS: Set[str] = {
        "ver_crm_dashboard",
        "gestionar_usuarios",
        "crear_personal_admin",
        "cambiar_estado_usuario",
        "gestionar_inventario",
        "ver_reporte_ventas",
        "ver_agenda_doctor",
        "ver_historial_clinico",
        "actualizar_diagnostico",
        "cambiar_estado_cita",
        "ver_tienda",
        "comprar_productos",
        "agendar_cita",
        "ver_mis_citas",
        "ver_mis_mascotas",
        "crear_mascota_cliente",
        "eliminar_mascota_cliente",
        "actualizar_documento_cliente",
        "cambiar_password",
        "ver_mis_compras",
        "solicitar_cambio_mascota",
        "ver_mis_solicitudes",
        "gestionar_solicitudes_mascota",
        "resolver_solicitud_mascota",
    }

    def nombre_rol(self) -> str:
        return "admin"

    def permisos_permitidos(self) -> Set[str]:
        return set(self.PERMISOS)

    def tiene_permiso(self, accion: str) -> bool:
        return accion in self.PERMISOS

    def obtener_configuracion_vista(self) -> Dict[str, Any]:
        return {
            "rol": "admin",
            "etiqueta": "Administrador",
            "ruta_principal": "/admin",
            "ruta_espacio": "/admin-app",
            "vistas_disponibles": [
                {"nombre": "Aplicación administrativa", "ruta": "/admin-app"},
                {"nombre": "Agenda veterinaria", "ruta": "/doctor"},
                {"nombre": "Espacio del cliente", "ruta": "/cliente"},
                {"nombre": "Tienda veterinaria", "ruta": "/tienda"},
            ],
            "acciones": sorted(self.PERMISOS),
        }


class RBACContext:
    """
    Contexto del Patrón Strategy:
    Mantiene una referencia a una estrategia de rol y permite intercambiarla
    dinámicamente según el usuario autenticado.
    """

    _MAPA_ESTRATEGIAS: Dict[str, RoleAuthorizationStrategy] = {
        "admin": AdminRoleStrategy(),
        "doctor": DoctorRoleStrategy(),
        "cliente": ClientRoleStrategy(),
    }

    def __init__(self, rol: str = "cliente") -> None:
        self._strategy: RoleAuthorizationStrategy = self.resolver_estrategia(rol)

    @classmethod
    def resolver_estrategia(cls, rol: str) -> RoleAuthorizationStrategy:
        rol_limpio = (rol or "").strip().lower()
        if rol_limpio not in cls._MAPA_ESTRATEGIAS:
            raise ValueError(f"Rol RBAC no reconocido: '{rol}'")
        return cls._MAPA_ESTRATEGIAS[rol_limpio]

    def cambiar_estrategia(self, nueva_estrategia: RoleAuthorizationStrategy) -> None:
        self._strategy = nueva_estrategia

    def autorizar(self, accion: str) -> bool:
        return self._strategy.tiene_permiso(accion)

    def obtener_vista_y_permisos(self) -> Dict[str, Any]:
        return self._strategy.obtener_configuracion_vista()

    def listar_acciones(self) -> List[str]:
        return sorted(self._strategy.permisos_permitidos())
