import os
import asyncio
from hypercorn.asyncio import serve
from hypercorn.config import Config
from app import create_app

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
    config = Config()
    config.bind = ["0.0.0.0:8000"]
    config.reload = True
    config.use_reloader = True
    asyncio.run(serve(create_app(os.getenv("FLASK_ENV", "development")), config))
