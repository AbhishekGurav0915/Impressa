from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Request,
    Form,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from pydantic import BaseModel
from typing import Optional  # Import Optional from typing instead of pydantic
import jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./print_jobs.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Printer(Base):
    __tablename__ = "printers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    status = Column(String)
    print_jobs = relationship("PrintJob", back_populates="printer")

class PrintJob(Base):
    __tablename__ = "print_jobs"
    id = Column(Integer, primary_key=True, index=True)
    printer_id = Column(Integer, ForeignKey("printers.id"))
    status = Column(String)
    file_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    printer = relationship("Printer", back_populates="print_jobs")

Base.metadata.create_all(bind=engine)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    client_id: Optional[str] = None  # Use Optional from typing

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/login")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    client_id = form_data.username
    password = form_data.password
    if not client_id or not password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": client_id}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

active_connections = {}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            if "client_id" in data and "token" in data:
                try:
                    payload = verify_token(data["token"])
                    client_id = payload.get("sub")
                    active_connections[client_id] = websocket
                    await websocket.send_json({"status": "connected"})
                except HTTPException as e:
                    await websocket.send_json({"error": e.detail})
            elif "print_job" in data:
                client_id = data["print_job"].get("client_id")
                if client_id in active_connections:
                    await active_connections[client_id].send_json({"print_job": data["print_job"]})
    except WebSocketDisconnect:
        for client_id, conn in list(active_connections.items()):
            if conn == websocket:
                del active_connections[client_id]
                break

@app.post("/printers/")
async def add_printer(name: str, status: str, token: str = Depends(verify_token)):
    db = SessionLocal()
    try:
        printer = Printer(name=name, status=status)
        db.add(printer)
        db.commit()
        db.refresh(printer)
        return {"printer": printer}
    finally:
        db.close()

@app.get("/printers/")
async def get_printers(token: str = Depends(verify_token)):
    db = SessionLocal()
    try:
        printers = db.query(Printer).all()
        return {"printers": printers}
    finally:
        db.close()

@app.post("/print-job/")
async def send_print_job(printer_id: int, file_url: str, copies: int = 1, token: str = Depends(verify_token)):
    db = SessionLocal()
    try:
        printer = db.query(Printer).filter(Printer.id == printer_id).first()
        if not printer:
            raise HTTPException(status_code=404, detail="Printer not found")

        print_job = PrintJob(printer_id=printer_id, file_url=file_url, status="pending")
        db.add(print_job)
        db.commit()
        db.refresh(print_job)

        for client_id, conn in active_connections.items():
            await conn.send_json({
                "print_job": {
                    "printer_id": printer_id,
                    "file_url": file_url,
                    "copies": copies
                }
            })

        return {"print_job": print_job}
    finally:
        db.close()