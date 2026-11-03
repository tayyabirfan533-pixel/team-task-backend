# Database schema / ERD

```mermaid
erDiagram
  USERS ||--o{ TASKS : creates
  USERS ||--o{ TASKS : assigned_to
  TASKS ||--o{ SUBMISSIONS : has
  USERS ||--o{ SUBMISSIONS : submits
  TASKS ||--o{ REVIEWS : receives
  USERS ||--o{ REVIEWS : reviews
  USERS ||--o{ ACTIVITY_LOGS : performs
  TASKS ||--o{ ACTIVITY_LOGS : records
  USERS ||--o{ NOTIFICATIONS : receives
  TASKS ||--o{ NOTIFICATIONS : references
  TASKS ||--o{ COMMENTS : has
  USERS ||--o{ COMMENTS : writes

  USERS {
    int id PK
    string name
    string email UK
    string password_hash
    enum role
    bool is_active
    datetime created_at
  }
  TASKS {
    int id PK
    string title
    text description
    enum priority
    enum status
    datetime deadline
    int created_by_id FK
    int assigned_to_id FK
    datetime submitted_at
    datetime completed_at
  }
  SUBMISSIONS {
    int id PK
    int task_id FK
    int submitted_by_id FK
    text message
    string attachment_name
    string attachment_path
    datetime created_at
  }
  REVIEWS {
    int id PK
    int task_id FK
    int reviewer_id FK
    enum decision
    text feedback
    datetime created_at
  }
  ACTIVITY_LOGS {
    int id PK
    int actor_id FK
    int task_id FK
    string action
    text details
    datetime created_at
  }
  NOTIFICATIONS {
    int id PK
    int user_id FK
    int task_id FK
    string title
    text message
    bool is_read
    datetime created_at
  }
  COMMENTS {
    int id PK
    int task_id FK
    int author_id FK
    text body
    datetime created_at
  }
```

## Workflow status values

`assigned`, `in_progress`, `submitted`, `revision_requested`, `approved`, `rejected`.

Review decision values: `approved`, `rejected`, `revision_requested`.
