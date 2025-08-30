import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from config import settings
from passlib.context import CryptContext

# Configuración para hash de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@contextmanager
def get_db_connection():
    conn = psycopg2.connect(
        settings.DATABASE_URL,
        cursor_factory=RealDictCursor
    )
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def get_db_cursor():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e

def init_db():
    with get_db_cursor() as cur:
        # Crear tabla de clientes si no existe
        cur.execute('''
            CREATE TABLE IF NOT EXISTS clientes (
                email VARCHAR(255) PRIMARY KEY,
                nombre VARCHAR(255),
                dni_cif VARCHAR(50),
                direccion TEXT,
                password VARCHAR(255) NOT NULL,
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

def get_user_by_email(email: str):
    with get_db_cursor() as cur:
        cur.execute('SELECT email, nombre, dni_cif, direccion, password, activo FROM clientes WHERE email = %s', (email,))
        return cur.fetchone()

def save_user(user_data: dict):
    with get_db_cursor() as cur:
        cur.execute('''
            INSERT INTO clientes (email, nombre, dni_cif, direccion, password, activo)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET
            nombre = EXCLUDED.nombre,
            dni_cif = EXCLUDED.dni_cif,
            direccion = EXCLUDED.direccion,
            password = EXCLUDED.password,
            activo = EXCLUDED.activo
        ''', (
            user_data['email'],
            user_data.get('nombre'),
            user_data.get('dni_cif'),
            user_data.get('direccion'),
            user_data['password'],
            user_data.get('activo', True)
        ))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)