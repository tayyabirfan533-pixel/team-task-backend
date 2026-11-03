import os
import enum
import shutil
import uuid
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Date, Boolean, ForeignKey, Enum, or_, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from sqlalchemy import text
from passlib.context import CryptContext
from jose import jwt, JWTError

APP_NAME = "Team Task & Approval Workflow API"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./team_tasks.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_KEY_BEFORE_DEPLOYMENT")
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "720"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".zip"}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

class Role(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    employee = "employee"

class TaskStatus(str, enum.Enum):
    assigned = "assigned"
    in_progress = "in_progress"
    submitted = "submitted"
    revision_requested = "revision_requested"
    approved = "approved"
    rejected = "rejected"

class Priority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"

class ReviewDecision(str, enum.Enum):
    approved = "approved"
    rejected = "rejected"
    revision_requested = "revision_requested"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(Role), nullable=False, default=Role.employee)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=False)
    priority = Column(Enum(Priority), default=Priority.medium, nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.assigned, nullable=False, index=True)
    deadline = Column(DateTime, nullable=True, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    submitted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_by = relationship("User", foreign_keys=[created_by_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
    submissions = relationship("Submission", back_populates="task", cascade="all, delete-orphan", order_by="Submission.created_at")
    reviews = relationship("Review", back_populates="task", cascade="all, delete-orphan", order_by="Review.created_at")

class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, default="", nullable=False)
    attachment_name = Column(String(255), nullable=True)
    attachment_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    task = relationship("Task", back_populates="submissions")
    submitted_by = relationship("User")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    decision = Column(Enum(ReviewDecision), nullable=False)
    feedback = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    task = relationship("Task", back_populates="reviews")
    reviewer = relationship("User")

class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    details = Column(Text, default="", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    actor = relationship("User")

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user = relationship("User")

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    author = relationship("User")

Base.metadata.create_all(bind=engine)

class RegisterInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role = Role.employee

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    role: Role
    is_active: bool
    created_at: datetime

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    assigned_to_id: int
    priority: Priority = Priority.medium
    deadline: Optional[datetime] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    assigned_to_id: Optional[int] = None
    priority: Optional[Priority] = None
    deadline: Optional[datetime] = None
    status: Optional[TaskStatus] = None

class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    priority: Priority
    status: TaskStatus
    deadline: Optional[datetime]
    created_by_id: int
    assigned_to_id: int
    assigned_to_name: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime]
    completed_at: Optional[datetime]
    latest_submission_id: Optional[int] = None
    latest_feedback: Optional[str] = None
    is_overdue: bool = False

class SubmitInput(BaseModel):
    message: str = Field(default="", max_length=5000)

class ReviewInput(BaseModel):
    decision: ReviewDecision
    feedback: str = Field(min_length=2, max_length=5000)

class CommentInput(BaseModel):
    body: str = Field(min_length=1, max_length=3000)

class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    message: str
    task_id: Optional[int]
    is_read: bool
    created_at: datetime

class ReadInput(BaseModel):
    is_read: bool = True

app = FastAPI(title=APP_NAME, version="1.0.0", description="JWT-secured task assignment, submission, review, approvals, activity logs, notifications and analytics API.")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

@app.on_event("startup")
def bootstrap_admin():
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    if not email or not password:
        return
    db = SessionLocal()
    try:
        existing = db.query(User).filter(func.lower(User.email) == email.lower()).first()
        if not existing:
            db.add(User(name=os.getenv("BOOTSTRAP_ADMIN_NAME", "System Admin"), email=email.lower(), password_hash=pwd_context.hash(password), role=Role.admin))
            db.commit()
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False

def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    payload = {"sub": str(user.id), "role": user.role.value, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired authentication token", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError, TypeError):
        raise credentials_error
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise credentials_error
    return user

def require_roles(*roles: Role):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action")
        return user
    return checker

def log_action(db: Session, actor_id: int, action: str, details: str = "", task_id: Optional[int] = None):
    db.add(ActivityLog(actor_id=actor_id, task_id=task_id, action=action, details=details[:5000]))

def notify(db: Session, user_id: int, title: str, message: str, task_id: Optional[int] = None):
    db.add(Notification(user_id=user_id, title=title, message=message, task_id=task_id))

def ensure_task_access(task: Task, user: User):
    if user.role == Role.admin:
        return
    if user.role == Role.manager:
        if task.created_by_id != user.id:
            raise HTTPException(status_code=403, detail="Managers can only access tasks they created")
    elif task.assigned_to_id != user.id:
        raise HTTPException(status_code=403, detail="Employees can only access tasks assigned to them")

def get_task_or_404(db: Session, task_id: int) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

def task_to_dict(task: Task) -> dict:
    latest_submission = task.submissions[-1] if task.submissions else None
    latest_review = task.reviews[-1] if task.reviews else None
    now = datetime.utcnow()
    overdue = bool(task.deadline and task.deadline.replace(tzinfo=None) < now and task.status not in (TaskStatus.approved, TaskStatus.rejected))
    return {"id": task.id, "title": task.title, "description": task.description, "priority": task.priority, "status": task.status,
            "deadline": task.deadline, "created_by_id": task.created_by_id, "assigned_to_id": task.assigned_to_id,
            "assigned_to_name": task.assigned_to.name if task.assigned_to else "", "created_by_name": task.created_by.name if task.created_by else "",
            "created_at": task.created_at, "updated_at": task.updated_at, "submitted_at": task.submitted_at, "completed_at": task.completed_at,
            "latest_submission_id": latest_submission.id if latest_submission else None,
            "latest_feedback": latest_review.feedback if latest_review else None, "is_overdue": overdue}

@app.get("/")
def root():
    return {"name": APP_NAME, "status": "running", "docs": "/docs", "health": "/health"}

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {str(exc)}")

@app.post("/auth/register", response_model=UserOut, status_code=201)
def register(payload: RegisterInput, db: Session = Depends(get_db)):
    # Public registration may create managers/employees only. Admins must be bootstrapped via environment variables.
    if payload.role == Role.admin:
        raise HTTPException(status_code=403, detail="Admin accounts can only be created through deployment environment settings")
    email = payload.email.lower()
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(name=payload.name.strip(), email=email, password_hash=pwd_context.hash(payload.password), role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@app.post("/auth/token", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == form.username.lower()).first()
    if not user or not verify_password(form.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=401, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user}

@app.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user

@app.get("/users", response_model=List[UserOut])
def list_users(role: Optional[Role] = None, q: Optional[str] = None, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(User)
    if user.role != Role.admin:
        query = query.filter(User.is_active == True)
    if role:
        query = query.filter(User.role == role)
    if q:
        query = query.filter(or_(User.name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    return query.order_by(User.name).offset(skip).limit(limit).all()

@app.patch("/users/{user_id}/active", response_model=UserOut)
def set_user_active(user_id: int, is_active: bool, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.admin))):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id and not is_active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    target.is_active = is_active
    log_action(db, user.id, "user_activated" if is_active else "user_deactivated", f"User ID {target.id}")
    db.commit()
    db.refresh(target)
    return target

@app.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(payload: TaskCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.admin, Role.manager))):
    assignee = db.query(User).filter(User.id == payload.assigned_to_id, User.is_active == True).first()
    if not assignee:
        raise HTTPException(status_code=404, detail="Assignee not found or inactive")
    if assignee.role != Role.employee:
        raise HTTPException(status_code=400, detail="Tasks can only be assigned to employee accounts")
    task = Task(title=payload.title.strip(), description=payload.description.strip(), assigned_to_id=assignee.id, created_by_id=user.id, priority=payload.priority, deadline=payload.deadline, status=TaskStatus.assigned)
    db.add(task)
    db.flush()
    log_action(db, user.id, "task_created", f"Created and assigned task to {assignee.email}", task.id)
    notify(db, assignee.id, "New task assigned", f"You have been assigned: {task.title}", task.id)
    db.commit()
    db.refresh(task)
    return task_to_dict(task)

@app.get("/tasks")
def list_tasks(status_filter: Optional[TaskStatus] = Query(None, alias="status"), priority: Optional[Priority] = None, assignee_id: Optional[int] = None, created_by_id: Optional[int] = None, overdue_only: bool = False, q: Optional[str] = None, sort_by: str = Query("created_at", pattern="^(created_at|deadline|priority|title|updated_at)$"), sort_order: str = Query("desc", pattern="^(asc|desc)$"), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Task)
    if user.role == Role.employee:
        query = query.filter(Task.assigned_to_id == user.id)
    elif user.role == Role.manager:
        query = query.filter(Task.created_by_id == user.id)
    if status_filter:
        query = query.filter(Task.status == status_filter)
    if priority:
        query = query.filter(Task.priority == priority)
    if assignee_id:
        query = query.filter(Task.assigned_to_id == assignee_id)
    if created_by_id:
        query = query.filter(Task.created_by_id == created_by_id)
    if q:
        query = query.filter(or_(Task.title.ilike(f"%{q}%"), Task.description.ilike(f"%{q}%")))
    if overdue_only:
        query = query.filter(Task.deadline < datetime.utcnow(), Task.status.notin_([TaskStatus.approved, TaskStatus.rejected]))
    sort_column = getattr(Task, sort_by)
    query = query.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc())
    total = query.count()
    tasks = query.offset(skip).limit(limit).all()
    return {"items": [task_to_dict(t) for t in tasks], "total": total, "skip": skip, "limit": limit}

@app.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = get_task_or_404(db, task_id)
    ensure_task_access(task, user)
    return task_to_dict(task)

@app.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = get_task_or_404(db, task_id)
    if user.role not in (Role.admin, Role.manager) or (user.role == Role.manager and task.created_by_id != user.id):
        raise HTTPException(status_code=403, detail="Only the task creator or admin can edit task details")
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes:
        raise HTTPException(status_code=400, detail="Use the progress endpoint to update task status")
    if "assigned_to_id" in changes:
        assignee = db.query(User).filter(User.id == changes["assigned_to_id"], User.role == Role.employee, User.is_active == True).first()
        if not assignee:
            raise HTTPException(status_code=400, detail="Assignee must be an active employee")
        old_assignee = task.assigned_to_id
        task.assigned_to_id = assignee.id
        if old_assignee != assignee.id:
            notify(db, assignee.id, "Task assigned to you", f"Task: {task.title}", task.id)
    for field, value in changes.items():
        if field != "assigned_to_id" and value is not None:
            setattr(task, field, value)
    log_action(db, user.id, "task_updated", f"Updated fields: {', '.join(changes.keys())}", task.id)
    db.commit()
    db.refresh(task)
    return task_to_dict(task)

@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.admin, Role.manager))):
    task = get_task_or_404(db, task_id)
    if user.role == Role.manager and task.created_by_id != user.id:
        raise HTTPException(status_code=403, detail="Managers can only delete tasks they created")
    log_action(db, user.id, "task_deleted", f"Deleted task: {task.title}", None)
    db.delete(task)
    db.commit()

@app.patch("/tasks/{task_id}/progress", response_model=TaskOut)
def update_progress(task_id: int, new_status: TaskStatus, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = get_task_or_404(db, task_id)
    ensure_task_access(task, user)
    if user.role != Role.employee:
        raise HTTPException(status_code=403, detail="Only assigned employees can update progress here")
    if task.status == TaskStatus.approved:
        raise HTTPException(status_code=400, detail="Approved tasks cannot be updated")
    if new_status not in (TaskStatus.in_progress, TaskStatus.assigned):
        raise HTTPException(status_code=400, detail="Employees can set status to assigned or in_progress; submit work separately")
    old = task.status
    task.status = new_status
    log_action(db, user.id, "task_progress_updated", f"Status changed from {old.value} to {new_status.value}", task.id)
    notify(db, task.created_by_id, "Task progress updated", f"{task.title} is now {new_status.value}", task.id)
    db.commit()
    db.refresh(task)
    return task_to_dict(task)

@app.post("/tasks/{task_id}/submissions", status_code=201)
def submit_work(task_id: int, message: str = Query("", max_length=5000), attachment: Optional[UploadFile] = File(None), db: Session = Depends(get_db), user: User = Depends(require_roles(Role.employee))):
    task = get_task_or_404(db, task_id)
    ensure_task_access(task, user)
    if task.status == TaskStatus.approved:
        raise HTTPException(status_code=400, detail="Approved tasks cannot be resubmitted")
    filename = None
    saved_path = None
    if attachment:
        suffix = Path(attachment.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
        content = attachment.file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
        if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit")
        safe_name = f"{uuid.uuid4().hex}{suffix}"
        target = UPLOAD_DIR / safe_name
        with target.open("wb") as out:
            out.write(content)
        filename = Path(attachment.filename or safe_name).name
        saved_path = str(target)
    submission = Submission(task_id=task.id, submitted_by_id=user.id, message=message, attachment_name=filename, attachment_path=saved_path)
    db.add(submission)
    old_status = task.status
    task.status = TaskStatus.submitted
    task.submitted_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    log_action(db, user.id, "work_submitted", f"Submission #{submission.id}; previous status {old_status.value}", task.id)
    notify(db, task.created_by_id, "Task submitted for review", f"{user.name} submitted work for: {task.title}", task.id)
    db.commit()
    db.refresh(submission)
    return {"id": submission.id, "task_id": task.id, "message": submission.message, "attachment_name": filename, "attachment_url": f"/uploads/{Path(saved_path).name}" if saved_path else None, "created_at": submission.created_at}

@app.get("/tasks/{task_id}/submissions")
def list_submissions(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = get_task_or_404(db, task_id)
    ensure_task_access(task, user)
    rows = db.query(Submission).filter(Submission.task_id == task_id).order_by(Submission.created_at.desc()).all()
    return [{"id": s.id, "task_id": s.task_id, "submitted_by_id": s.submitted_by_id, "submitted_by_name": s.submitted_by.name, "message": s.message, "attachment_name": s.attachment_name, "attachment_url": f"/uploads/{Path(s.attachment_path).name}" if s.attachment_path else None, "created_at": s.created_at} for s in rows]

@app.post("/tasks/{task_id}/review", status_code=201)
def review_submission(task_id: int, payload: ReviewInput, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.admin, Role.manager))):
    task = get_task_or_404(db, task_id)
    if user.role == Role.manager and task.created_by_id != user.id:
        raise HTTPException(status_code=403, detail="Managers can only review tasks they created")
    if task.status != TaskStatus.submitted:
        raise HTTPException(status_code=400, detail="Only submitted tasks can be reviewed")
    if payload.decision == ReviewDecision.approved:
        task.status = TaskStatus.approved
        task.completed_at = datetime.utcnow()
    elif payload.decision == ReviewDecision.rejected:
        # Keep the rejected decision in review history, but allow employee revision and resubmission.
        task.status = TaskStatus.revision_requested
        task.completed_at = None
    else:
        task.status = TaskStatus.revision_requested
        task.completed_at = None
    review = Review(task_id=task.id, reviewer_id=user.id, decision=payload.decision, feedback=payload.feedback)
    db.add(review)
    log_action(db, user.id, "task_reviewed", f"Decision: {payload.decision.value}; feedback: {payload.feedback}", task.id)
    notify(db, task.assigned_to_id, f"Task {payload.decision.value.replace('_', ' ')}", f"{task.title}: {payload.feedback}", task.id)
    db.commit()
    db.refresh(review)
    return {"id": review.id, "task_id": task.id, "decision": review.decision, "feedback": review.feedback, "reviewer_id": user.id, "created_at": review.created_at, "task_status": task.status}

@app.get("/tasks/{task_id}/reviews")
def list_reviews(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = get_task_or_404(db, task_id)
    ensure_task_access(task, user)
    rows = db.query(Review).filter(Review.task_id == task_id).order_by(Review.created_at.desc()).all()
    return [{"id": r.id, "decision": r.decision, "feedback": r.feedback, "reviewer_id": r.reviewer_id, "reviewer_name": r.reviewer.name, "created_at": r.created_at} for r in rows]

@app.post("/tasks/{task_id}/comments", status_code=201)
def add_comment(task_id: int, payload: CommentInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = get_task_or_404(db, task_id)
    ensure_task_access(task, user)
    comment = Comment(task_id=task.id, author_id=user.id, body=payload.body.strip())
    db.add(comment)
    log_action(db, user.id, "comment_added", "Added task comment", task.id)
    db.commit()
    db.refresh(comment)
    return {"id": comment.id, "task_id": task.id, "author_id": user.id, "author_name": user.name, "body": comment.body, "created_at": comment.created_at}

@app.get("/tasks/{task_id}/comments")
def list_comments(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = get_task_or_404(db, task_id)
    ensure_task_access(task, user)
    rows = db.query(Comment).filter(Comment.task_id == task_id).order_by(Comment.created_at.asc()).all()
    return [{"id": c.id, "author_id": c.author_id, "author_name": c.author.name, "body": c.body, "created_at": c.created_at} for c in rows]

@app.get("/notifications", response_model=List[NotificationOut])
def get_notifications(unread_only: bool = False, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        query = query.filter(Notification.is_read == False)
    return query.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()

@app.patch("/notifications/{notification_id}", response_model=NotificationOut)
def update_notification(notification_id: int, payload: ReadInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")
    row.is_read = payload.is_read
    db.commit()
    db.refresh(row)
    return row

@app.post("/notifications/read-all")
def read_all_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    updated = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).update({"is_read": True})
    db.commit()
    return {"updated": updated}

@app.get("/activity-logs")
def activity_logs(task_id: Optional[int] = None, actor_id: Optional[int] = None, action: Optional[str] = None, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(ActivityLog)
    if user.role == Role.employee:
        assigned_ids = db.query(Task.id).filter(Task.assigned_to_id == user.id)
        query = query.filter(or_(ActivityLog.task_id.in_(assigned_ids), ActivityLog.actor_id == user.id))
    elif user.role == Role.manager:
        managed_ids = db.query(Task.id).filter(Task.created_by_id == user.id)
        query = query.filter(or_(ActivityLog.task_id.in_(managed_ids), ActivityLog.actor_id == user.id))
    if task_id:
        query = query.filter(ActivityLog.task_id == task_id)
    if actor_id:
        query = query.filter(ActivityLog.actor_id == actor_id)
    if action:
        query = query.filter(ActivityLog.action == action)
    total = query.count()
    rows = query.order_by(ActivityLog.created_at.desc()).offset(skip).limit(limit).all()
    return {"items": [{"id": r.id, "actor_id": r.actor_id, "actor_name": r.actor.name, "task_id": r.task_id, "action": r.action, "details": r.details, "created_at": r.created_at} for r in rows], "total": total, "skip": skip, "limit": limit}

@app.get("/analytics/dashboard")
def dashboard_analytics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Task)
    if user.role == Role.employee:
        query = query.filter(Task.assigned_to_id == user.id)
    elif user.role == Role.manager:
        query = query.filter(Task.created_by_id == user.id)
    tasks = query.all()
    now = datetime.utcnow()
    counts = {s.value: sum(1 for t in tasks if t.status == s) for s in TaskStatus}
    overdue = sum(1 for t in tasks if t.deadline and t.deadline.replace(tzinfo=None) < now and t.status not in (TaskStatus.approved, TaskStatus.rejected))
    pending_reviews = sum(1 for t in tasks if t.status == TaskStatus.submitted)
    completed = [t for t in tasks if t.status == TaskStatus.approved and t.completed_at and t.created_at]
    durations = [(t.completed_at - t.created_at).total_seconds() / 3600 for t in completed]
    avg_completion_hours = round(sum(durations) / len(durations), 2) if durations else None
    priority_counts = {p.value: sum(1 for t in tasks if t.priority == p) for p in Priority}
    return {"total_tasks": len(tasks), "status_counts": counts, "priority_counts": priority_counts, "overdue_tasks": overdue, "pending_reviews": pending_reviews, "approved_tasks": counts.get("approved", 0), "average_completion_hours": avg_completion_hours}

@app.get("/analytics/overdue")
def overdue_tasks(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Task).filter(Task.deadline < datetime.utcnow(), Task.status.notin_([TaskStatus.approved, TaskStatus.rejected]))
    if user.role == Role.employee:
        query = query.filter(Task.assigned_to_id == user.id)
    elif user.role == Role.manager:
        query = query.filter(Task.created_by_id == user.id)
    total = query.count()
    rows = query.order_by(Task.deadline.asc()).offset(skip).limit(limit).all()
    return {"items": [task_to_dict(t) for t in rows], "total": total, "skip": skip, "limit": limit}

@app.get("/analytics/pending-reviews")
def pending_reviews(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(require_roles(Role.admin, Role.manager))):
    query = db.query(Task).filter(Task.status == TaskStatus.submitted)
    if user.role == Role.manager:
        query = query.filter(Task.created_by_id == user.id)
    total = query.count()
    rows = query.order_by(Task.submitted_at.asc()).offset(skip).limit(limit).all()
    return {"items": [task_to_dict(t) for t in rows], "total": total, "skip": skip, "limit": limit}
