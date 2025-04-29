from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

from config import DB_URL

Base = declarative_base()
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(100))
    chats = relationship("Chat", back_populates="user")
    prompts = relationship("Prompt", back_populates="user")
    
    total_tokens_input = Column(Integer, default=0)
    total_tokens_output = Column(Integer, default=0)
    total_cost_usd = Column(Float, default=0.0)


class Chat(Base):
    __tablename__ = "chats"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="chats")
    model = Column(String(50), nullable=False)
    
    tokens_input = Column(Integer, default=0)
    tokens_output = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    
    messages = relationship("Message", back_populates="chat")


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    chat = relationship("Chat", back_populates="messages")
    
    role = Column(String(20), nullable=False)  # user или assistant
    content = Column(Text, nullable=False)
    
    tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)


class Prompt(Base):
    __tablename__ = "prompts"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="prompts")
    
    name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)


def create_tables():
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    create_tables()