from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from .agent.router import router as tutor_router
from .curriculum.loader import list_lessons, seed_lesson_progress
from .database import Base, engine, get_db
from .settings import get_settings

app = FastAPI(
    title="gaosi-tutor",
    description="高思竞赛数学课本 · 一年级上册陪学 Agent",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    settings = get_settings()
    if not settings.deepseek_api_key:
        print("[WARN] DEEPSEEK_API_KEY 未配置，Agent 对话不可用（见 config/.env.example）")

    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        seeded = seed_lesson_progress(db)
        print(f"[DB] 课程进度表已就绪，新建 {seeded} 条讲次记录")
        print(f"[Curriculum] 已加载 {len(list_lessons())} 讲（一年级上册）")
    finally:
        db.close()


@app.get("/")
def root():
    return {"name": "gaosi-tutor", "docs": "/docs"}


app.include_router(tutor_router)
