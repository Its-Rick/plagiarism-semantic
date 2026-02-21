from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.database import Base, engine, SessionLocal
from app.schemas import AssignmentRequest
from app.models import Assignment, Sentence
from app.services.embedding_service import generate_embeddings
from app.services.plagiarism_service import check_plagiarism
from app.utils import split_sentences

Base.metadata.create_all(bind=engine)

app = FastAPI()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/assignments/upload")
def upload_assignment(data: AssignmentRequest, db: Session = Depends(get_db)):

    sentences = split_sentences(data.text)
    embeddings = generate_embeddings(sentences)

    assignment = Assignment(
        student_id=data.student_id,
        assignment_group_id=data.assignment_id
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    for i in range(len(sentences)):
        sentence_obj = Sentence(
            assignment_id=data.assignment_id,
            student_id=data.student_id,
            sentence_text=sentences[i],
            embedding=embeddings[i].tolist()
        )
        db.add(sentence_obj)

    db.commit()

    return {"message": "Assignment stored successfully"}


@app.post("/assignments/check")
def check_assignment(data: AssignmentRequest):

    sentences = split_sentences(data.text)
    embeddings = generate_embeddings(sentences)

    plagiarism_percentage, matches = check_plagiarism(
    sentences,
    embeddings,
    data.assignment_id,
    data.student_id
)

    return {
        "plagiarism_percentage": plagiarism_percentage,
        "matches": matches
    }