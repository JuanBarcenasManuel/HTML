from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text
from database import engine

app = FastAPI(title="ERP B2B DATA - Módulo de Ventas & Analytics")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def dashboard_view(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "page_title": "Tablero Principal B2B"
    })

# ==========================================
# ENDPOINTS KPIS DE VENTAS (MÓDULO ESTÁNDAR)
# ==========================================

@app.get("/api/analytics/ventas-resumen")
def get_resumen_ventas():
    """Retorna los indicadores clave (KPIs) de ventas para la junta directiva/compras."""
    with engine.connect() as conn:
        # 1. Total Ventas y Margen
        totales = conn.execute(text("""
            SELECT 
                COALESCE(SUM(total_venta_usd), 0) AS total_ingresos,
                COALESCE(SUM(total_costo_usd), 0) AS total_costos,
                COALESCE(SUM(margen_ganancia_usd), 0) AS margen_total
            FROM ventas_historico;
        """)).fetchone()

        # 2. Producto más vendido (Top SKU)
        top_producto = conn.execute(text("""
            SELECT p.descripcion, p.sku_ref, SUM(v.cantidad_vendida) AS unidades
            FROM ventas_historico v
            JOIN maestro_productos p ON v.producto_id = p.id
            GROUP BY p.descripcion, p.sku_ref
            ORDER BY unidades DESC
            LIMIT 1;
        """)).fetchone()

        # 3. Tienda con más ventas (Anonimizada)
        top_tienda = conn.execute(text("""
            SELECT t.nombre_tienda, t.region, SUM(v.total_venta_usd) AS total_ventas
            FROM ventas_historico v
            JOIN tiendas t ON v.tienda_id = t.id
            GROUP BY t.nombre_tienda, t.region
            ORDER BY total_ventas DESC
            LIMIT 1;
        """)).fetchone()

        # 4. Región con más ventas
        top_region = conn.execute(text("""
            SELECT t.region, SUM(v.total_venta_usd) AS total_ventas
            FROM ventas_historico v
            JOIN tiendas t ON v.tienda_id = t.id
            GROUP BY t.region
            ORDER BY total_ventas DESC
            LIMIT 1;
        """)).fetchone()

    return {
        "status": "success",
        "kpis": {
            "total_ingresos_usd": float(totales.total_ingresos),
            "total_costos_usd": float(totales.total_costos),
            "margen_total_usd": float(totales.margen_total),
            "top_producto": {
                "sku": top_producto.sku_ref if top_producto else "N/A",
                "descripcion": top_producto.descripcion if top_producto else "N/A",
                "unidades": int(top_producto.unidades) if top_producto else 0
            },
            "top_tienda": {
                "nombre": top_tienda.nombre_tienda if top_tienda else "N/A",
                "region": top_tienda.region if top_tienda else "N/A",
                "total_usd": float(top_tienda.total_ventas) if top_tienda else 0.0
            },
            "top_region": {
                "region": top_region.region if top_region else "N/A",
                "total_usd": float(top_region.total_ventas) if top_region else 0.0
            }
        }
    }

@app.get("/api/analytics/ventas-por-region")
def ventas_por_region():
    """Desglose de ventas por Región para gráficos en el dashboard."""
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT t.region, SUM(v.total_venta_usd) AS total_usd, COUNT(DISTINCT t.id) AS num_tiendas
            FROM ventas_historico v
            JOIN tiendas t ON v.tienda_id = t.id
            GROUP BY t.region
            ORDER BY total_usd DESC;
        """))
        data = [dict(row._mapping) for row in res]
    return {"status": "success", "data": data}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
