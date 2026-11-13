"""Dependencias compartidas y manejo uniforme de errores Proxy/SQL Server para los routers."""
from typing import Any, Dict, Optional
from fastapi import HTTPException, Request

from ..patterns import (
    ErrorConexionSQLServer,
    ErrorConsultaSQLServer,
    ErrorRegistroDuplicadoSQLServer,
    ErrorSeguridadProxy,
)


def manejar_proxy(
    request: Request,
    token: Optional[str],
    accion: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ejecuta una acción protegida a través de AuthSessionProxy y traduce excepciones a HTTP."""
    proxy_seguridad = request.app.state.proxy
    try:
        return proxy_seguridad.ejecutar_accion(token, accion, params)
    except ErrorSeguridadProxy as exc:
        raise HTTPException(status_code=exc.codigo_http, detail=str(exc)) from exc
    except ErrorConexionSQLServer as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ErrorRegistroDuplicadoSQLServer) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ErrorConsultaSQLServer as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
