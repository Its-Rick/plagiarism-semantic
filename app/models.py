from sqlalchemy import Column, Integer, Text, ForeignKey
from pgvector.sqlalchemy import Vector
from app.database import Base

class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, index=True)
    assignment_group_id = Column(Integer, index=True)


class Sentence(Base):
    __tablename__ = "sentences"

    id = Column(Integer, primary_key=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"))
    student_id = Column(Integer)
    sentence_text = Column(Text)
    embedding = Column(Vector(384))