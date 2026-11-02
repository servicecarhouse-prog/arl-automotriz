# -*- coding: utf-8 -*-
"""Pruebas sin internet: se simulan las respuestas de las tiendas.

Ejecutar:  python -m unittest test_buscar_ofertas -v
"""
import contextlib
import io
import json
import unittest
from unittest import mock

import buscar_ofertas as bo


def producto_vtex(nombre, precio, lista=None, stock=5, vendedor_id="1", vendedor="Tienda",
                  marca="Motorola", link="https://tienda.pe/x/p", extra=None):
    p = {
        "productName": nombre,
        "brand": marca,
        "link": link,
        "items": [{
            "name": nombre,
            "sellers": [{
                "sellerId": vendedor_id,
                "sellerName": vendedor,
                "commertialOffer": {
                    "Price": precio,
                    "ListPrice": lista if lista is not None else precio,
                    "AvailableQuantity": stock,
                },
            }],
        }],
    }
    p.update(extra or {})
    return p


RESPUESTA_VTEX = [
    producto_vtex("Celular Motorola Edge 60 Fusion 8GB 256GB Azul", 849, 1299,
                  link="https://www.plazavea.com.pe/edge-60-azul/p",
                  extra={"Garantía": ["12 meses"]}),
    producto_vtex("Celular Motorola Edge 60 Fusion 8GB 256GB Rosa", 799, 1299, vendedor_id="seller77",
                  vendedor="Importaciones XYZ SAC", link="https://www.plazavea.com.pe/edge-60-rosa/p"),
    producto_vtex("Funda para Motorola Edge 60 Fusion", 39, marca="Genérico",
                  link="https://www.plazavea.com.pe/funda/p"),
    producto_vtex("Motorola Edge 70 Fusion 12GB 512GB", 1099, 1599,
                  link="https://www.plazavea.com.pe/edge-70/p"),
    producto_vtex("Motorola Edge 70 Fusion+ 12GB 512GB", 950,
                  link="https://www.plazavea.com.pe/edge-70-plus/p"),
    producto_vtex("Motorola Edge 60 Fusión Reacondicionado", 600,
                  link="https://www.plazavea.com.pe/edge-60-reac/p"),
    producto_vtex("Motorola Edge 60 Fusion Verde", 700, stock=0,
                  link="https://www.plazavea.com.pe/edge-60-verde/p"),
    producto_vtex("Motorola Edge 70 Fusión 8GB 256GB", 999,
                  link="https://www.plazavea.com.pe/edge-70-barato/p"),
]

HTML_FALABELLA = """<html><body><script id="__NEXT_DATA__" type="application/json">%s</script></body></html>""" % json.dumps({
    "props": {"pageProps": {"results": [
        {"displayName": "Celular Edge 60 Fusion 256GB 8GB", "brand": "MOTOROLA",
         "url": "https://www.falabella.com.pe/falabella-pe/product/1/edge-60",
         "sellerName": "TOTTUS",
         "prices": [
             {"type": "cmrPrice", "price": ["779"], "crossed": False},
             {"type": "internetPrice", "price": ["889"], "crossed": False},
             {"type": "normalPrice", "price": ["1,499"], "crossed": True},
         ]},
        {"displayName": "Celular Edge 70 Fusion 256GB", "brand": "MOTOROLA",
         "url": "/falabella-pe/product/2/edge-70", "sellerName": "PERU SMART S.A.C",
         "prices": [{"type": "internetPrice", "price": ["989"], "crossed": False}]},
    ]}}
})

HTML_RIPLEY = """<html><script>window.__PRELOADED_STATE__ = %s;</script></html>""" % json.dumps({
    "products": {"list": [
        {"name": "MOTOROLA EDGE 70 FUSION 256GB", "manufacturer": "MOTOROLA",
         "url": "/motorola-edge-70-fusion-pmp1", "isMarketplaceProduct": False,
         "prices": {"listPrice": 1599, "offerPrice": 1049, "cardPrice": 949}},
    ]}
})

HTML_HIRAOKA = """
<ol>
<li class="item product product-item"><div class="product-item-info" data-container="product-grid">
  <a class="product-item-link" href="https://hiraoka.com.pe/motorola-edge-60-fusion">
     Celular Motorola Edge 60 Fusion 256GB
  </a>
  <span id="p1" data-price-amount="879" data-price-type="finalPrice" class="price-wrapper"><span class="price">S/ 879.00</span></span>
  <span id="p2" data-price-amount="1199" data-price-type="oldPrice" class="price-wrapper"></span>
</div></li>
<li class="item product product-item"><div class="product-item-info">
  <a href="https://hiraoka.com.pe/edge-60-agotado" class="product-item-link">Motorola Edge 60 Fusion Negro</a>
  <span data-price-amount="799" data-price-type="finalPrice"></span>
  <div class="stock unavailable"><span>Agotado</span></div>
</div></li>
</ol>
"""


def descargar_falso(url, es_html=False):
    if "/api/catalog_system/" in url:
        return json.dumps(RESPUESTA_VTEX)
    if "intelligent-search" in url:
        return json.dumps({"products": []})
    if "falabella" in url:
        return HTML_FALABELLA
    if "ripley" in url:
        return HTML_RIPLEY
    if "hiraoka" in url:
        return HTML_HIRAOKA
    raise bo.TiendaError("sin datos de prueba")


class PruebasNumeros(unittest.TestCase):
    def test_a_numero(self):
        self.assertEqual(bo.a_numero("1,049"), 1049.0)
        self.assertEqual(bo.a_numero("1.049"), 1049.0)
        self.assertEqual(bo.a_numero("S/ 1,049.90"), 1049.9)
        self.assertEqual(bo.a_numero("1.049,90"), 1049.9)
        self.assertEqual(bo.a_numero("999.9"), 999.9)
        self.assertEqual(bo.a_numero(["899"]), 899.0)
        self.assertEqual(bo.a_numero(950), 950.0)
        self.assertIsNone(bo.a_numero("sin precio"))
        self.assertIsNone(bo.a_numero(None))


class PruebasTiendas(unittest.TestCase):
    def setUp(self):
        parche = mock.patch.object(bo, "descargar", side_effect=descargar_falso)
        parche.start()
        self.addCleanup(parche.stop)

    def test_vtex_filtros(self):
        tienda = bo.TiendaVTEX("Plaza Vea", "https://www.plazavea.com.pe", alias_vendedor=("plazavea",))
        res = bo.consultar_tienda(tienda, bo.MODELOS)
        self.assertEqual(res.errores, [])
        ev = bo.evaluar([res], bo.MODELOS)
        nombres = {o.nombre: o for o, _ in ev.cumplen}
        # Solo pasan: Edge 60 azul a 849 (vendido por la tienda) y Edge 70 a 999.
        self.assertEqual(sorted(nombres), [
            "Celular Motorola Edge 60 Fusion 8GB 256GB Azul",
            "Motorola Edge 70 Fusión 8GB 256GB",
        ])
        azul = nombres["Celular Motorola Edge 60 Fusion 8GB 256GB Azul"]
        self.assertEqual(azul.garantia, "12 meses")
        self.assertEqual(azul.descuento(), 35)
        info = ev.por_tienda["Plaza Vea"]
        self.assertEqual(info["externas_baratas"], 1)        # el de 799 de vendedor externo
        self.assertEqual(info["min"]["edge70"], 999)

    def test_vtex_con_marketplace(self):
        tienda = bo.TiendaVTEX("Plaza Vea", "https://www.plazavea.com.pe")
        ev = bo.evaluar([bo.consultar_tienda(tienda, bo.MODELOS)], bo.MODELOS, incluir_marketplace=True)
        precios = sorted(o.precio for o, _ in ev.cumplen)
        self.assertEqual(precios, [799, 849, 999])

    def test_falabella(self):
        res = bo.consultar_tienda(bo.TiendaFalabella(), bo.MODELOS)
        self.assertEqual(res.errores, [])
        edge60 = [o for o in res.ofertas if "60" in o.nombre][0]
        self.assertEqual((edge60.precio, edge60.precio_lista, edge60.precio_tarjeta), (889, 1499, 779))
        self.assertTrue(edge60.vendedor_es_tienda)            # Tottus cuenta como tienda propia
        ev = bo.evaluar([res], bo.MODELOS)
        self.assertEqual([o.precio for o, _ in ev.cumplen], [889])   # el Edge 60 queda bajo 900
        self.assertEqual(ev.por_tienda["Falabella / Tottus"]["externas_baratas"], 1)
        edge70 = [o for o in res.ofertas if "70" in o.nombre][0]
        self.assertEqual(edge70.url, "https://www.falabella.com.pe/falabella-pe/product/2/edge-70")

    def test_ripley_precio_tarjeta(self):
        res = bo.consultar_tienda(bo.TiendaRipley(), bo.MODELOS)
        self.assertEqual(res.errores, [])
        self.assertEqual(bo.evaluar([res], bo.MODELOS).cumplen, [])          # 1049 normal: no
        ev = bo.evaluar([res], bo.MODELOS, con_tarjeta=True)                  # 949 con tarjeta: sí
        self.assertEqual([o.precio_efectivo(True) for o, _ in ev.cumplen], [949])
        self.assertEqual(ev.cumplen[0][0].url, "https://simple.ripley.com.pe/motorola-edge-70-fusion-pmp1")

    def test_hiraoka(self):
        res = bo.consultar_tienda(bo.TiendaHiraoka(), bo.MODELOS)
        self.assertEqual(len(res.ofertas), 2)
        ev = bo.evaluar([res], bo.MODELOS)
        self.assertEqual([(o.precio, o.precio_lista) for o, _ in ev.cumplen], [(879, 1199)])

    def test_tienda_bloqueada_no_rompe_el_programa(self):
        tienda = bo.TiendaVTEX("Bloqueada", "https://bloqueada.pe")
        with mock.patch.object(bo, "descargar", side_effect=bo.TiendaError("HTTP 403")):
            res = bo.consultar_tienda(tienda, bo.MODELOS)
        self.assertEqual(res.ofertas, [])
        self.assertEqual(res.errores, ["HTTP 403"])

    def test_programa_completo(self):
        tiendas = [bo.TiendaVTEX("Plaza Vea", "https://www.plazavea.com.pe"),
                   bo.TiendaFalabella(), bo.TiendaHiraoka()]
        salida = io.StringIO()
        with mock.patch.object(bo, "TIENDAS", tiendas), contextlib.redirect_stdout(salida):
            codigo = bo.main([])
        texto = salida.getvalue()
        self.assertEqual(codigo, 0)
        self.assertIn("S/ 849.00", texto)
        self.assertIn("MEJOR PRECIO", texto)
        self.assertIn("Garantía: 12 meses", texto)
        self.assertNotIn("Funda", texto)
        self.assertNotIn("Reacondicionado", texto)


class PruebasModelo(unittest.TestCase):
    def identificar(self, nombre, **kw):
        return bo.identificar_modelo(bo.Oferta(tienda="t", nombre=nombre, precio=800, url="u", **kw), bo.MODELOS)

    def test_reconoce_modelos(self):
        self.assertEqual(self.identificar("Smartphone MOTOROLA EDGE 60 FUSIÓN 256GB")[0]["id"], "edge60")
        self.assertEqual(self.identificar("moto edge70 fusion 5G")[0]["id"], "edge70")
        self.assertIsNone(self.identificar("Motorola Edge 60 Pro")[0])
        self.assertIsNone(self.identificar("Motorola Edge 70 Fusion+")[0])

    def test_descarta(self):
        self.assertIsNotNone(self.identificar("Mica de vidrio Edge 60 Fusion")[1])
        self.assertIsNotNone(self.identificar("Edge 60 Fusion open box")[1])
        self.assertIsNotNone(self.identificar("Edge 60 Fusion", stock=False)[1])

    def test_combo_con_regalo_no_es_fusion_plus(self):
        modelo, motivo = self.identificar("Celular Motorola Edge 60 Fusion + Audífonos de regalo")
        self.assertEqual(modelo["id"], "edge60")
        self.assertIsNone(motivo)
        self.assertIsNone(self.identificar("Motorola Edge 70 Fusion Plus 512GB")[0])


if __name__ == "__main__":
    unittest.main()
