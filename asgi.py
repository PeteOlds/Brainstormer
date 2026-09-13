import os
from app import create_app
from asgiref.wsgi import WsgiToAsgi

wsgi_app = create_app(os.getenv("FLASK_ENV", "production"))
app = WsgiToAsgi(wsgi_app)
