from sqlalchemy import select, update, delete, func, desc
from models import async_session, User, Problem, UserSolution, Subject, Difficulty, Task
from passlib.context import CryptContext
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import re

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def _hash_password(password: str) -> str:
    return pwd_ctx.hash(password)

def _verify_password(password: str, hashed: str) -> bool:
    return pwd_ctx.verify(password, hashed)

def _normalize_answer(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r'\s+', '', s.lower()).replace(',', '.').strip()

def _answer_to_set(s: str):
    """Если ответ содержит разделители (; ,), вернём множество вариантов."""
    if s is None:
        return set()
    parts = re.split(r'[;,]', s)
    return set(_normalize_answer(p) for p in parts if p != '')

# ---------------- User management ----------------

async def get_user_by_tg(tg_id: int) -> Optional[User]:
    async with async_session() as session:
        return await session.scalar(select(User).where(User.tg_id == tg_id))

async def get_user_by_email(email: str) -> Optional[User]:
    async with async_session() as session:
        return await session.scalar(select(User).where(User.email == email))

async def add_user(tg_id: int = None, name: str = None, email: str = None, password: str = None):
    """
    Создаёт пользователя если не существует.
    Если передан email+password — регистрируем классически.
    Если передан tg_id — создаём/возвращаем пользователя по telegram id.
    """
    async with async_session() as session:
        if tg_id:
            user = await session.scalar(select(User).where(User.tg_id == tg_id))
            if user:
                return user
            new_user = User(tg_id=tg_id, name=name)
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            return new_user

        if email:
            user = await session.scalar(select(User).where(User.email == email))
            if user:
                return None  # уже есть
            new_user = User(email=email, name=name, password_hash=_hash_password(password))
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            return new_user

async def register_user_via_email(email: str, password: str, name: str = None):
    existing = await get_user_by_email(email)
    if existing:
        return None
    return await add_user(email=email, password=password, name=name)

async def check_credentials(email: str, password: str):
    user = await get_user_by_email(email)
    if not user:
        return None
    if not user.password_hash:
        return None
    if _verify_password(password, user.password_hash):
        return user
    return None

# ---------------- Problems & Solutions ----------------

async def get_problems(subject: str = None, difficulty: str = None):
    async with async_session() as session:
        query = select(Problem)
        if subject:
            try:
                query = query.where(Problem.subject == Subject(subject))
            except Exception:
                pass
        if difficulty:
            try:
                query = query.where(Problem.difficulty == Difficulty(difficulty))
            except Exception:
                pass
        problems = await session.scalars(query)
        return [
            {
                'id': p.id,
                'title': p.title,
                'description': p.description,
                'subject': p.subject.value,
                'difficulty': p.difficulty.value,
                'points': p.points
            } for p in problems
        ]

async def check_solution(user_id: int, problem_id: int, user_answer: str):
    async with async_session() as session:
        problem = await session.scalar(select(Problem).where(Problem.id == problem_id))
        user = await session.scalar(select(User).where(User.id == user_id))
        if not problem or not user:
            return {'error': 'user or problem not found'}

        # сравнение ответов (поддерживает варианты вида "2;3")
        correct_raw = problem.correct_answer or ""
        # если в ответе есть разделители — сравним множества
        if re.search(r'[;,]', correct_raw):
            is_correct = _answer_to_set(user_answer) == _answer_to_set(correct_raw)
        else:
            is_correct = _normalize_answer(user_answer) == _normalize_answer(correct_raw)

        # Сохраняем решение
        solution = UserSolution(
            user_id=user_id,
            problem_id=problem_id,
            user_answer=user_answer,
            is_correct=is_correct
        )

        if is_correct:
            user.score = (user.score or 0) + (problem.points or 0)
            # Повышаем уровень каждые 100 очков
            user.level = (user.score // 100) + 1

        session.add(solution)
        await session.commit()
        await session.refresh(user)

        return {
            'correct': is_correct,
            'correct_answer': None if is_correct else problem.correct_answer,
            'points_earned': problem.points if is_correct else 0,
            'new_score': user.score
        }

# ---------------- Stats ----------------

async def get_user_stats(user_id: int):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        if not user:
            return None
        solved_count = await session.scalar(
            select(func.count(UserSolution.id))
            .where(UserSolution.user_id == user_id, UserSolution.is_correct == True)
        ) or 0

        math_solved = await session.scalar(
            select(func.count(UserSolution.id))
            .join(Problem, Problem.id == UserSolution.problem_id)
            .where(UserSolution.user_id == user_id,
                   UserSolution.is_correct == True,
                   Problem.subject == Subject.MATH)
        ) or 0

        informatics_solved = await session.scalar(
            select(func.count(UserSolution.id))
            .join(Problem, Problem.id == UserSolution.problem_id)
            .where(UserSolution.user_id == user_id,
                   UserSolution.is_correct == True,
                   Problem.subject == Subject.INFORMATICS)
        ) or 0

        return {
            'score': user.score or 0,
            'level': user.level or 1,
            'solved_count': int(solved_count),
            'math_solved': int(math_solved),
            'informatics_solved': int(informatics_solved)
        }

# ---------------- Tasks (user to-do) ----------------

async def get_tasks_for_tg(tg_id: int):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))
        if not user:
            return []
        tasks = await session.scalars(select(Task).where(Task.user_id == user.id).order_by(Task.created_at.desc()))
        return [
            {
                'id': t.id,
                'title': t.title,
                'completed': t.completed,
                'created_at': t.created_at.isoformat()
            } for t in tasks
        ]

async def create_task_for_tg(tg_id: int, title: str):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))
        if not user:
            user = await add_user(tg_id=tg_id)
        task = Task(user_id=user.id, title=title)
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return {
            'id': task.id,
            'title': task.title,
            'completed': task.completed
        }

async def complete_task(task_id: int):
    async with async_session() as session:
        task = await session.scalar(select(Task).where(Task.id == task_id))
        if not task:
            return None
        task.completed = True
        await session.commit()
        return {
            'id': task.id,
            'title': task.title,
            'completed': task.completed
        }
