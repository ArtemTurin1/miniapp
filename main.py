from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models import init_db
import requests as rq

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print('Ready')
    yield

app = FastAPI(title="to Do app", lifespan= lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_originals = ['*'],
    allow_credentatials = True,
    allow_methods = ['*'],
    allow_headers = ['*']
)

@app.get("/api/tasks/{tg_id}")
async def tasks(tg_id: int):
    user = await rq.add_user()
    return await rq.get_tasks(user.id)


@app.get("/api/tasks/{tg_id}")
async def profile(tg_id: int):
    user = await rq.add_user(tg_id)
    completed_task = await rq.get_complited(user.id)
    return {'completedTask': completed_task}
