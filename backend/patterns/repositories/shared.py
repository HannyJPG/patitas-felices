"""Utilidades compartidas y adaptador de mensajería WhatsApp para repositorios SQL Server."""
from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import hmac
import os
import secrets
from typing import Any, Dict, Optional
from urllib.parse import quote

_PBKDF2_PREFIX = "pbkdf2_sha256$"
_PBKDF2_ITERATIONS = 100000
_PREFIJOS_HONORIFICOS = {
    "dr.", "dr", "dra.", "dra", "sr.", "sr", "sra.", "sra",
    "lic.", "lic", "mg.", "mg", "mv.", "mv", "mvz.", "mvz", "m.v.",
}


def es_email_valido(email: str) -> bool:
    """Valida formato estricto de correo electrónico."""
    email_limpio = str(email or "").strip().lower()
    if (
        not email_limpio
        or any(ch.isspace() for ch in email_limpio)
        or email_limpio.count("@") != 1
    ):
        return False
    local, domain = email_limpio.split("@", 1)
    if not local or not domain or "." not in domain:
        return False
    return all(bool(part) for part in domain.split("."))


def separar_nombres_apellidos(
    nombre_completo: str,
    nombres: Optional[str] = None,
    apellidos: Optional[str] = None,
    default_nombre: str = "Usuario",
) -> tuple[str, str]:
    """
    Separa de forma limpia nombres y apellidos removiendo prefijos honoríficos
    ('Dr.', 'Dra.', 'Lic.', etc.) cuando no se envían campos explícitos.
    """
    nom_exp = str(nombres or "").strip()
    ape_exp = str(apellidos or "").strip()
    if nom_exp:
        tokens = [t for t in nom_exp.split() if t]
        while len(tokens) > 1 and tokens[0].lower() in _PREFIJOS_HONORIFICOS:
            tokens.pop(0)
        nom_clean = " ".join(tokens).strip() or nom_exp
        if not ape_exp and " " in nom_clean:
            nom_clean, ape_exp = nom_clean.split(" ", 1)
        return nom_clean, ape_exp

    tokens = [t for t in str(nombre_completo or "").strip().split() if t]
    while len(tokens) > 1 and tokens[0].lower() in _PREFIJOS_HONORIFICOS:
        tokens.pop(0)
    if not tokens:
        return default_nombre, ""
    if len(tokens) == 1:
        return tokens[0], ape_exp
    return tokens[0], " ".join(tokens[1:])


def hashear_password(password_plano: str) -> str:
    """Genera un hash criptográfico PBKDF2-HMAC-SHA256 con sal aleatoria de 128 bits."""
    if not password_plano or str(password_plano).startswith(_PBKDF2_PREFIX):
        return str(password_plano)
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", str(password_plano).encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS
    ).hex()
    return f"{_PBKDF2_PREFIX}{salt}${dk}"


def verificar_password(password_plano: str, hash_almacenado: str) -> bool:
    """
    Verifica de forma segura (tiempo constante) una contraseña contra su hash PBKDF2-SHA256.
    Rechaza hashes heredados en texto plano sin prefijo pbkdf2_sha256$.
    """
    if not password_plano or not hash_almacenado:
        return False
    hash_str = str(hash_almacenado)
    plano_str = str(password_plano)
    if not hash_str.startswith(_PBKDF2_PREFIX):
        return False
    partes = hash_str.split("$", 2)
    if len(partes) != 3:
        return False
    _, salt, digest_esperado = partes
    dk = hashlib.pbkdf2_hmac(
        "sha256", plano_str.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS
    ).hex()
    return hmac.compare_digest(dk, digest_esperado)


class IWhatsAppNotificationAdapter(ABC):
    """Target Interface: Define el contrato que la clínica necesita para notificar."""

    @abstractmethod
    def generar_enlace_cita(self, datos_cita: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    def generar_enlace_boleta(self, numero_boleta: str, cliente: str, total: float) -> str:
        pass


class WhatsAppAdapter(IWhatsAppNotificationAdapter):
    """
    Adapter concreto: Adapta los diccionarios de negocio de la clínica al formato
    requerido por la API web de WhatsApp (https://wa.me/<telefono>?text=<mensaje_codificado>).
    """

    SERVICIOS_NOMBRES = {
        "consulta-general": "Consulta general",
        "vacunacion": "Vacunación",
        "desparasitacion": "Desparasitación",
        "control": "Control y seguimiento",
    }
    SERVICIOS_CODIGOS = {nombre: codigo for codigo, nombre in SERVICIOS_NOMBRES.items()}

    def __init__(self, numero_clinica: Optional[str] = None) -> None:
        self.numero_clinica = numero_clinica or os.getenv("CLINICA_WHATSAPP", "51990853697")

    def _construir_url(self, mensaje: str) -> str:
        texto_codificado = quote(mensaje, safe="")
        return f"https://wa.me/{self.numero_clinica}?text={texto_codificado}"

    def generar_enlace_cita(self, datos_cita: Dict[str, Any]) -> str:
        fecha_raw = str(datos_cita.get("fecha", ""))
        partes = fecha_raw.split("-")
        fecha_formateada = f"{partes[2]}/{partes[1]}/{partes[0]}" if len(partes) == 3 else fecha_raw
        servicio_clave = datos_cita.get("servicio", "")
        servicio_legible = self.SERVICIOS_NOMBRES.get(servicio_clave, servicio_clave)
        lineas = [
            "Hola, Patitas Felices. Quisiera solicitar una cita veterinaria.",
            "",
            f"Propietario: {datos_cita.get('propietario', '')}",
            f"Teléfono de contacto: {datos_cita.get('telefono', '')}",
            f"Mascota: {datos_cita.get('mascota_nombre') or datos_cita.get('mascota', '')}",
            f"Servicio: {servicio_legible}",
            f"Fecha deseada: {fecha_formateada}",
            f"Hora deseada: {datos_cita.get('hora', '')} (Lima, Perú)",
            "Duración: 30 minutos",
            f"Motivo: {datos_cita.get('motivo', '')}",
            "",
            "¿Podrían confirmar si este horario está disponible?",
        ]
        return self._construir_url("\n".join(lineas))

    def generar_enlace_boleta(self, numero_boleta: str, cliente: str, total: float) -> str:
        mensaje = (
            f"Hola, Patitas Felices. Soy {cliente}. Acabo de realizar la compra con "
            f"Boleta N° {numero_boleta} por un total de S/ {total:.2f}. Solicito coordinación de entrega."
        )
        return self._construir_url(mensaje)
