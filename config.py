import os

API_ID = int(os.getenv("API_ID", 21545599))
API_HASH = os.getenv("API_HASH", "418029ca436b64d3401b2d4e8a3afad6")
PHONENUMBER = os.getenv("PHONENUMBER", "+51996588466")

DB_URL = os.getenv("DB_URL", "sqlite:///./clientes.db")