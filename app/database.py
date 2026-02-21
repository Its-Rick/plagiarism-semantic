from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"}
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

#M79kmdBItXJFQ8M6