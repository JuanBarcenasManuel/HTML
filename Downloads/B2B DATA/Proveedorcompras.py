import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

# Ruta exacta del archivo e información de conexión
ARCHIVO_EXCEL = "/Users/juanbarcenas/Downloads/B2B DATA/ESTIMACIÓN DE COMPRAS MARZO 2026.xlsx"

# Intenta primero con usuario juanbarcenas (estándar en Postgres.app), si falla usa postgres
DB_URL = "postgresql://juanbarcenas@localhost:5432/b2b_demand_db"

def limpiar_y_cargar_opl(file_path, db_engine):
    print(f"Leyendo archivo Excel desde:\n{file_path}\n")
    df = pd.read_excel(file_path, sheet_name='OPL')
    
    # Normalizar nombres de columnas
    df.columns = df.columns.str.strip()
    
    print("Procesando proveedores...")
    df_prov = df[['PROVEEDOR', 'REGIÓN', 'METODO DE PAGO']].dropna(subset=['PROVEEDOR']).drop_duplicates()
    
    print("Procesando productos...")
    df_prod = df[['Refere', 'Descrip1', 'Dpto', 'Grupo', 'SubGrupo', 'ABC', 'Costo']].dropna(subset=['Refere']).drop_duplicates(subset=['Refere'])
    
    def a_float(val):
        if pd.isna(val): return 0.0
        s = str(val).replace('$', '').replace(' ', '').replace(',', '.')
        try: return float(s)
        except: return 0.0

    df_prod['costo'] = df_prod['Costo'].apply(a_float)
    
    print("Insertando datos en PostgreSQL (b2b_demand_db)...")
    with db_engine.begin() as conn:
        # 1. Crear tabla de Proveedores
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS proveedores (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(255) UNIQUE NOT NULL,
                region VARCHAR(100),
                metodo_pago_defecto VARCHAR(100)
            );
        """))
        
        # 2. Crear tabla de Maestro de Productos
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS maestro_productos (
                id SERIAL PRIMARY KEY,
                sku_ref VARCHAR(100) UNIQUE NOT NULL,
                descripcion TEXT,
                departamento VARCHAR(100),
                grupo VARCHAR(100),
                subgrupo VARCHAR(100),
                clasificacion_abc VARCHAR(10),
                costo_base NUMERIC(12, 2)
            );
        """))

        # 3. Cargar Proveedores
        for _, r in df_prov.iterrows():
            conn.execute(text("""
                INSERT INTO proveedores (nombre, region, metodo_pago_defecto)
                VALUES (:nombre, :region, :pago)
                ON CONFLICT (nombre) DO UPDATE SET region = EXCLUDED.region;
            """), {
                "nombre": str(r['PROVEEDOR']).strip().upper(),
                "region": str(r['REGIÓN']),
                "pago": str(r['METODO DE PAGO'])
            })

        # 4. Cargar Productos
        for _, r in df_prod.iterrows():
            conn.execute(text("""
                INSERT INTO maestro_productos (sku_ref, descripcion, departamento, grupo, subgrupo, clasificacion_abc, costo_base)
                VALUES (:sku, :desc, :dpto, :grp, :sub, :abc, :costo)
                ON CONFLICT (sku_ref) DO UPDATE SET costo_base = EXCLUDED.costo_base;
            """), {
                "sku": str(r['Refere']).strip().upper(),
                "desc": str(r['Descrip1']).strip().upper(),
                "dpto": str(r['Dpto']),
                "grp": str(r['Grupo']),
                "sub": str(r['SubGrupo']),
                "abc": str(r['ABC']),
                "costo": float(r['costo'])
            })

    print("\n¡Carga y limpieza de datos OPL completada con éxito!")

if __name__ == "__main__":
    if os.path.exists(ARCHIVO_EXCEL):
        try:
            engine = create_engine(DB_URL)
            limpiar_y_cargar_opl(ARCHIVO_EXCEL, engine)
        except Exception as e:
            # Reintento con usuario 'postgres' en caso de autenticación
            try:
                engine = create_engine("postgresql://postgres:postgres@localhost:5432/b2b_demand_db")
                limpiar_y_cargar_opl(ARCHIVO_EXCEL, engine)
            except Exception as e2:
                print(f"Ocurrió un error de conexión o ejecución: {e2}")
    else:
        print(f"No se encontró el archivo en la ruta: {ARCHIVO_EXCEL}")
