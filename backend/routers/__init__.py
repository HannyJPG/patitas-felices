"""Registro de routers modulares de la API Patitas Felices."""

from . import admin, auth, bd, citas, doctor, tienda

__all__ = ["admin", "auth", "bd", "citas", "doctor", "tienda"]
