import uvicorn
import logging
from src.app import App
from src.settings import settings

app = App()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("main:app",  host=settings.host, port=settings.port)
