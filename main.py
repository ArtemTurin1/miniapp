from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from models import init_db
import requests as rq

class SolutionRequest(BaseModel):
    tg_id: int
    problem_id: int
    user_answer: str

@asynccontextmanager
async def lifespan(app_: FastAPI):
    await init_db()
    print('Bot is ready')
    yield

app = FastAPI(title="Math & Informatics App", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/problems/")
async def get_problems(
    subject: str = Query(None, description="Subject filter"),
    difficulty: str = Query(None, description="Difficulty filter")
):
    return await rq.get_problems(subject, difficulty)

@app.post("/api/solve/")
async def solve_problem(solution: SolutionRequest):
    user = await rq.add_user(solution.tg_id)
    result = await rq.check_solution(user.id, solution.problem_id, solution.user_answer)
    return result

@app.get("/api/stats/{tg_id}")
async def get_stats(tg_id: int):
    user = await rq.add_user(tg_id)
    return await rq.get_user_stats(user.id)

@app.get("/api/profile/{tg_id}")
async def profile(tg_id: int):
    user = await rq.add_user(tg_id)
    stats = await rq.get_user_stats(user.id)
    return stats.model_dump()