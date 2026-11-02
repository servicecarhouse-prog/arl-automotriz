# Buscador de ofertas: Motorola Edge 70 Fusion y Edge 60 Fusion

Programa que revisa las tiendas más conocidas del Perú y te muestra **solo** las ofertas que cumplen:

| Modelo | Precio máximo |
|---|---|
| Motorola Edge 70 Fusion | menos de **S/ 1000** |
| Motorola Edge 60 Fusion | menos de **S/ 900** |

Tiendas revisadas: **Plaza Vea, Efe, La Curacao, Oechsle, Coolbox, Motorola (tienda oficial), Falabella / Tottus, Ripley e Hiraoka**.

## Cómo cuida la garantía

- Solo cuenta productos **vendidos por la propia tienda**. Los de vendedores externos (marketplace) se ocultan,
  pero el reporte te avisa cuántos había por si quieres verlos (`--incluir-marketplace`).
- Descarta equipos **reacondicionados, usados, open box, de exhibición o importados**.
- Descarta **accesorios** (fundas, micas, cargadores…) y el modelo **Fusion+**, que es otro equipo.
- Descarta productos **sin stock**.
- Si la tienda publica el dato de garantía (por ejemplo "12 meses"), lo muestra.

## Cómo usarlo

1. Instala Python 3 desde <https://www.python.org/downloads/> (en Windows marca **"Add Python to PATH"**).
   No hace falta instalar nada más.
2. Descarga esta carpeta `ofertas-motorola`.
3. En Windows: doble clic en **`buscar_ofertas.bat`**.
   En Mac/Linux: abre una terminal en la carpeta y ejecuta `python3 buscar_ofertas.py`.

Ejemplo de lo que muestra:

```
>> Motorola Edge 60 Fusion  (menos de S/ 900.00)
   1)    S/ 849.00   antes S/ 1,299.00 (-35%)   PLAZA VEA   <-- MEJOR PRECIO
      Celular Motorola Edge 60 Fusion 8GB 256GB Azul
      Vendido por: plazaVea   |   Garantía: 12 meses
      https://www.plazavea.com.pe/...

-- Estado de cada tienda ---------------------------------
   Tienda                     Resultado      más barato Edge 70 / más barato Edge 60
   Plaza Vea                  OK             S/ 1,149.00 / S/ 849.00
   Ripley                     NO SE PUDO     - / -
      motivo: la tienda rechazó la consulta (HTTP 403); suele ser protección anti-bots
```

(Los precios del ejemplo son inventados; los reales salen al ejecutarlo.)

La tabla de abajo te dice además **el precio más barato que vio en cada tienda** aunque no llegue a tu límite,
para que sepas qué tan cerca está.

## Opciones

| Opción | Qué hace |
|---|---|
| `--max-70 950` | Cambia el precio máximo del Edge 70 Fusion |
| `--max-60 850` | Cambia el precio máximo del Edge 60 Fusion |
| `--con-tarjeta` | Cuenta también el precio con tarjeta de la tienda (CMR, Ripley…) |
| `--incluir-marketplace` | Muestra también vendedores externos (la garantía la da ese vendedor) |
| `--tiendas "plaza vea,efe,curacao"` | Revisa solo esas tiendas |
| `--csv ofertas.csv` | Guarda las ofertas en un archivo que se abre con Excel (va sumando filas con fecha) |
| `--cada 60` | Repite la búsqueda cada 60 minutos y avisa con un pitido si aparece una oferta nueva |

Ejemplo: `python buscar_ofertas.py --cada 30 --csv ofertas.csv`

## Cosas a tener en cuenta

- **Plaza Vea, Efe, La Curacao, Oechsle, Coolbox y Motorola** se consultan con la API pública de su plataforma
  (VTEX), que es estable. **Falabella, Ripley e Hiraoka** se leen desde su página web: si cambian el diseño o
  bloquean las consultas automáticas, el programa lo indica en "Estado de cada tienda" y sigue con las demás.
- Plaza Vea, Oechsle y otras tiendas tienen precios especiales con su tarjeta (Oh!, etc.) que no siempre se
  publican en la API; el programa usa el precio online normal.
- El precio final puede cambiar en el carrito (envío, cupones, stock por distrito). Confirma siempre en la web
  antes de comprar.
- Para agregar otra tienda hecha con VTEX, añade una línea en la lista `TIENDAS` dentro de `buscar_ofertas.py`.

## Pruebas

`python -m unittest test_buscar_ofertas -v` — usa respuestas simuladas, no necesita internet.
