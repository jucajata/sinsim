"""Catálogo único de errores de dominio (constitución V).

Cada código lleva su estado HTTP, su código de salida del CLI y un mensaje al usuario en
español, accionable y sin jerga interna. La API los convierte en Problem Details (RFC 9457)
y el CLI en códigos de salida 0–4.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ExitCode(IntEnum):
    """Códigos de salida del CLI (constitución V)."""

    OK = 0
    GENERAL = 1
    USAGE = 2
    NETWORK = 3
    VALIDATION = 4


@dataclass(frozen=True)
class ErrorSpec:
    """Definición de un código de error del catálogo."""

    code: str
    title: str
    http_status: int
    exit_code: ExitCode
    user_message: str


CATALOG: dict[str, ErrorSpec] = {
    spec.code: spec
    for spec in (
        ErrorSpec(
            "SNAPSHOT_NOT_FOUND",
            "Snapshot no encontrado",
            404,
            ExitCode.GENERAL,
            "No hay datos para esa fecha. Elige otra con `sinsim snapshots list` o ejecuta "
            "`sinsim scrape --fecha YYYY-MM-DD`.",
        ),
        ErrorSpec(
            "SNAPSHOT_EXISTS",
            "El snapshot ya existe",
            409,
            ExitCode.GENERAL,
            "Ya existe un snapshot para esa fecha y los snapshots son inmutables. "
            "No se modificó nada.",
        ),
        ErrorSpec(
            "SCRAPE_IN_PROGRESS",
            "Ya hay una descarga en curso",
            409,
            ExitCode.GENERAL,
            "Ya se está descargando otra fecha. Espera a que termine e inténtalo de nuevo.",
        ),
        ErrorSpec(
            "SCRAPE_JOB_NOT_FOUND",
            "Descarga no encontrada",
            404,
            ExitCode.GENERAL,
            "No hay ninguna descarga con ese identificador. Las descargas solo se recuerdan "
            "mientras la API sigue encendida.",
        ),
        ErrorSpec(
            "SNAPSHOT_CORRUPTED",
            "Snapshot alterado",
            409,
            ExitCode.GENERAL,
            "El contenido del snapshot no coincide con su manifiesto, así que no se usa. "
            "Restáuralo desde git o genera uno nuevo con `sinsim scrape`.",
        ),
        ErrorSpec(
            "OPERATING_POINT_MISSING",
            "Falta el punto de operación",
            404,
            ExitCode.GENERAL,
            "Esa fecha no tiene despacho programado o pronóstico de demanda. "
            "Ejecuta `sinsim scrape --fecha YYYY-MM-DD` para obtenerlos.",
        ),
        ErrorSpec(
            "BASEMAP_NOT_FOUND",
            "Mapa base no disponible",
            404,
            ExitCode.GENERAL,
            "No se encontró el mapa base en `data/geo/`. Restáuralo desde git; la disposición "
            "lógica sigue disponible.",
        ),
        ErrorSpec(
            "CASE_NOT_FOUND",
            "Caso no encontrado",
            404,
            ExitCode.GENERAL,
            "No existe un caso con ese identificador. Constrúyelo de nuevo.",
        ),
        ErrorSpec(
            "RUN_NOT_FOUND",
            "Ejecución no encontrada",
            404,
            ExitCode.GENERAL,
            "No existe una ejecución con ese identificador.",
        ),
        ErrorSpec(
            "PERIOD_OUT_OF_RANGE",
            "Periodo fuera de rango",
            422,
            ExitCode.USAGE,
            "El periodo debe estar entre 1 y 24.",
        ),
        ErrorSpec(
            "INVALID_DATE",
            "Fecha inválida",
            400,
            ExitCode.USAGE,
            "La fecha debe tener el formato YYYY-MM-DD y no puede ser posterior a mañana: XM "
            "publica el despacho programado la víspera.",
        ),
        ErrorSpec(
            "PARAM_MISSING",
            "Parámetro faltante",
            422,
            ExitCode.VALIDATION,
            "A un elemento le falta un parámetro obligatorio. Revisa el reporte de calidad.",
        ),
        ErrorSpec(
            "PARATEC_SCHEMA_CHANGED",
            "PARATEC cambió de estructura",
            502,
            ExitCode.VALIDATION,
            "La respuesta de PARATEC no tiene la estructura esperada. No se guardó nada. "
            "Puede que XM haya cambiado el formato; revisa el detalle del error.",
        ),
        ErrorSpec(
            "XM_FILE_SCHEMA_CHANGED",
            "Archivo de XM con estructura inesperada",
            502,
            ExitCode.VALIDATION,
            "Un archivo de despacho o demanda de XM no tiene el formato esperado. "
            "No se guardó nada; revisa el detalle del error.",
        ),
        ErrorSpec(
            "XM_FILE_NOT_FOUND",
            "Archivo de XM no disponible",
            404,
            ExitCode.GENERAL,
            "XM no tiene publicado ese archivo para la fecha pedida. Comprueba que la fecha "
            "ya esté publicada (el despacho se publica el día anterior) e inténtalo de nuevo.",
        ),
        ErrorSpec(
            "DISPATCH_TOTAL_MISMATCH",
            "El despacho no cuadra con su total",
            502,
            ExitCode.VALIDATION,
            "La suma de los recursos del despacho no coincide con la fila Total del archivo. "
            "No se guardó nada.",
        ),
        ErrorSpec(
            "EQUIVALENCE_OVERLAP",
            "Equivalencias con vigencias solapadas",
            500,
            ExitCode.VALIDATION,
            "Una tabla de equivalencias tiene dos filas vigentes para la misma clave. "
            "Corrige las fechas de vigencia.",
        ),
        ErrorSpec(
            "NETWORK_ERROR",
            "Error de red",
            503,
            ExitCode.NETWORK,
            "No se pudo conectar con PARATEC o con el portal de XM. Revisa tu conexión e "
            "inténtalo de nuevo; los snapshots existentes no se tocaron.",
        ),
        ErrorSpec(
            "PHYSICAL_CHECK_FAILED",
            "Validación física fallida",
            400,
            ExitCode.VALIDATION,
            "El caso tiene valores físicamente imposibles (por ejemplo una impedancia nula). "
            "Revisa el reporte de calidad antes de simular.",
        ),
        ErrorSpec(
            "REQUEST_INVALID",
            "Petición inválida",
            422,
            ExitCode.USAGE,
            "La petición no cumple el esquema. Revisa los campos indicados.",
        ),
        ErrorSpec(
            "HOST_NOT_ALLOWED",
            "Host no permitido",
            400,
            ExitCode.USAGE,
            "La API de sinsim solo atiende peticiones dirigidas a 127.0.0.1 o localhost. Abre la "
            "interfaz en http://127.0.0.1 con el puerto que indicó `sinsim serve`.",
        ),
        ErrorSpec(
            "ORIGIN_NOT_ALLOWED",
            "Origen no permitido",
            403,
            ExitCode.USAGE,
            "La API de sinsim solo acepta cambios hechos desde su propia interfaz local. "
            "Una página externa no puede iniciar descargas ni construir casos.",
        ),
        ErrorSpec(
            "N1_BASE_INVALID",
            "El análisis N-1 necesita un flujo AC convergido",
            422,
            ExitCode.VALIDATION,
            "El análisis N-1 se hace sobre un flujo AC que convergió. Corre el flujo AC primero.",
        ),
        ErrorSpec(
            "N1_IN_PROGRESS",
            "Ya hay un análisis N-1 en curso",
            409,
            ExitCode.GENERAL,
            "Ya hay un análisis N-1 en curso y ocupa casi todos los núcleos del equipo. Espera a "
            "que termine e inténtalo de nuevo.",
        ),
        ErrorSpec(
            "N1_JOB_NOT_FOUND",
            "Análisis N-1 no encontrado",
            404,
            ExitCode.GENERAL,
            "No hay ningún análisis N-1 con ese identificador. Los análisis solo se recuerdan "
            "mientras la API sigue encendida.",
        ),
        ErrorSpec(
            "SC_BUS_NOT_FOUND",
            "Barra no encontrada para el cortocircuito",
            422,
            ExitCode.VALIDATION,
            "La barra pedida no existe en el caso. Usa el nombre como aparece en la tabla de "
            "barras (por ejemplo `SABANALARGA|230` o `SABANALARGA 220`).",
        ),
        ErrorSpec(
            "SC_NO_SOURCES",
            "Sin fuentes de cortocircuito",
            422,
            ExitCode.VALIDATION,
            "Ninguna unidad generadora tiene parámetros de cortocircuito en este snapshot. "
            "Genera uno nuevo con `sinsim scrape --fecha YYYY-MM-DD`.",
        ),
        ErrorSpec(
            "SC_NOT_FOUND",
            "Cortocircuito no calculado",
            404,
            ExitCode.GENERAL,
            "No hay un cálculo de cortocircuito guardado para este caso. Lánzalo con el botón "
            "«Cortocircuito» o con `sinsim sc`.",
        ),
        ErrorSpec(
            "INTERNAL_ERROR",
            "Error no previsto",
            500,
            ExitCode.GENERAL,
            "Ocurrió un error no previsto. Comparte el trace_id al reportarlo.",
        ),
    )
}


ERROR_TYPE_BASE = "https://github.com/jucajata/sinsim/errors/"
"""Prefijo del campo `type` de Problem Details (constitución V)."""


def problem_type_url(code: str) -> str:
    """URL `type` de un código del catálogo."""
    return ERROR_TYPE_BASE + code.lower().replace("_", "-")


class DomainError(Exception):
    """Error de dominio con código del catálogo.

    Args:
        code: Código del catálogo (`CATALOG`).
        detail: Explicación técnica en español, con nombres de archivos o entidades.
        user_message: Mensaje al usuario; si se omite, se usa el del catálogo.
    """

    def __init__(self, code: str, detail: str = "", user_message: str | None = None) -> None:
        """Crea el error y valida que el código exista en el catálogo."""
        if code not in CATALOG:
            msg = f"código de error desconocido: {code}"
            raise ValueError(msg)
        self.spec = CATALOG[code]
        self.code = code
        self.detail = detail
        self.user_message = user_message or self.spec.user_message
        super().__init__(f"{code}: {detail or self.spec.title}")

    @property
    def http_status(self) -> int:
        """Estado HTTP asociado al código."""
        return self.spec.http_status

    @property
    def exit_code(self) -> ExitCode:
        """Código de salida del CLI asociado al código."""
        return self.spec.exit_code

    @property
    def title(self) -> str:
        """Título corto del error."""
        return self.spec.title
