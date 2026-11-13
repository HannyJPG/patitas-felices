"""Router de Inspección de las 16 Tablas SQL Server y Ruta /visor-bd."""
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse

from ..patterns import ErrorConexionSQLServer, ErrorConsultaSQLServer
from ..schemas import TablasBDResponse
from .deps import manejar_proxy

router = APIRouter()

_DIST_VISOR_HTML = (
    Path(__file__).resolve().parent.parent.parent / "dist" / "visor-bd" / "index.html"
)


@router.get("/api/bd/tablas", tags=["Base de Datos (16 Tablas)"], response_model=TablasBDResponse)
def obtener_tablas_completas(
    request: Request,
    limit: Optional[int] = None,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    manejar_proxy(request, authorization, "ver_crm_dashboard")
    adaptador_bd = request.app.state.db
    try:
        if limit is not None:
            tablas = adaptador_bd.obtener_todas_las_16_tablas(limit_per_table=limit)
        else:
            tablas = adaptador_bd.obtener_todas_las_16_tablas()
    except ErrorConexionSQLServer as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ErrorConsultaSQLServer as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    srv = getattr(adaptador_bd, "server", "localhost")
    db_name = getattr(adaptador_bd, "database", "PatitasFelices_DB")
    return {
        "total_tablas": len(tablas),
        "motor_bd": f"Microsoft SQL Server ({srv} / {db_name})",
        "tablas": tablas,
    }


@router.get("/visor-bd", tags=["Base de Datos (16 Tablas)"])
def visor_html_bd() -> Response:
    """Sirve la vista compilada de Astro para /visor-bd (con respaldo ligero si aún no existe dist/)."""
    if _DIST_VISOR_HTML.is_file():
        return FileResponse(str(_DIST_VISOR_HTML), media_type="text/html")
    html_respaldo = (
        "<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'>"
        "<title>Visor en Vivo de las 16 Tablas | Patitas Felices</title></head>"
        "<body><h1>Visor en Vivo de las 16 Tablas (DER)</h1>"
        "<p>Ejecuta <code>npm run build</code> para habilitar la interfaz Astro.</p>"
        "</body></html>"
    )
    return Response(content=html_respaldo, media_type="text/html")
