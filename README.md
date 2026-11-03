# Team Task & Approval Workflow Backend

FastAPI backend for assigning team tasks, employee submissions, manager review/approval/rejection, resubmissions, attachments, notifications, activity logs, and dashboard analytics.

## Features

- JWT bearer authentication and role-based access: `admin`, `manager`, `employee`.
- Admin bootstrap through environment variables; public registration cannot create an admin.
- Task create, edit, assign, delete, search, filter, sort, paginate, progress tracking, and overdue detection.
- Employee submissions with optional attachments; supports PDF, DOC/DOCX, TXT, images, and ZIP up to the configured size.
- Review decisions: approved, rejected, or revision requested. Rejected/revision-requested tasks can be revised and resubmitted.
- Feedback and review history, task comments, activity logs, in-app notifications, and dashboard analytics.
- SQLite by default for local testing; PostgreSQL supported with `DATABASE_URL`.
- Interactive API documentation at `/docs` and health check at `/health`.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Set environment variables before first run. For local development, SQLite is used automatically. Create an admin account by setting `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` before starting the API. Use a strong password and do not commit `.env` or credentials.

```bash
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

## Render deployment

- Keep `main.py`, `requirements.txt`, and `render.yaml` at the repository root.
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- For persistent production data, create a PostgreSQL database and set `DATABASE_URL` to its internal connection URL.
- Set `SECRET_KEY` to a long random secret and set `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` in Render Environment. Do not put secrets in GitHub.
- The free web service filesystem may be ephemeral. Uploaded files and SQLite data may be lost after restarts/redeploys; use PostgreSQL plus persistent/object storage for production file retention.

## Authentication

Register a manager or employee using `POST /auth/register`. Admin accounts are created only through `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD`. Log in at `POST /auth/token` using form fields `username` (email) and `password`. Copy the returned access token and use `Authorization: Bearer <token>` for protected endpoints.

## Main endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Service/database health |
| POST | `/auth/register` | Register manager/employee |
| POST | `/auth/token` | Login and receive JWT |
| GET | `/auth/me` | Current user |
| GET | `/users` | Search users; filter by role |
| POST | `/tasks` | Admin/manager creates and assigns a task |
| GET | `/tasks` | Search/filter/sort/paginate visible tasks |
| GET | `/tasks/{task_id}` | Task details |
| PATCH | `/tasks/{task_id}` | Creator/admin updates task details |
| DELETE | `/tasks/{task_id}` | Creator/admin deletes task |
| PATCH | `/tasks/{task_id}/progress?new_status=in_progress` | Employee updates progress |
| POST | `/tasks/{task_id}/submissions?message=...` | Employee submits work; optional multipart `attachment` |
| GET | `/tasks/{task_id}/submissions` | Submission history |
| POST | `/tasks/{task_id}/review` | Manager/admin reviews submitted task |
| GET | `/tasks/{task_id}/reviews` | Review history |
| POST/GET | `/tasks/{task_id}/comments` | Add/list comments |
| GET | `/notifications` | Current user's notifications |
| PATCH | `/notifications/{notification_id}` | Mark notification read/unread |
| POST | `/notifications/read-all` | Mark all notifications read |
| GET | `/activity-logs` | Activity history, scoped by role |
| GET | `/analytics/dashboard` | Status, priority, overdue, review, completion statistics |
| GET | `/analytics/overdue` | Overdue task list |
| GET | `/analytics/pending-reviews` | Submitted tasks awaiting review |

## Demo workflow

1. Bootstrap an admin through environment variables.
2. Register a manager and employee.
3. Log in as manager, create a task and assign it to the employee's user ID.
4. Log in as employee, set progress to `in_progress`, then submit work (with optional attachment).
5. Log in as manager and call `/tasks/{task_id}/review` with `decision` equal to `approved`, `rejected`, or `revision_requested` and include feedback.
6. Check employee notifications, task status, reviews, activity logs, and `/analytics/dashboard`.
7. If rejected or revision requested, employee can revise and submit again; manager can review the new submission.

## Notes / limitations

- Notifications are stored in-app and exposed through REST endpoints. WebSocket push is not implemented in this backend version.
- Attachments are served from `/uploads`; configure durable object storage or a persistent disk for production retention.
- File extension and size are checked, but files are not malware-scanned. Restrict access and scan uploads before production use.
- This is an API-only backend; frontend dashboards are outside the assigned backend scope.
