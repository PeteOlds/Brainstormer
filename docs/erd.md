# brainstormer — Entity Relationship Diagram

```mermaid
erDiagram
    USERS {
        int id PK
        string email UK
        string password_hash
        boolean is_active
        datetime created_at
    }
