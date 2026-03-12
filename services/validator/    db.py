from sqlmodel import SQLModel, create_engine

DATABASE_URL = "postgresql://ai:ai@ai_postgres:5432/ainetwork"

engine = create_engine(DATABASE_URL, echo=False)

def init_db():
    SQLModel.metadata.create_all(engine)

