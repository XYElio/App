#app.py
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for

#Cadena de conexión a NeonDB (PostgreSQL)
DATABASE_URL = ("postgresql://neondb_owner:npg_1YgAylzvPw9x@ep-lively-shadow-a4o9mzps-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require")

def get_db_connection():
    """Abre y devuelve una conexión a la base de datos PostgreSQL."""
    return psycopg2.connect(DATABASE_URL)

def crear_app():
  app = Flask(__name__)

  @app.route('/', methods=['GET'])
  def clientes():
      # 1)Leer parametro cliente_id (si ya eligio uno)
      cliente_id = request.args.get('cliente_id', type=int)

      conn = get_db_connection()
      cur  = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

      # 2)Cargar listado completo de clientes
      cur.execute("""
        SELECT c.id_cte, c.rfc_cte, c.nombre_cte, c.direccion_cte,
              e.nombre_estado, ci.ciudad_cte
        FROM public.cliente c
        JOIN public.estado e   ON c.id_estado = e.id_estado
        JOIN public.ciudades ci ON c.id_ciudad = ci.id_ciudad
        ORDER BY c.id_cte
      """)
      listado = cur.fetchall()

      #Variables que se llenan si ya seleccionó cliente
      cliente   = None
      pedido    = None
      detalles  = []
      productos = []
      subtotal = iva = total = 0.0

      if cliente_id:
          # 3)Datos del cliente
          cur.execute("""
            SELECT c.id_cte, c.rfc_cte, c.nombre_cte, c.direccion_cte,e.nombre_estado, ci.ciudad_cte
            FROM public.cliente c
            JOIN public.estado e   ON c.id_estado = e.id_estado
            JOIN public.ciudades ci ON c.id_ciudad = ci.id_ciudad
            WHERE c.id_cte = %s
          """, (cliente_id,))
          cliente = cur.fetchone()

          # 4)Obtener o crear pedido (ultimo pedido)
          cur.execute("""
            SELECT id_pedido, fecha_pedido
            FROM public.pedido
            WHERE id_cte = %s
            ORDER BY fecha_pedido DESC
            LIMIT 1
          """, (cliente_id,))
          fila = cur.fetchone()
          if fila:
              pedido = {'id_pedido': fila['id_pedido'], 'fecha_pedido': fila['fecha_pedido']}
          else:
              cur.execute("""
                INSERT INTO public.pedido (id_cte)
                VALUES (%s)
                RETURNING id_pedido, fecha_pedido
              """, (cliente_id,))
              nueva = cur.fetchone()
              conn.commit()
              pedido = {'id_pedido': nueva['id_pedido'], 'fecha_pedido': nueva['fecha_pedido']}

          # 5)Cargar detalles del pedido
          cur.execute("""
            SELECT p.id_producto, p.descripcion_producto, p.precio_unitario, dp.cantidad_productos,(dp.cantidad_productos * p.precio_unitario) AS total_linea
            FROM public.detalle_pedido dp
            JOIN public.producto p ON dp.id_producto = p.id_producto
            WHERE dp.id_pedido = %s
          """, (pedido['id_pedido'],))
          detalles = cur.fetchall()

          # 6)Cargar catálogo completo de productos para agregar
          cur.execute("""
            SELECT id_producto, descripcion_producto, precio_unitario
            FROM public.producto
            ORDER BY descripcion_producto
          """)
          productos = cur.fetchall()

          # 7)Cálculos de totales (convertir Decimal a float)
          subtotal = sum(float(d['total_linea']) for d in detalles)
          iva      = round(subtotal * 0.16, 2)
          total    = round(subtotal + iva, 2)

      cur.close()
      conn.close()

      return render_template(
          'clientes.html',
          listado=listado,
          cliente=cliente,
          pedido=pedido,
          detalles=detalles,
          productos=productos,
          subtotal=subtotal,
          iva=iva,
          total=total
      )

  @app.route('/add', methods=['POST'])
  def add():
      #Recibe el form de Agregar producto
      cliente_id = int(request.form['cliente_id'])
      pedido_id  = int(request.form['pedido_id'])
      prod_id    = int(request.form['producto_id'])
      cantidad   = int(request.form['cantidad'])

      conn = get_db_connection()
      cur  = conn.cursor()
      cur.execute("""
        INSERT INTO public.detalle_pedido
          (id_pedido, id_producto, cantidad_productos)
        VALUES (%s, %s, %s) ON CONFLICT (id_pedido, id_producto) DO UPDATE SET cantidad_productos =
          public.detalle_pedido.cantidad_productos + EXCLUDED.cantidad_productos
      """, (pedido_id, prod_id, cantidad))
      conn.commit()
      cur.close()
      conn.close()

      #Volver a la misma página con el cliente seleccionado
      return redirect(url_for('clientes', cliente_id=cliente_id))

  @app.route('/factura', methods=['GET'])
  def factura_final():
      cliente_id = request.args.get('cliente_id', type=int)
      pedido_id  = request.args.get('pedido_id',  type=int)

      #Datos estáticos de la empresa
      empresa = {
        'nombre':   'GAMINGTO S.A. de C.V.',
        'rfc':      'GTG210319ABC',
        'direccion':'Av. Montevideo 304, Col. Americana, Guadalajara, Jalisco, CP 44160',
        'telefono': '(33) 1234-5678',
        'email':    'gamingto@gmail.com'
      }

      conn = get_db_connection()
      cur  = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

      # 1)Datos del cliente
      cur.execute("""
        SELECT c.nombre_cte, c.rfc_cte, c.direccion_cte,e.nombre_estado, ci.ciudad_cte
        FROM public.cliente c
        JOIN public.estado e   ON c.id_estado = e.id_estado
        JOIN public.ciudades ci ON c.id_ciudad = ci.id_ciudad
        WHERE c.id_cte = %s
      """, (cliente_id,))
      cliente = cur.fetchone()

      # 2)Fecha del pedido
      cur.execute("SELECT fecha_pedido FROM public.pedido WHERE id_pedido = %s", (pedido_id,))
      fecha_row = cur.fetchone()
      fecha_pedido = fecha_row['fecha_pedido'] if fecha_row else None
      pedido = {'id_pedido': pedido_id, 'fecha_pedido': fecha_pedido}

      # 3)Detalles finales
      cur.execute("""
        SELECT p.descripcion_producto, dp.cantidad_productos,p.precio_unitario,(dp.cantidad_productos * p.precio_unitario) AS total_linea
        FROM public.detalle_pedido dp
        JOIN public.producto p ON dp.id_producto = p.id_producto
        WHERE dp.id_pedido = %s
      """, (pedido_id,))
      detalles = cur.fetchall()

      # 4)Calculos finales
      subtotal = sum(float(d['total_linea']) for d in detalles)
      iva      = round(subtotal * 0.16, 2)
      total    = round(subtotal + iva, 2)

      cur.close()
      conn.close()

      return render_template(
          'factura.html',
          empresa=empresa,
          cliente=cliente,
          detalles=detalles,
          subtotal=subtotal,
          iva=iva,
          total=total,
          folio=pedido_id,
          pedido=pedido
      )

if __name__ == '__main__':
    app = crear_app
    app.run
