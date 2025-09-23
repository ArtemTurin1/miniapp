from sqlalchemy import select, update, delete, func, desc
from models import async_session, User, Problem, UserSolution, Subject, Difficulty
from pydantic import BaseModel, ConfigDict
from typing import List
from datetime import datetime

class ProblemSchema(BaseModel):
    id: int
    title: str
    description: str
    subject: str
    difficulty: str
    points: int
    
    model_config = ConfigDict(from_attributes=True)

class UserStatsSchema(BaseModel):
    score: int
    level: int
    solved_count: int
    math_solved: int
    informatics_solved: int

async def add_user(tg_id):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))
        if user:
            return user
        
        new_user = User(tg_id=tg_id)
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        return new_user

async def get_problems(subject: str = None, difficulty: str = None):
    async with async_session() as session:
        query = select(Problem)
        
        if subject:
            query = query.where(Problem.subject == Subject(subject))
        if difficulty:
            query = query.where(Problem.difficulty == Difficulty(difficulty))
            
        problems = await session.scalars(query)
        return [ProblemSchema.model_validate(p).model_dump() for p in problems]

async def check_solution(user_id: int, problem_id: int, user_answer: str):
    async with async_session() as session:
        problem = await session.scalar(select(Problem).where(Problem.id == problem_id))
        user = await session.scalar(select(User).where(User.id == user_id))
        
        is_correct = user_answer.strip().lower() == problem.correct_answer.strip().lower()
        
        # Сохраняем решение
        solution = UserSolution(
            user_id=user_id,
            problem_id=problem_id,
            user_answer=user_answer,
            is_correct=is_correct
        )
        
        if is_correct:
            user.score += problem.points
            # Повышаем уровень каждые 100 очков
            user.level = user.score // 100 + 1
        
        session.add(solution)
        await session.commit()
        
        return {
            'correct': is_correct,
            'correct_answer': problem.correct_answer if not is_correct else None,
            'points_earned': problem.points if is_correct else 0,
            'new_score': user.score
        }

async def get_user_stats(user_id: int):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        solved_count = await session.scalar(
            select(func.count(UserSolution.id))
            .where(UserSolution.user_id == user_id, UserSolution.is_correct == True)
        )
        
        math_solved = await session.scalar(
            select(func.count(UserSolution.id))
            .join(Problem)
            .where(UserSolution.user_id == user_id, 
                   UserSolution.is_correct == True,
                   Problem.subject == Subject.MATH)
        )
        
        informatics_solved = await session.scalar(
            select(func.count(UserSolution.id))
            .join(Problem)
            .where(UserSolution.user_id == user_id,
                   UserSolution.is_correct == True,
                   Problem.subject == Subject.INFORMATICS)
        )
        
        return UserStatsSchema(
            score=user.score,
            level=user.level,
            solved_count=solved_count,
            math_solved=math_solved,
            informatics_solved=informatics_solved
        )