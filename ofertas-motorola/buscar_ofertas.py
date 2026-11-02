#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Buscador de ofertas: Motorola Edge 70 Fusion y Motorola Edge 60 Fusion en tiendas del Perú.

Uso rápido:
    python buscar_ofertas.py

Revisa las tiendas de la lista TIENDAS, busca los dos modelos y muestra solo las
ofertas que están POR DEBAJO del precio máximo de cada modelo:
    - Edge 70 Fusion: menos de S/ 1000
    - Edge 60 Fusion: menos de S/ 900

Para cuidar la garantía:
    - Por defecto solo cuenta productos vendidos por la propia tienda (no por
      vendedores externos del "marketplace").
    - Descarta equipos reacondicionados, usados, de exhibición o importados,
      y accesorios (fundas, micas, cargadores...).

Solo usa la biblioteca estándar de Python 3.8+ (no hay que instalar nada con pip).
Ejecuta "python buscar_ofertas.py --help" para ver todas las opciones.
"""

import argparse
import csv
import gzip
import html as html_lib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ===========================================================================
# CONFIGURACIÓN: aquí puedes cambiar precios, palabras y tiendas
# ===========================================================================

MODELOS = [
    {
        "id": "edge70",
        "nombre": "Motorola Edge 70 Fusion",
        "corto": "Edge 70",
        "precio_max": 1000.0,
        # Se compara con el nombre del producto ya en minúsculas y sin tildes.
        "patron": r"\bedge\s*70\s*fusion\b",
        "busquedas": ["motorola edge 70 fusion", "edge 70 fusion"],
    },
    {
        "id": "edge60",
        "nombre": "Motorola Edge 60 Fusion",
        "corto": "Edge 60",
        "precio_max": 900.0,
        "patron": r"\bedge\s*60\s*fusion\b",
        "busquedas": ["motorola edge 60 fusion", "edge 60 fusion"],
    },
]

# Si el nombre trae alguna de estas palabras, es un accesorio y no el celular.
PALABRAS_ACCESORIO = [
    "funda", "case", "carcasa", "estuche", "cover", "protector", "mica",
    "vidrio", "templado", "lamina", "hidrogel", "skin", "glass", "film",
    "cargador", "cable", "correa", "holder", "soporte", "repuesto", "tapa",
]

# Si el nombre trae alguna de estas palabras, normalmente NO tiene la garantía
# oficial de un equipo nuevo, así que se descarta.
PALABRAS_SIN_GARANTIA = [
    "reacondicionado", "reacondicionada", "refurbished", "refurb", "renovado",
    "renewed", "usado", "usada", "seminuevo", "semi nuevo", "segunda mano",
    "open box", "caja abierta", "exhibicion", "importado", "importada",
    "como nuevo",
]

# Un celular nuevo de estos modelos no cuesta menos que esto; si sale más barato
# casi seguro es un accesorio o un error de la tienda.
PRECIO_MINIMO_RAZONABLE = 300.0

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
TIEMPO_ESPERA = 25  # segundos por consulta


# ===========================================================================
# Utilidades
# ===========================================================================

class TiendaError(Exception):
    """Error al consultar una tienda (bloqueo, sin conexión, web cambiada...)."""


def normalizar(texto) -> str:
    """Minúsculas, sin tildes y solo letras/números/'+' separados por espacios."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9+]+", " ", texto).strip()


def compacto(texto) -> str:
    return normalizar(texto).replace(" ", "")


def contiene_palabra(texto_normalizado: str, palabras: List[str]) -> Optional[str]:
    for palabra in palabras:
        if re.search(r"\b" + re.escape(normalizar(palabra)) + r"\b", texto_normalizado):
            return palabra
    return None


def a_numero(valor) -> Optional[float]:
    """Convierte '1,049.90', '1.049', 'S/ 999' o 999 a número."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, list):
        return a_numero(valor[0]) if valor else None
    s = re.sub(r"[^\d.,]", "", str(valor))
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        miles = "." if decimal == "," else ","
        s = s.replace(miles, "").replace(decimal, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        partes = s.split(sep)
        if len(partes) > 2 or len(partes[-1]) == 3:
            s = s.replace(sep, "")       # separador de miles: 1,049 / 1.049
        else:
            s = s.replace(sep, ".")      # decimales: 999,90 / 999.9
    try:
        return float(s)
    except ValueError:
        return None


def soles(valor: Optional[float]) -> str:
    return "-" if valor is None else f"S/ {valor:,.2f}"


def descargar(url: str, es_html: bool = False) -> str:
    cabeceras = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            if es_html else "application/json, text/plain, */*"
        ),
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
    }
    peticion = urllib.request.Request(url, headers=cabeceras)
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA) as resp:
            cuerpo = resp.read()
            codificacion = (resp.headers.get("Content-Encoding") or "").lower()
            charset = resp.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429):
            raise TiendaError(
                f"la tienda rechazó la consulta (HTTP {e.code}); suele ser protección anti-bots"
            )
        if e.code == 404:
            raise TiendaError("dirección no encontrada (HTTP 404); la tienda pudo cambiar su web")
        raise TiendaError(f"error HTTP {e.code} de la tienda")
    except urllib.error.URLError as e:
        raise TiendaError(f"no se pudo conectar ({e.reason})")
    except OSError as e:  # timeouts, conexión cortada, etc.
        raise TiendaError(f"no se pudo conectar ({e.__class__.__name__}: {e})")

    try:
        if codificacion == "gzip":
            cuerpo = gzip.decompress(cuerpo)
        elif codificacion == "deflate":
            try:
                cuerpo = zlib.decompress(cuerpo)
            except zlib.error:
                cuerpo = zlib.decompress(cuerpo, -zlib.MAX_WBITS)
    except (OSError, zlib.error):
        raise TiendaError("respuesta comprimida dañada")
    return cuerpo.decode(charset, errors="replace")


def descargar_json(url: str):
    texto = descargar(url)
    try:
        return json.loads(texto)
    except ValueError:
        raise TiendaError("la tienda respondió algo que no es JSON (posible bloqueo o cambio en la web)")


def buscar_dicts(nodo, condicion, _profundidad: int = 0):
    """Recorre un JSON y devuelve los diccionarios que cumplan la condición."""
    if _profundidad > 60:
        return
    if isinstance(nodo, dict):
        if condicion(nodo):
            yield nodo
            return
        for valor in nodo.values():
            yield from buscar_dicts(valor, condicion, _profundidad + 1)
    elif isinstance(nodo, list):
        for valor in nodo:
            yield from buscar_dicts(valor, condicion, _profundidad + 1)


def json_tras_marcador(texto: str, marcador: str):
    """Lee el objeto JSON que viene después de 'marcador = ' dentro de un HTML."""
    pos = texto.find(marcador)
    if pos < 0:
        return None
    inicio = texto.find("{", pos)
    if inicio < 0:
        return None
    try:
        datos, _ = json.JSONDecoder().raw_decode(texto, inicio)
        return datos
    except ValueError:
        return None


def url_absoluta(base: str, enlace: str) -> str:
    enlace = (enlace or "").strip()
    if not enlace:
        return ""
    if enlace.startswith("//"):
        return "https:" + enlace
    if enlace.startswith("/"):
        return base.rstrip("/") + enlace
    if not enlace.startswith("http"):
        return base.rstrip("/") + "/" + enlace
    return enlace


def sin_etiquetas(fragmento: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", fragmento)
    return re.sub(r"\s+", " ", html_lib.unescape(texto)).strip()


# ===========================================================================
# Modelo de datos
# ===========================================================================

@dataclass
class Oferta:
    tienda: str
    nombre: str
    precio: float
    url: str
    vendedor: str = ""
    vendedor_es_tienda: bool = True
    marca: str = ""
    precio_lista: Optional[float] = None
    precio_tarjeta: Optional[float] = None
    garantia: Optional[str] = None
    stock: bool = True

    def precio_efectivo(self, con_tarjeta: bool) -> float:
        if con_tarjeta and self.precio_tarjeta and self.precio_tarjeta < self.precio:
            return self.precio_tarjeta
        return self.precio

    def descuento(self) -> Optional[int]:
        if self.precio_lista and self.precio_lista > self.precio:
            return round((1 - self.precio / self.precio_lista) * 100)
        return None

    def clave(self) -> Tuple[str, str]:
        return (self.tienda, self.url.split("?")[0].rstrip("/").lower() or self.nombre)


# ===========================================================================
# Tiendas
# ===========================================================================

class TiendaVTEX:
    """Tiendas hechas con VTEX (Plaza Vea, Oechsle, Efe, La Curacao, Coolbox...).

    Usa la API pública de búsqueda de VTEX, que devuelve precio, stock y
    vendedor de cada producto en JSON.
    """

    fragil = False

    def __init__(self, nombre: str, base: str, alias_vendedor=()):
        self.nombre = nombre
        self.base = base.rstrip("/")
        self.alias = [compacto(a) for a in alias_vendedor if compacto(a)]

    def es_vendedor_propio(self, id_vendedor, nombre_vendedor) -> bool:
        if str(id_vendedor).strip() == "1":   # en VTEX el vendedor "1" es la propia tienda
            return True
        c = compacto(nombre_vendedor)
        return bool(c) and any(a in c for a in self.alias)

    def _productos(self, termino: str) -> list:
        q = urllib.parse.quote(termino)
        direcciones = [
            f"{self.base}/api/catalog_system/pub/products/search?ft={q}&_from=0&_to=49",
            f"{self.base}/api/io/_v/api/intelligent-search/product_search/"
            f"?query={q}&count=50&page=1&locale=es-PE",
        ]
        errores, alguna_respondio = [], False
        for url in direcciones:
            try:
                datos = descargar_json(url)
            except TiendaError as e:
                errores.append(str(e))
                continue
            if isinstance(datos, dict):
                datos = datos.get("products")
            if isinstance(datos, list):
                alguna_respondio = True
                if datos:
                    return datos
        if errores and not alguna_respondio:
            raise TiendaError(errores[0])
        return []

    @staticmethod
    def _garantia(producto: dict) -> Optional[str]:
        def texto(valores):
            if isinstance(valores, list):
                return ", ".join(str(v) for v in valores if v)
            return str(valores) if valores else ""

        for clave, valores in producto.items():
            if "garant" in normalizar(clave) and texto(valores):
                return texto(valores)
        especificaciones = list(producto.get("properties") or [])
        for grupo in producto.get("specificationGroups") or []:
            especificaciones += grupo.get("specifications") or []
        for esp in especificaciones:
            if isinstance(esp, dict) and "garant" in normalizar(esp.get("name")):
                if texto(esp.get("values")):
                    return texto(esp.get("values"))
        return None

    def buscar(self, termino: str) -> List[Oferta]:
        ofertas = []
        for producto in self._productos(termino):
            if not isinstance(producto, dict):
                continue
            nombre = producto.get("productName") or ""
            enlace = producto.get("link") or ""
            if not enlace and producto.get("linkText"):
                enlace = f"/{producto['linkText']}/p"
            url = url_absoluta(self.base, enlace)
            garantia = self._garantia(producto)
            for item in producto.get("items") or []:
                variante = item.get("name") or ""
                nombre_completo = nombre
                if variante and normalizar(variante) not in normalizar(nombre):
                    nombre_completo = f"{nombre} ({variante})"
                for vendedor in item.get("sellers") or []:
                    oferta_com = vendedor.get("commertialOffer") or {}
                    precio = a_numero(oferta_com.get("Price"))
                    if not precio:
                        continue
                    cantidad = oferta_com.get("AvailableQuantity") or 0
                    disponible = cantidad > 0 or oferta_com.get("IsAvailable") is True
                    lista = a_numero(oferta_com.get("ListPrice"))
                    nombre_vendedor = vendedor.get("sellerName") or self.nombre
                    ofertas.append(Oferta(
                        tienda=self.nombre,
                        nombre=nombre_completo,
                        marca=producto.get("brand") or "",
                        precio=precio,
                        precio_lista=lista if lista and lista > precio else None,
                        url=url,
                        vendedor=nombre_vendedor,
                        vendedor_es_tienda=self.es_vendedor_propio(
                            vendedor.get("sellerId"), nombre_vendedor),
                        garantia=garantia,
                        stock=disponible,
                    ))
        return ofertas


class TiendaFalabella:
    """Falabella (incluye productos de Tottus y Sodimac). Lee los datos de la página de búsqueda."""

    fragil = True
    nombre = "Falabella / Tottus"
    base = "https://www.falabella.com.pe"
    propios = ("falabella", "tottus", "sodimac")

    def buscar(self, termino: str) -> List[Oferta]:
        url = f"{self.base}/falabella-pe/search?Ntt={urllib.parse.quote_plus(termino)}"
        pagina = descargar(url, es_html=True)
        m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', pagina, re.S)
        datos = None
        if m:
            try:
                datos = json.loads(m.group(1))
            except ValueError:
                datos = None
        if datos is None:
            raise TiendaError("la página no trajo los datos de productos (posible bloqueo anti-bots o cambio en la web)")

        ofertas = []
        es_producto = lambda d: isinstance(d.get("displayName"), str) and isinstance(d.get("prices"), list)
        for p in buscar_dicts(datos, es_producto):
            precio = lista = tarjeta = None
            for pr in p["prices"]:
                if not isinstance(pr, dict):
                    continue
                valor = a_numero(pr.get("price"))
                if not valor:
                    continue
                tipo = str(pr.get("type") or "").lower()
                if "cmr" in tipo:
                    tarjeta = valor if tarjeta is None else min(tarjeta, valor)
                elif pr.get("crossed"):
                    lista = valor if lista is None else max(lista, valor)
                else:
                    precio = valor if precio is None else min(precio, valor)
            if precio is None:
                precio = lista
                lista = None
            if not precio:
                continue
            vendedor = p.get("sellerName") or "Falabella"
            ofertas.append(Oferta(
                tienda=self.nombre,
                nombre=p["displayName"],
                marca=p.get("brand") or "",
                precio=precio,
                precio_lista=lista if lista and lista > precio else None,
                precio_tarjeta=tarjeta if tarjeta and tarjeta < precio else None,
                url=url_absoluta(self.base, p.get("url") or ""),
                vendedor=vendedor,
                vendedor_es_tienda=any(a in compacto(vendedor) for a in self.propios),
            ))
        return ofertas


class TiendaRipley:
    """Ripley. Lee los datos que trae la página de búsqueda."""

    fragil = True
    nombre = "Ripley"
    base = "https://simple.ripley.com.pe"

    def buscar(self, termino: str) -> List[Oferta]:
        url = f"{self.base}/search/{urllib.parse.quote(termino)}"
        pagina = descargar(url, es_html=True)
        datos = json_tras_marcador(pagina, "__PRELOADED_STATE__")
        if datos is None:
            raise TiendaError("la página no trajo los datos de productos (posible bloqueo anti-bots o cambio en la web)")

        def es_producto(d):
            precios = d.get("prices")
            return (isinstance(d.get("name"), str) and isinstance(precios, dict)
                    and any(k in precios for k in ("offerPrice", "listPrice", "cardPrice")))

        ofertas = []
        for p in buscar_dicts(datos, es_producto):
            pr = p["prices"]
            lista = a_numero(pr.get("listPrice"))
            precio = a_numero(pr.get("offerPrice")) or lista
            tarjeta = a_numero(pr.get("cardPrice"))
            if not precio:
                continue
            mercado = p.get("marketplace")
            vendedor = p.get("sellerName") or ""
            if not vendedor and isinstance(mercado, dict):
                vendedor = mercado.get("shopName") or mercado.get("name") or ""
            vendedor = vendedor or "Ripley"
            es_externo = bool(p.get("isMarketplaceProduct")) or "ripley" not in compacto(vendedor)
            ofertas.append(Oferta(
                tienda=self.nombre,
                nombre=p["name"],
                marca=p.get("manufacturer") or p.get("brand") or "",
                precio=precio,
                precio_lista=lista if lista and lista > precio else None,
                precio_tarjeta=tarjeta if tarjeta and tarjeta < precio else None,
                url=url_absoluta(self.base, p.get("url") or ""),
                vendedor=vendedor,
                vendedor_es_tienda=not es_externo,
                stock=not p.get("isOutOfStock", False),
            ))
        return ofertas


class TiendaHiraoka:
    """Hiraoka (web Magento). Lee la lista de resultados de la página de búsqueda."""

    fragil = True
    nombre = "Hiraoka"
    base = "https://hiraoka.com.pe"

    def buscar(self, termino: str) -> List[Oferta]:
        url = f"{self.base}/catalogsearch/result/?q={urllib.parse.quote_plus(termino)}"
        pagina = descargar(url, es_html=True)
        bloques = re.split(r'class="[^"]*\bproduct-item-info\b', pagina)[1:]
        ofertas = []
        for bloque in bloques:
            enlace = re.search(r'<a\b([^>]*\bproduct-item-link\b[^>]*)>(.*?)</a>', bloque, re.S)
            if not enlace:
                continue
            href = re.search(r'href="([^"]+)"', enlace.group(1))
            nombre = sin_etiquetas(enlace.group(2))
            precio = lista = None
            for etiqueta in re.finditer(r'<[^>]*\bdata-price-amount="([\d.]+)"[^>]*>', bloque):
                tipo = re.search(r'data-price-type="(\w+)"', etiqueta.group(0))
                tipo = tipo.group(1) if tipo else ""
                valor = a_numero(etiqueta.group(1))
                if tipo == "oldPrice" and lista is None:
                    lista = valor
                elif tipo in ("finalPrice", "") and precio is None:
                    precio = valor
            if not nombre or not precio:
                continue
            agotado = re.search(r"stock\s+unavailable|agotado", bloque, re.I) is not None
            ofertas.append(Oferta(
                tienda=self.nombre,
                nombre=nombre,
                precio=precio,
                precio_lista=lista if lista and lista > precio else None,
                url=html_lib.unescape(href.group(1)) if href else url,
                vendedor="Hiraoka",
                vendedor_es_tienda=True,
                stock=not agotado,
            ))
        return ofertas


# Lista de tiendas que se revisan. Para quitar una, bórrala o ponle "#" delante.
# Para agregar otra tienda VTEX: TiendaVTEX("Nombre", "https://www.dominio.pe", alias_vendedor=("nombre",))
TIENDAS = [
    TiendaVTEX("Plaza Vea", "https://www.plazavea.com.pe", alias_vendedor=("plaza vea", "plazavea", "supermercados peruanos")),
    TiendaVTEX("Efe", "https://www.efe.com.pe", alias_vendedor=("efe", "conecta retail")),
    TiendaVTEX("La Curacao", "https://www.lacuracao.pe", alias_vendedor=("curacao", "conecta retail")),
    TiendaVTEX("Oechsle", "https://www.oechsle.pe", alias_vendedor=("oechsle",)),
    TiendaVTEX("Coolbox", "https://www.coolbox.pe", alias_vendedor=("coolbox",)),
    TiendaVTEX("Motorola (tienda oficial)", "https://www.motorola.com/pe", alias_vendedor=("motorola", "lenovo")),
    TiendaFalabella(),
    TiendaRipley(),
    TiendaHiraoka(),
]


# ===========================================================================
# Búsqueda y filtros
# ===========================================================================

@dataclass
class ResultadoTienda:
    tienda: object
    ofertas: List[Oferta] = field(default_factory=list)
    errores: List[str] = field(default_factory=list)
    consultas: int = 0


def consultar_tienda(tienda, modelos) -> ResultadoTienda:
    resultado = ResultadoTienda(tienda=tienda)
    vistas = set()
    for modelo in modelos:
        for termino in modelo["busquedas"]:
            resultado.consultas += 1
            try:
                for oferta in tienda.buscar(termino):
                    clave = (oferta.url, oferta.nombre, oferta.vendedor, oferta.precio)
                    if clave not in vistas:
                        vistas.add(clave)
                        resultado.ofertas.append(oferta)
            except TiendaError as e:
                if str(e) not in resultado.errores:
                    resultado.errores.append(str(e))
            except Exception as e:  # nunca dejar que una tienda tumbe todo el programa
                resultado.errores.append(f"error inesperado: {e.__class__.__name__}: {e}")
    return resultado


def identificar_modelo(oferta: Oferta, modelos) -> Tuple[Optional[dict], Optional[str]]:
    """Devuelve (modelo, motivo_de_descarte). motivo es None si la oferta es válida."""
    nombre = normalizar(oferta.nombre)
    for modelo in modelos:
        coincide = re.search(modelo["patron"], nombre)
        if coincide:
            break
    else:
        return None, "otro producto"

    # "Fusion+" o "Fusion Plus" es otro modelo; "Fusion + audífonos" es un combo válido.
    resto = nombre[coincide.end():]
    if resto.startswith("+") or re.match(r"\s*plus\b", resto):
        return None, "es la versión Fusion+ (otro modelo)"
    marca = normalizar(oferta.marca)
    if marca and "motorola" not in marca and "moto" not in marca.split():
        return modelo, f"marca {oferta.marca} (accesorio)"
    palabra = contiene_palabra(nombre, PALABRAS_ACCESORIO)
    if palabra:
        return modelo, f"accesorio ('{palabra}')"
    palabra = contiene_palabra(nombre, PALABRAS_SIN_GARANTIA)
    if palabra:
        return modelo, f"sin garantía de equipo nuevo ('{palabra}')"
    if not oferta.stock:
        return modelo, "sin stock"
    if oferta.precio < PRECIO_MINIMO_RAZONABLE:
        return modelo, "precio demasiado bajo (posible accesorio o error)"
    return modelo, None


@dataclass
class Evaluacion:
    cumplen: List[Tuple[Oferta, dict]] = field(default_factory=list)
    # por tienda: {"min": {modelo_id: precio}, "externas_baratas": n}
    por_tienda: Dict[str, dict] = field(default_factory=dict)


def evaluar(resultados: List[ResultadoTienda], modelos, con_tarjeta=False,
            incluir_marketplace=False) -> Evaluacion:
    ev = Evaluacion()
    mejores: Dict[Tuple[str, str], Tuple[Oferta, dict]] = {}
    for res in resultados:
        info = {"min": {}, "externas_baratas": 0, "del_modelo": 0}
        ev.por_tienda[res.tienda.nombre] = info
        for oferta in res.ofertas:
            modelo, motivo = identificar_modelo(oferta, modelos)
            if modelo is None or motivo:
                continue
            precio = oferta.precio_efectivo(con_tarjeta)
            barata = precio < modelo["precio_max"]
            if not oferta.vendedor_es_tienda and not incluir_marketplace:
                if barata:
                    info["externas_baratas"] += 1
                continue
            info["del_modelo"] += 1
            actual = info["min"].get(modelo["id"])
            if actual is None or precio < actual:
                info["min"][modelo["id"]] = precio
            if not barata:
                continue
            clave = oferta.clave()
            previa = mejores.get(clave)
            if previa is None or precio < previa[0].precio_efectivo(con_tarjeta):
                mejores[clave] = (oferta, modelo)
    ev.cumplen = sorted(mejores.values(), key=lambda om: om[0].precio_efectivo(con_tarjeta))
    return ev


def buscar_todo(tiendas, modelos) -> List[ResultadoTienda]:
    with ThreadPoolExecutor(max_workers=max(1, len(tiendas))) as hilos:
        return list(hilos.map(lambda t: consultar_tienda(t, modelos), tiendas))


# ===========================================================================
# Reporte
# ===========================================================================

LINEA = "=" * 78


def imprimir_reporte(resultados, ev: Evaluacion, modelos, con_tarjeta, incluir_marketplace,
                     nuevas=None):
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    print()
    print(LINEA)
    print(f" OFERTAS MOTOROLA EDGE FUSION  -  {ahora}")
    print("   " + "   |   ".join(f"{m['corto']} Fusion: menos de {soles(m['precio_max'])}" for m in modelos))
    notas = ["solo vendido por la tienda" if not incluir_marketplace else "incluye vendedores externos"]
    if con_tarjeta:
        notas.append("cuenta precio con tarjeta de la tienda")
    print("   (" + "; ".join(notas) + ")")
    print(LINEA)

    respondieron = sum(1 for r in resultados if r.ofertas or not r.errores)
    if respondieron == 0:
        print()
        print(" No se pudo revisar ninguna tienda. Revisa tu conexión a internet")
        print(" (abajo está el motivo de cada tienda).")

    for modelo in modelos:
        lista = [o for o, m in ev.cumplen if m["id"] == modelo["id"]]
        if respondieron == 0:
            break
        print()
        print(f">> {modelo['nombre']}  (menos de {soles(modelo['precio_max'])})")
        if not lista:
            print(f"   Ninguna oferta por debajo de ese precio en las {respondieron} tienda(s) que respondieron.")
            continue
        for i, o in enumerate(lista, 1):
            precio = o.precio_efectivo(con_tarjeta)
            linea = f"   {i}) {soles(precio):>12}"
            if precio != o.precio:
                linea += f" con tarjeta (normal {soles(o.precio)})"
            if o.precio_lista:
                linea += f"   antes {soles(o.precio_lista)} (-{o.descuento()}%)"
            linea += f"   {o.tienda.upper()}"
            if i == 1:
                linea += "   <-- MEJOR PRECIO"
            if nuevas is not None and o.clave() in nuevas:
                linea += "   [NUEVA]"
            print(linea)
            print(f"      {o.nombre}")
            detalle = f"      Vendido por: {o.vendedor}"
            if not o.vendedor_es_tienda:
                detalle += " (vendedor externo: revisa su garantía)"
            if o.precio_tarjeta and not con_tarjeta:
                detalle += f"   |   con tarjeta: {soles(o.precio_tarjeta)}"
            if o.garantia:
                detalle += f"   |   Garantía: {o.garantia}"
            print(detalle)
            print(f"      {o.url}")

    print()
    print("-- Estado de cada tienda " + "-" * 53)
    encabezado_min = " / ".join(f"más barato {m['corto']}" for m in modelos)
    print(f"   {'Tienda':<26} {'Resultado':<14} {encabezado_min}")
    aviso_externas = False
    for res in resultados:
        info = ev.por_tienda.get(res.tienda.nombre, {})
        minimos = " / ".join(soles(info.get("min", {}).get(m["id"])) for m in modelos)
        if res.errores and not res.ofertas:
            estado = "NO SE PUDO"
        elif res.errores:
            estado = "PARCIAL"
        else:
            estado = "OK"
        print(f"   {res.tienda.nombre:<26} {estado:<14} {minimos}")
        if res.errores and not res.ofertas:
            print(f"      motivo: {res.errores[0]}")
        elif res.errores:
            print(f"      aviso: {res.errores[0]}")
        elif not res.ofertas and getattr(res.tienda, "fragil", False):
            print("      aviso: 0 productos; si se repite siempre, la web pudo cambiar de diseño")
        if info.get("externas_baratas"):
            aviso_externas = True
            print(f"      +{info['externas_baratas']} oferta(s) bajo el precio de vendedores externos (ocultas)")
    if aviso_externas:
        print("   Para verlas usa:  python buscar_ofertas.py --incluir-marketplace")
    print()


def guardar_csv(ruta: str, ev: Evaluacion, con_tarjeta: bool):
    nuevo = True
    try:
        with open(ruta, "r", encoding="utf-8-sig"):
            nuevo = False
    except OSError:
        pass
    with open(ruta, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["fecha", "modelo", "tienda", "precio", "precio_antes", "descuento_%",
                        "precio_tarjeta", "vendedor", "vendido_por_la_tienda", "garantia",
                        "producto", "url"])
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        for o, m in ev.cumplen:
            w.writerow([fecha, m["nombre"], o.tienda, f"{o.precio_efectivo(con_tarjeta):.2f}",
                        f"{o.precio_lista:.2f}" if o.precio_lista else "", o.descuento() or "",
                        f"{o.precio_tarjeta:.2f}" if o.precio_tarjeta else "", o.vendedor,
                        "si" if o.vendedor_es_tienda else "no", o.garantia or "", o.nombre, o.url])


# ===========================================================================
# Programa principal
# ===========================================================================

def leer_argumentos(argv=None):
    p = argparse.ArgumentParser(
        description="Busca ofertas del Motorola Edge 70 Fusion y Edge 60 Fusion en tiendas del Perú.")
    p.add_argument("--max-70", type=float, default=None, metavar="SOLES",
                   help="precio máximo para el Edge 70 Fusion (por defecto 1000)")
    p.add_argument("--max-60", type=float, default=None, metavar="SOLES",
                   help="precio máximo para el Edge 60 Fusion (por defecto 900)")
    p.add_argument("--con-tarjeta", action="store_true",
                   help="usar también el precio con tarjeta de la tienda (CMR, Ripley...) si es menor")
    p.add_argument("--incluir-marketplace", action="store_true",
                   help="incluir productos de vendedores externos (marketplace); su garantía la da ese vendedor")
    p.add_argument("--tiendas", metavar="LISTA",
                   help='revisar solo algunas tiendas, separadas por coma. Ej: --tiendas "plaza vea,efe,curacao"')
    p.add_argument("--csv", metavar="ARCHIVO",
                   help="guardar las ofertas encontradas en un archivo CSV (se abre con Excel)")
    p.add_argument("--cada", type=float, metavar="MINUTOS",
                   help="repetir la búsqueda cada X minutos y avisar cuando aparezca una oferta nueva")
    return p.parse_args(argv)


def preparar_modelos(args):
    modelos = [dict(m) for m in MODELOS]
    for m in modelos:
        if m["id"] == "edge70" and args.max_70:
            m["precio_max"] = args.max_70
        if m["id"] == "edge60" and args.max_60:
            m["precio_max"] = args.max_60
    return modelos


def elegir_tiendas(filtro: Optional[str]):
    if not filtro:
        return list(TIENDAS)
    pedidas = [compacto(x) for x in filtro.split(",") if compacto(x)]
    elegidas = [t for t in TIENDAS if any(p in compacto(t.nombre) for p in pedidas)]
    if not elegidas:
        nombres = ", ".join(t.nombre for t in TIENDAS)
        sys.exit(f"No reconozco esas tiendas. Las disponibles son: {nombres}")
    return elegidas


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

    args = leer_argumentos(argv)
    modelos = preparar_modelos(args)
    tiendas = elegir_tiendas(args.tiendas)

    vistas_antes = None
    while True:
        print(f"\nRevisando {len(tiendas)} tiendas: {', '.join(t.nombre for t in tiendas)} ...")
        resultados = buscar_todo(tiendas, modelos)
        ev = evaluar(resultados, modelos, args.con_tarjeta, args.incluir_marketplace)

        nuevas = None
        if vistas_antes is not None:
            nuevas = {o.clave() for o, _ in ev.cumplen} - vistas_antes
        imprimir_reporte(resultados, ev, modelos, args.con_tarjeta, args.incluir_marketplace, nuevas)
        if args.csv and ev.cumplen:
            guardar_csv(args.csv, ev, args.con_tarjeta)
            print(f"Ofertas guardadas en {args.csv}")

        if not args.cada:
            return 0 if ev.cumplen else 1
        if nuevas:
            print(f"\a*** {len(nuevas)} oferta(s) NUEVA(S) desde la última revisión ***")
        vistas_antes = (vistas_antes or set()) | {o.clave() for o, _ in ev.cumplen}
        print(f"Próxima revisión en {args.cada:g} minuto(s). Ctrl+C para salir.")
        try:
            time.sleep(args.cada * 60)
        except KeyboardInterrupt:
            print("\nListo, búsqueda detenida.")
            return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nBúsqueda cancelada.")
        sys.exit(130)
