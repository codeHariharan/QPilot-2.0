from fastapi import FastAPI

from api.router import router

app = FastAPI(title="QPilot API")
app.include_router(router)