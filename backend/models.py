from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    email = Column(String, unique=True)
    display_name = Column(String)
    native_lang = Column(String)
    target_lang = Column(String)
    level = Column(Integer, default=1)
    interests = Column(JSON, default=[])
    daily_goal_minutes = Column(Integer, default=15)
    total_xp = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class Lesson(Base):
    __tablename__ = "lessons"
    id = Column(String, primary_key=True)
    title = Column(String)
    description = Column(String)
    level = Column(String)
    duration = Column(Integer)
    xp = Column(Integer, default=10)
    content = Column(JSON)

class UserProgress(Base):
    __tablename__ = "user_progress"
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    lesson_id = Column(String, ForeignKey("lessons.id"))
    completed = Column(Boolean, default=False)
    score = Column(Float, default=0)

class Story(Base):
    __tablename__ = "stories"
    id = Column(String, primary_key=True)
    title = Column(String)
    content = Column(String)
    level = Column(String)
    genre = Column(String)
    read_time = Column(Integer)
    rating = Column(Float, default=4.5)
