from sqlalchemy import Column, Integer, String, ForeignKey, Text, Float, DateTime, func
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, index=True)
    supabase_uid = Column(String, unique=True, nullable=False, index=True)
    email        = Column(String, unique=True, nullable=False)
    role         = Column(String, nullable=False)  # "teacher" | "student"

    assignments = relationship("Assignment", back_populates="teacher")
    submissions = relationship("Submission", back_populates="student")


class Assignment(Base):
    __tablename__ = "assignments"

    id         = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title      = Column(String, nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deadline   = Column(DateTime(timezone=True), nullable=True)   # None = no deadline
    status     = Column(String, default="open")                   # open | closed | checked

    teacher     = relationship("User", back_populates="assignments")
    submissions = relationship("Submission", back_populates="assignment", cascade="all, delete")


class Submission(Base):
    __tablename__ = "submissions"

    id                    = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id            = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignment_id         = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    text                  = Column(Text, nullable=False)
    plagiarism_percentage = Column(Float, nullable=True)   # NULL until deadline passes
    submitted_at          = Column(DateTime(timezone=True), server_default=func.now())
    checked_at            = Column(DateTime(timezone=True), nullable=True)

    student    = relationship("User", back_populates="submissions")
    assignment = relationship("Assignment", back_populates="submissions")
    sentences  = relationship("Sentence", back_populates="submission", cascade="all, delete")
    matches    = relationship("Match",    back_populates="submission", cascade="all, delete")


class Sentence(Base):
    __tablename__ = "sentences"

    id            = Column(Integer, primary_key=True, index=True, autoincrement=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    student_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    sentence_text = Column(Text, nullable=False)
    embedding     = Column(Vector(384), nullable=False)

    submission = relationship("Submission", back_populates="sentences")


class Match(Base):
    __tablename__ = "matches"

    id               = Column(Integer, primary_key=True, index=True, autoincrement=True)
    submission_id    = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    input_sentence   = Column(Text, nullable=False)
    matched_sentence = Column(Text, nullable=False)
    student_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    similarity       = Column(Float, nullable=False)

    submission = relationship("Submission", back_populates="matches")