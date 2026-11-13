"""Repositorios de dominio desacoplados para Microsoft SQL Server (Patrón Repository + Adapter)."""

from .citas_repo import CitasRepositoryMixin
from .mascotas_repo import MascotasRepositoryMixin
from .shared import (
    _PBKDF2_PREFIX,
    IWhatsAppNotificationAdapter,
    WhatsAppAdapter,
    es_email_valido,
    hashear_password,
    separar_nombres_apellidos,
    verificar_password,
)
from .tienda_repo import TiendaRepositoryMixin
from .usuarios_repo import UsuariosRepositoryMixin

__all__ = [
    "_PBKDF2_PREFIX",
    "CitasRepositoryMixin",
    "IWhatsAppNotificationAdapter",
    "MascotasRepositoryMixin",
    "TiendaRepositoryMixin",
    "UsuariosRepositoryMixin",
    "WhatsAppAdapter",
    "es_email_valido",
    "hashear_password",
    "separar_nombres_apellidos",
    "verificar_password",
]
