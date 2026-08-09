import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

# 1. CONEXIÓN A POSTGRESQL LOCAL
DB_USER = "postgres"      # o tu usuario de macOS (ej: juanbarcenas)
DB_PASS = ""              # tu clave si le asignaste alguna
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "b2b_demand_db"

engine_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}" if DB_PASS else f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(engine_url)

print("1. Leyendo el archivo Excel...")
df = pd.read_excel("/Users/juanbarcenas/Downloads/B2B DATA/data-4.xlsx")

# Limpiar nombres de columnas
df.columns = df.columns.str.strip()

# Filtrar filas basura (filtros aplicados o referencias nulas/largas)
df = df[df['Refere'].notnull()].copy()
df['Refere'] = df['Refere'].astype(str).str.strip()
df = df[~df['Refere'].str.contains("Applied filters", case=False, na=False)]
df = df[df['Refere'].str.len() <= 100]  # Filtrar cualquier texto largo erróneo

print(f"✓ Leídas {len(df)} filas válidas de ventas.")

with engine.connect() as conn:
    # 2. AMPLIAR TAMAÑO DE COLUMNAS EN POSTGRES SI ES NECESARIO
    conn.execute(text("""
        ALTER TABLE productos ALTER COLUMN sku TYPE VARCHAR(100);
        ALTER TABLE productos ALTER COLUMN nombre TYPE VARCHAR(255);
        ALTER TABLE productos ALTER COLUMN categoria TYPE VARCHAR(100);
    """))
    conn.commit()

    # 3. ALMACENES / TIENDAS
    print("2. Cargando Almacenes...")
    tiendas = df['Tienda'].dropna().unique()
    for t in tiendas:
        reg = df[df['Tienda'] == t]['región'].iloc[0] if 'región' in df.columns else ''
        conn.execute(text("""
            INSERT INTO almacenes (nombre, ubicacion)
            VALUES (:nombre, :ubicacion)
            ON CONFLICT DO NOTHING;
        """), {"nombre": str(t), "ubicacion": str(reg)})
    conn.commit()

    # 4. PRODUCTOS
    print("3. Cargando Productos...")
    prods = df[['Refere', 'DESCRIPCCION', 'DEPARTAMENTO', 'GRUPO']].drop_duplicates(subset=['Refere'])
    
    for _, row in prods.iterrows():
        sku = str(row['Refere']).strip()
        nombre = str(row['DESCRIPCCION']).strip() if pd.notnull(row['DESCRIPCCION']) else 'Sin Nombre'
        cat = f"{row['DEPARTAMENTO']} - {row['GRUPO']}" if pd.notnull(row['DEPARTAMENTO']) else 'General'
        
        conn.execute(text("""
            INSERT INTO productos (sku, nombre, categoria, costo_usd, precio_usd)
            VALUES (:sku, :nombre, :cat, 0.00, 0.00)
            ON CONFLICT (sku) DO NOTHING;
        """), {"sku": sku, "nombre": nombre, "cat": cat})
    conn.commit()

    # 5. MAPEOS DE ID PARA CARGA RÁPIDA
    print("4. Mapeando IDs para inserción de facturas...")
    df_alm = pd.read_sql("SELECT almacen_id, nombre FROM almacenes", conn)
    dict_alm = dict(zip(df_alm['nombre'], df_alm['almacen_id']))

    df_prod = pd.read_sql("SELECT producto_id, sku FROM productos", conn)
    dict_prod = dict(zip(df_prod['sku'], df_prod['producto_id']))

    # 6. CARGAR VENTAS
    print("5. Procesando facturas y líneas...")
    col_factura = 'Facturas Distintas' if 'Facturas Distintas' in df.columns else 'Facturas Dist'
    facturas_agrupadas = df.groupby(col_factura)
    
    facturas_count = 0
    lineas_count = 0

    for num_factura, group in facturas_agrupadas:
        primera = group.iloc[0]
        almacen_id = dict_alm.get(primera['Tienda'], 1)
        
        fecha_emision = datetime.now().date()
        total_neto = float(group['Monto neto'].sum()) if 'Monto neto' in group.columns else 0.0

        res = conn.execute(text("""
            INSERT INTO documentos_cabecera (tipo_documento, almacen_origen_id, estado, fecha_emision, total_usd)
            VALUES ('VENTA', :alm, 'ACTIVO', :fec, :tot)
            RETURNING documento_id;
        """), {"alm": almacen_id, "fec": fecha_emision, "tot": total_neto})
        
        doc_id = res.fetchone()[0]
        facturas_count += 1

        for _, fila in group.iterrows():
            sku = str(fila['Refere']).strip()
            p_id = dict_prod.get(sku)
            if p_id:
                cant = float(fila['Cantidades']) if pd.notnull(fila['Cantidades']) else 1.0
                monto = float(fila['Monto neto']) if pd.notnull(fila['Monto neto']) else 0.0
                costo = float(fila['Costo total']) if 'Costo total' in df.columns and pd.notnull(fila['Costo total']) else 0.0
                
                pu = (monto / cant) if cant > 0 else 0.0
                cu = (costo / cant) if cant > 0 else 0.0

                conn.execute(text("""
                    INSERT INTO documentos_lineas (documento_id, producto_id, cantidad, precio_unitario_usd, costo_unitario_usd)
                    VALUES (:d_id, :p_id, :cant, :pu, :cu);
                """), {"d_id": doc_id, "p_id": p_id, "cant": cant, "pu": pu, "cu": cu})
                lineas_count += 1

    conn.commit()
    print(f"\n¡CARGA COMPLETADA CON ÉXITO!")
    print(f"✓ Facturas creadas: {facturas_count}")
    print(f"✓ Líneas de venta creadas: {lineas_count}")