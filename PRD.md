# Product Requirements Document (PRD): Brainstormer

AI-Driven Business Idea Generator & Evaluator

## 1. Executive Summary

This document outlines the product requirements for a web-based (and future Android-compatible) platform designed to automatically generate, evaluate, and track business ideas using local Ollama-hosted LLMs.

  

The system operates on an automated background pipeline: administrators configure recurring prompts, the backend executes them via a local Ollama server, and the resulting ideas populate a centralized dashboard where users and administrators can review, vote on, and execute follow-up actions (e.g., competitive analysis, prompt refinement).

  

## 2. Goals & Objectives

- **Automate Idea Generation:** Periodically trigger specialized prompts via local LLMs to generate novel business concepts hands-free.
    
      
    
- **Streamline Evaluation:** Provide an interface for upvoting/downvoting ideas and tracking their lifecycle status.
    
      
    
- **Enable Interactive Refinement:** Allow administrators to perform secondary AI actions on promising ideas (e.g., identifying competitors, refining value propositions).
    
      
    
- **Cost & Privacy Control:** Leverage a local Ollama instance to eliminate per-token API costs and ensure data privacy.
    
      
    

## 3. User Roles & Permissions

|**Role**|**Access Level & Permissions**|
|---|---|
|**Administrator**|Full system access: configure AI prompts/intervals, view ideas, change idea status, execute secondary actions (Refine, Competitors), upvote/downvote.|
|**User** _(Phase 2)_|Read-only access to published ideas; ability to upvote/downvote once per idea.|

## 4. Feature Requirements

### 4.1. Admin Prompt Configuration & Management

The Administrator needs a management panel to configure recurring background prompts.

  

- **Maximum Prompt Limit:** Up to 10 active prompt configurations.
    
      
    
- **Prompt Schema:**
    
      
    1. **Title:** Short label for reference (e.g., "SaaS Tool for Local Businesses").
        
          
        
    2. **Prompt Body:** System prompt text sent to Ollama (hidden from regular users).
        
          
        
    3. **Execution Interval:** Cron schedule or pre-set frequency (e.g., Every 6 hours, Daily, Weekly).
        
          
        
    4. **AI Model Selection:** Dynamic dropdown fetching available models from the local Ollama instance (e.g., `llama3:8b`, `mistral`, `qwen2.5`).
        
          
        
    5. **Status:** Active / Paused toggle.
        
          
        

### 4.2. Automated Execution Engine (Scheduler & Ollama Integration)

- **Background Runner:** A background worker (e.g., Celery, Redis Queue, or Cron) checks scheduled intervals for active prompts.
    
      
    
- **Ollama API Client:** Connects to the local Ollama endpoint (`http://localhost:11434/api/generate` or `/api/chat`).
    
      
    
- **Ingestion Pipeline:** Upon completion, raw response text is processed and stored in the database.
    
      
    

### 4.3. Ideas Dashboard & Display Table

A responsive, table-formatted view displaying generated ideas.

  

- **Displayed Columns:**
    
      
    - **Reference ID:** Auto-generated unique identifier (e.g., `IDEA-1042`).
        
          
        
    - **Timestamp:** Human-readable generation date/time (e.g., _Oct 24, 2026 at 2:30 PM_).
        
          
        
    - **Prompt Title:** Reference name of the source prompt.
        
          
        
    - **Generated Response:** Rendered summary text with expandable modal/drawer for full details.
        
          
        
    - **Status:** Current state badge (_New_, _Under Consideration_, _Discarded_).
        
          
        
    - **Voting Score:** Combined score (+ / -) with upvote/downvote buttons.
        
          
        
    - **Actions:** Quick action trigger menu (Admin only).
        
          
        

### 4.4. Voting System

- Users can click **Upvote (+1)** or **Downvote (-1)** on an idea.
    
      
    
- Each user/session can cast only **one vote per idea** (can toggle or rescind).
    
      
    
- Total net score is displayed inline in the table.
    
      
    

### 4.5. Idea Status Management

Administrators can update an idea's lifecycle state via an inline dropdown:

  

- **New:** Default status for freshly generated ideas.
    
      
    
- **Consideration:** Promising ideas slated for further investigation.
    
      
    
- **Discarded:** Rejected ideas (filtered out by default, but retrievable).
    
      
    

### 4.6. Secondary Action Triggers (Iterative AI Context)

Administrators can trigger follow-up AI prompts on existing ideas. Clicking an action spawns a secondary prompt sent to Ollama, appending the output to the idea's detail view.

  

- **Action 1: Refine Idea**
    
      
    - _Prompt logic:_ Takes original idea output and executes: _"Refine this business concept into a clear 1-paragraph elevator pitch, core target audience, and primary revenue model."_
        
          
        
- **Action 2: Competitor Analysis**
    
      
    - _Prompt logic:_ Takes original idea output and executes: _"Identify potential direct/indirect competitors (both global and local), key differentiators, and potential barriers to entry for this concept."_
        
          
        
- **Extensibility:** Interface designed to easily add new context-aware actions in future releases.
    
      
    

## 5. Mobile & Platform Requirements (Phase 2 - Android)

- **Responsive Architecture:** UI designed mobile-first using Tailwind CSS with Flask + Jinja2 templates to prepare for PWA packaging.
    
    
    
- **API First:** Backend exposed via REST so the Android app can consume identical endpoints for dashboard views and voting.
    
      
    

## 6. Suggested Feature Extensions (Enhancements to Consider)

To maximize the utility of an automated business idea generator, consider adding these complementary features:

  

### 💡 High-Value Feature Enhancements

1. **Feasibility / Viability Scoring Prompt (Automated Evaluation):**
    
      
    - _Concept:_ Automatically run a secondary "Evaluator" prompt immediately after generation. Have Ollama rate the idea from 1–10 on _Technical Feasibility_, _Market Demand_, and _Capital Requirement_, creating an aggregate score to order the dashboard automatically.
        
          
        
2. **Export & Pitch Deck Generator:**
    
      
    - _Concept:_ Allow admins to select an idea in "Consideration" and click **"Export Pitch Outline"** to download a formatted Markdown, PDF, or Notion page ready for team review.
        
          
        
3. **Structured Output Enforcement (JSON Mode):**
    
      
    - _Concept:_ Require Ollama responses to format as JSON (supported natively in Ollama) with fields like `Problem`, `Solution`, `Target Audience`, and `Est. ARR`. This keeps the dashboard table uniform rather than showing unstructured wall-of-text responses.
        
          
        
4. **Duplicate / Similarity Detection:**
    
      
    - _Concept:_ Use simple vector embeddings (via an Ollama embedding model like `nomic-embed-text`) to flag duplicate or very similar ideas generated across different runs.
        
          
        
5. **Prompt Experimentation / Playground:**
    
      
    - _Concept:_ A "Test Run" button in the admin configuration panel allowing administrators to dry-run a prompt once before committing it to a recurring schedule.
        
          
        

## 7. Technical & Non-Functional Requirements

- **Tech Stack Recommendations:**
    
    
    - **Frontend:** Flask + Jinja2 templates with Tailwind CSS for responsive table components.
        
        
        
    - **Backend:** Python Flask with Flask-SQLAlchemy, Flask-Migrate, Celery for background tasks.
        
        
        
    - **Database:** PostgreSQL with SQLAlchemy ORM (Alembic for migrations).
        
        
        
    - **Task Queue:** Redis + Celery (separate queues for Ollama and default tasks).
        
        
        
    - **AI Provider:** Local Ollama API runner.
        
          
        
- **Error Handling & Resilience:**
    
      
    - Handles scenario where local Ollama server is offline (retry queue with exponential backoff).
        
          
        
    - Gracefully truncates or streams long AI responses to avoid timeout errors.





## 1. System Architecture Overview

The system follows a modular **API-First Architecture** with an asynchronous background worker system to manage heavy LLM workloads without blocking user HTTP requests.

```
+---------------------------------------------------------------------------------+
|                                 CLIENT LAYER                                    |
|   +------------------------------------+   +--------------------------------+   |
|   |   Web App (Flask + Jinja2)         |   |   Android App (PWA / Native)   |   |
|   +-----------------+------------------+   +---------------+----------------+   |
+---------------------|--------------------------------------|--------------------+
                      |                                      |
                      +------------------+-------------------+
                                           | REST / HTTP API
+----------------------------------------v----------------------------------------+
|                                API GATEWAY / SERVER                             |
|    Flask Controller & Authorization (JWT Middleware via flask-appkit)          |
+---------------------+-------------------------------+---------------------------+
                      |                               |
        Reads/Writes  |                               | Pushes Jobs
                      v                               v
+---------------------+--------+            +---------+---------------------------+
|      PRIMARY DATABASE        |            |         REDIS TASK QUEUE            |
|  (PostgreSQL)                |            |   (Background Jobs & Schedules)   |
+------------------------------+            +---------+---------------------------+
                                                      |
                                                      | Picks up Job
                                                      v
                                            +---------+---------------------------+
                                            |   OLLAMA WORKER SERVICE             |
                                            |   (Celery Worker)                   |
                                            +---------+---------------------------+
                                                      |
                                                      | Local HTTP Requests
                                                      v
                                            +---------+---------------------------+
                                            |     LOCAL OLLAMA INSTANCE           |
                                            |   (http://localhost:11434)          |
                                            +-------------------------------------+
```

### Component Details

- **Client Layer:** Responsive Flask + Jinja2 templates with Tailwind CSS, communicating via standard REST APIs. Prepared for direct integration into an Android PWA shell or native HTTP client.
    
- **API Gateway / Backend Server:** Flask handles user authentication (flask-appkit JWT), RBAC, request routing, voting logic, and status updates.
    
- **Database Layer:** PostgreSQL managed via Flask-SQLAlchemy and Alembic migrations to store users, prompt configurations, generated ideas, action logs, and voting history.
    
- **Redis Task Queue & Scheduler:** Decouples API responses from long-running LLM generation tasks. Celery Beat periodically evaluates prompt execution intervals and enqueues generation jobs.
    
- **Ollama Worker Service:** Dedicated Celery worker (concurrency=1) that dequeues jobs, structures prompt payloads, calls the local Ollama API (`/api/generate` with `format: "json"`), validates response against Pydantic schemas, and updates database state.
    

## 2. API Endpoints Specification

### Base URL: `/api/v1`

### A. Ollama Integration & Models

Endpoints for discovering system LLM capabilities.

#### `GET /ollama/models`

- **Access:** Admin Only
    
- **Description:** Proxies query to local Ollama instance (`GET http://localhost:11434/api/tags`) to pull currently installed models for prompt configuration.
    
- **Response (200 OK):**
    

JSON

```
{
  "models": [
    { "name": "llama3:8b", "modified_at": "2026-08-15T10:20:00Z", "size": 4661224676 },
    { "name": "mistral:7b", "modified_at": "2026-08-20T14:10:00Z", "size": 4109844838 },
    { "name": "qwen2.5:14b", "modified_at": "2026-09-01T09:00:00Z", "size": 9012344838 }
  ]
}
```

### B. Prompt Configuration Management

Endpoints to manage scheduled background prompts (Up to 10 active).

#### `GET /prompts`

- **Access:** Admin Only
    
- **Description:** List all active and inactive configured background prompts.
    
- **Response (200 OK):**
    

JSON

```
{
  "prompts": [
    {
      "id": "p-101",
      "title": "SaaS Tools for Micro-Businesses",
      "prompt_text": "Generate a unique B2B SaaS idea targeting local micro-businesses...",
      "interval_minutes": 1440,
      "model": "llama3:8b",
      "is_active": true,
      "last_run_at": "2026-09-02T12:00:00Z",
      "next_run_at": "2026-09-03T12:00:00Z"
    }
  ]
}
```

#### `POST /prompts`

- **Access:** Admin Only
    
- **Description:** Create a new automated execution prompt. Enforces max active limit (10).
    
- **Request Body:**
    

JSON

```
{
  "title": "Consumer Mobile App Ideas",
  "prompt_text": "Brainstorm 1 consumer mobile application addressing daily productivity...",
  "interval_minutes": 720,
  "model": "qwen2.5:14b"
}
```

#### `PATCH /prompts/{prompt_id}`

- **Access:** Admin Only
    
- **Description:** Update interval, model, text, or toggle active status (`is_active: true/false`).
    

#### `POST /prompts/{prompt_id}/run-now`

- **Access:** Admin Only
    
- **Description:** Trigger immediate out-of-schedule execution of a specific prompt via background worker.
    

### C. Ideas & Dashboard Management

Endpoints for serving and interacting with generated ideas.

#### `GET /ideas`

- **Access:** Public / All Authenticated Users
    
- **Description:** Fetch paginated ideas for the dashboard with optional filtering.
    
- **Query Parameters:** `page`, `limit`, `status` (`NEW`, `CONSIDERATION`, `DISCARDED`), `sort_by` (`votes`, `created_at`).
    
- **Response (200 OK):**
    

JSON

```
{
  "total": 42,
  "page": 1,
  "ideas": [
    {
      "id": "idea-904",
      "reference_code": "IDEA-1042",
      "prompt_title": "SaaS Tools for Micro-Businesses",
      "summary": "AI-powered automated inventory audit tool using smartphone photos.",
      "content": "Full Markdown / Text output generated by Ollama...",
      "status": "CONSIDERATION",
      "net_votes": 8,
      "user_vote": 1,
      "created_at": "2026-09-02T14:30:00Z",
      "actions_run": ["REFINE", "COMPETITOR_ANALYSIS"]
    }
  ]
}
```

#### `GET /ideas/{idea_id}`

- **Access:** Public / All Authenticated Users
    
- **Description:** Fetch complete idea details including history of executed secondary actions.
    

#### `PATCH /ideas/{idea_id}/status`

- **Access:** Admin Only
    
- **Description:** Change an idea's status.
    
- **Request Body:**
    

JSON

```
{
  "status": "CONSIDERATION"
}
```

### D. Voting System

#### `POST /ideas/{idea_id}/vote`

- **Access:** All Authenticated Users
    
- **Description:** Cast an upvote (+1) or downvote (-1). Rescinds or flips vote if called again by the same user.
    
- **Request Body:**
    

JSON

```
{
  "direction": 1
}
```

- **Response (200 OK):**
    

JSON

```
{
  "idea_id": "idea-904",
  "net_votes": 9,
  "current_user_vote": 1
}
```

### E. Secondary AI Actions Pipeline

Endpoints for executing follow-up AI tasks on existing ideas.

#### `POST /ideas/{idea_id}/actions`

- **Access:** Admin Only
    
- **Description:** Submit an idea to Ollama for secondary processing. Executes asynchronously and appends result to idea record.
    
- **Request Body:**
    

JSON

```
{
  "action_type": "COMPETITORS",
  "model_override": "llama3:8b"
}
```

- **Response (202 Accepted):**
    

JSON

```
{
  "job_id": "job-8810",
  "status": "PENDING",
  "message": "Secondary analysis enqueued for processing."
}
```

#### `GET /ideas/{idea_id}/actions`

- **Access:** All Authenticated Users
    
- **Description:** Fetch output history from all secondary actions run on an idea.
    
- **Response (200 OK):**
    

JSON

```
{
  "idea_id": "idea-904",
  "results": [
    {
      "action_type": "REFINE",
      "executed_at": "2026-09-02T15:00:00Z",
      "output": "Elevator Pitch: ... Target Audience: ... Revenue Model: ..."
    },
    {
      "action_type": "COMPETITORS",
      "executed_at": "2026-09-02T15:05:00Z",
      "output": "Direct Competitors: Sortly, Orca Scan. Differentiator: ..."
    }
  ]
}
```


Here are production-ready prompt templates designed for your local Ollama instance.

To ensure clean execution and prevent unstructured "wall-of-text" responses, these templates instruct the model to return **JSON formatted outputs**. Most modern local LLMs (such as `llama3`, `mistral`, and `qwen2.5`) natively support standard JSON outputs, making them simple to parse and store in your database.

## 1. Action: "Refine Idea"

**Goal:** Take a raw, potentially vague business concept and compress it into a clear pitch, target persona, primary value proposition, and revenue model.

Plaintext

```
You are an expert startup advisor and product strategist. Your task is to analyze and refine a raw business idea concept into a clear, actionable business outline.

### RAW BUSINESS IDEA:
{{ORIGINAL_IDEA_CONTENT}}

---

### INSTRUCTIONS:
1. Strip away fluff and focus on clarity.
2. Structure your output STRICTLY as a valid JSON object matching the key schema provided below. Do not include introductory text, markdown wrappers (e.g. ```json), or trailing commentary outside the JSON object.

### OUTPUT JSON SCHEMA:
{
  "elevator_pitch": "A 1-2 sentence compelling summary of the business concept.",
  "target_audience": "Specific user personas or business tiers most likely to pay for this.",
  "core_value_proposition": "The single primary benefit or problem solved for the user.",
  "monetization_strategy": "Primary revenue streams (e.g. Freemium SaaS, Pay-per-transaction, Subscription tiers)."
}
```

## 2. Action: "Competitor Analysis"

**Goal:** Identify direct and indirect competitors, point out strategic vulnerabilities, and highlight potential barriers to entry.

Plaintext

```
You are a competitive intelligence and market research analyst. Analyze the following business idea and provide a structured landscape assessment.

### BUSINESS IDEA:
{{ORIGINAL_IDEA_CONTENT}}

---

### INSTRUCTIONS:
1. Identify existing companies, legacy solutions, or alternative workarounds.
2. Structure your output STRICTLY as a valid JSON object matching the schema below. Do not output conversational filler or prose outside the JSON object.

### OUTPUT JSON SCHEMA:
{
  "direct_competitors": [
    {
      "name": "Competitor / Tool Name",
      "description": "Brief summary of what they do.",
      "advantage_over_idea": "Where this competitor currently wins."
    }
  ],
  "indirect_competitors": [
    "Workaround 1 (e.g. Excel spreadsheets)",
    "Workaround 2 (e.g. Manual agency service)"
  ],
  "differentiator": "The key feature or positioning that gives this new idea an edge.",
  "barriers_to_entry": [
    "Potential technical or market obstacle 1",
    "Potential technical or market obstacle 2"
  ]
}
```

## 3. Action: "Feasibility Scoring" (Automated Evaluator)

**Goal:** Automatically evaluate generated ideas on a numeric scale across key execution parameters (Technical, Demand, Capital) to enable sorting on the frontend table.

Plaintext

```
You are a venture capital analyst specializing in early-stage project feasibility. Evaluate the business idea below across three core metrics on a scale of 1 to 10 (where 10 is easiest / highest potential).

### BUSINESS IDEA:
{{ORIGINAL_IDEA_CONTENT}}

---

### INSTRUCTIONS:
1. Assign integer scores (1 to 10) based on realistic market conditions and development complexity.
2. Provide short 1-sentence justifications for each score.
3. Calculate the overall average score as a float rounded to 1 decimal place.
4. Output STRICTLY a valid JSON object matching the schema below.

### OUTPUT JSON SCHEMA:
{
  "overall_score": 7.3,
  "scores": {
    "technical_feasibility": {
      "score": 8,
      "reasoning": "Standard web app stack with modern APIs; low technical risk."
    },
    "market_demand": {
      "score": 7,
      "reasoning": "High pain point for local businesses, though customer acquisition may be slow."
    },
    "capital_efficiency": {
      "score": 7,
      "reasoning": "Can be launched as a lean MVP without massive upfront infrastructure cost."
    }
  },
  "verdict": "RECOMMENDED" // Options: "RECOMMENDED", "PROCEED WITH CAUTION", "HIGH RISK"
}
```

## Implementation Tips for Ollama

1. **System Prompt vs. User Prompt:** Pass the `You are an expert...` intro as the `system` parameter in the Ollama API, and the `### RAW BUSINESS IDEA...` section as the `user` prompt.
    
2. **Ollama Format Option:** When calling Ollama's API (`/api/generate` or `/api/chat`), set `"format": "json"` in the request body. This forces Ollama's sampler to constrain generation to valid JSON strings:
    
    JSON
    
    ```
    {
      "model": "llama3:8b",
      "prompt": "...user prompt here...",
      "format": "json",
      "stream": false
    }
    ```


Here is the complete SQLite DDL (Data Definition Language) script equivalent to the PRD requirements and Prisma schema.

SQLite handles dynamic typing natively and doesn't support custom `ENUM` types directly, so string validation is enforced using `CHECK` constraints, and ISO-8601 formatted timestamps are handled via standard text functions.

SQL

```
-- Enable Foreign Key Constraints in SQLite
PRAGMA foreign_keys = ON;

-- ==========================================
-- 1. USERS TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,                       -- UUID v4 string
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    role TEXT NOT NULL DEFAULT 'USER' CHECK(role IN ('ADMIN', 'USER')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ==========================================
-- 2. PROMPT CONFIGURATIONS TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS prompt_configs (
    id TEXT PRIMARY KEY,                       -- UUID v4 string
    title TEXT NOT NULL,
    prompt_body TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL,
    model_name TEXT NOT NULL,                  -- e.g., 'llama3:8b'
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)), -- Boolean flag
    last_run_at TEXT,                          -- ISO-8601 Timestamp
    next_run_at TEXT,                          -- ISO-8601 Timestamp
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ==========================================
-- 3. IDEAS TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS ideas (
    id TEXT PRIMARY KEY,                       -- UUID v4 string
    reference_code TEXT NOT NULL UNIQUE,       -- Human readable (e.g., 'IDEA-1042')
    prompt_title TEXT NOT NULL,                -- Historical snapshot of prompt title
    raw_content TEXT NOT NULL,                 -- Complete text output from Ollama
    structured_content TEXT,                   -- JSON string format
    status TEXT NOT NULL DEFAULT 'NEW' CHECK(status IN ('NEW', 'CONSIDERATION', 'DISCARDED')),
    
    -- Cached voting metrics for quick table sorting
    upvotes_count INTEGER NOT NULL DEFAULT 0,
    downvotes_count INTEGER NOT NULL DEFAULT 0,
    net_score INTEGER NOT NULL DEFAULT 0,
    
    feasibility_score REAL,                    -- Numeric score from secondary evaluator
    prompt_config_id TEXT,                     -- FK to prompt configuration
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    
    FOREIGN KEY (prompt_config_id) REFERENCES prompt_configs(id) ON DELETE SET NULL
);

-- Performance Indexes for Dashboard Queries
CREATE INDEX IF NOT EXISTS idx_ideas_status ON ideas(status);
CREATE INDEX IF NOT EXISTS idx_ideas_net_score ON ideas(net_score DESC);
CREATE INDEX IF NOT EXISTS idx_ideas_created_at ON ideas(created_at DESC);

-- ==========================================
-- 4. SECONDARY ACTION RESULTS TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS secondary_action_results (
    id TEXT PRIMARY KEY,                       -- UUID v4 string
    idea_id TEXT NOT NULL,                     -- FK to target idea
    action_type TEXT NOT NULL CHECK(action_type IN ('REFINE', 'COMPETITORS', 'FEASIBILITY_SCORE')),
    model_used TEXT NOT NULL,
    result_data TEXT NOT NULL,                 -- JSON string containing structured response
    executed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    
    FOREIGN KEY (idea_id) REFERENCES ideas(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_action_results_idea_id ON secondary_action_results(idea_id);

-- ==========================================
-- 5. VOTES TABLE (Ensures 1 Vote per User per Idea)
-- ==========================================
CREATE TABLE IF NOT EXISTS votes (
    id TEXT PRIMARY KEY,                       -- UUID v4 string
    user_id TEXT NOT NULL,
    idea_id TEXT NOT NULL,
    value INTEGER NOT NULL CHECK(value IN (-1, 1)), -- +1 for Upvote, -1 for Downvote
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (idea_id) REFERENCES ideas(id) ON DELETE CASCADE,
    
    -- Enforces one vote record per user per idea
    UNIQUE (user_id, idea_id)
);

-- ==========================================
-- 6. STATUS HISTORY AUDIT LOG TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS idea_status_history (
    id TEXT PRIMARY KEY,                       -- UUID v4 string
    idea_id TEXT NOT NULL,
    changed_by_id TEXT NOT NULL,
    old_status TEXT NOT NULL CHECK(old_status IN ('NEW', 'CONSIDERATION', 'DISCARDED')),
    new_status TEXT NOT NULL CHECK(new_status IN ('NEW', 'CONSIDERATION', 'DISCARDED')),
    changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    
    FOREIGN KEY (idea_id) REFERENCES ideas(id) ON DELETE CASCADE,
    FOREIGN KEY (changed_by_id) REFERENCES users(id) ON DELETE CASCADE
);
```

### Automated Vote Score Triggers (Optional Optimization)

To keep `upvotes_count`, `downvotes_count`, and `net_score` in sync on the `ideas` table automatically when votes are added, updated, or deleted, you can optionally execute these SQLite triggers:

SQL

```
-- Trigger on new vote insertion
CREATE TRIGGER IF NOT EXISTS trg_vote_after_insert
AFTER INSERT ON votes
BEGIN
    UPDATE ideas 
    SET 
        upvotes_count = (SELECT COUNT(*) FROM votes WHERE idea_id = NEW.idea_id AND value = 1),
        downvotes_count = (SELECT COUNT(*) FROM votes WHERE idea_id = NEW.idea_id AND value = -1),
        net_score = (SELECT COALESCE(SUM(value), 0) FROM votes WHERE idea_id = NEW.idea_id)
    WHERE id = NEW.idea_id;
END;

-- Trigger on vote direction update (+1 to -1 or vice-versa)
CREATE TRIGGER IF NOT EXISTS trg_vote_after_update
AFTER UPDATE ON votes
BEGIN
    UPDATE ideas 
    SET 
        upvotes_count = (SELECT COUNT(*) FROM votes WHERE idea_id = NEW.idea_id AND value = 1),
        downvotes_count = (SELECT COUNT(*) FROM votes WHERE idea_id = NEW.idea_id AND value = -1),
        net_score = (SELECT COALESCE(SUM(value), 0) FROM votes WHERE idea_id = NEW.idea_id)
    WHERE id = NEW.idea_id;
END;

-- Trigger on vote removal
CREATE TRIGGER IF NOT EXISTS trg_vote_after_delete
AFTER DELETE ON votes
BEGIN
    UPDATE ideas 
    SET 
        upvotes_count = (SELECT COUNT(*) FROM votes WHERE idea_id = OLD.idea_id AND value = 1),
        downvotes_count = (SELECT COUNT(*) FROM votes WHERE idea_id = OLD.idea_id AND value = -1),
        net_score = (SELECT COALESCE(SUM(value), 0) FROM votes WHERE idea_id = OLD.idea_id)
    WHERE id = OLD.idea_id;
END;
```


## 1. UX & Admin Workflow Enhancements

- **Prompt Variations & Temperature Control (A/B Prompting):**
    
    Allow admins to associate a temperature setting (e.g., `0.2` for logical/structured outputs vs. `0.8` for creative brainstorming) with each configured prompt. Adding an option to run A/B variations of a prompt helps fine-tune which framing generates higher-rated ideas.
    
- **Inline Markdown & Rich Card Views:**
    
    In addition to the dense tabular view, include a **"Card Grid View"** or a side-drawer preview. Since LLMs generate rich text, rendering Markdown (bullet points, bold text, code blocks) directly in a preview panel will make long-form responses much easier to digest.
    
- **Bulk Actions & Filtering Presets:**
    
    Provide quick filter presets on the dashboard (e.g., _Highest Rated_, _Needs Review_, _Has Competitor Analysis_), along with bulk status changes so admins can discard weak batch runs with a single click.
    

## 2. Technical & Pipeline Optimizations

- **Automated JSON Validation & Retry Loop:**
    
    Small local models (e.g., 7B or 8B parameter variants) occasionally output malformed JSON or wrap output in extra text. Add a lightweight fallback handler in your backend worker: if JSON parsing fails on the Ollama response, automatically trigger a single retry with a strict formatting instruction or pass it through a lightweight parser fix before database insertion.
    
- **Streaming Responses to Dashboard for On-Demand Actions:**
    
    When an admin triggers an on-demand secondary action (_Refine_ or _Competitors_), stream the Ollama output via Server-Sent Events (SSE) or WebSockets. Visual feedback during a 10–20 second LLM generation prevents the user interface from feeling frozen.
    
- **Resource Queue & Rate Limiting for Local Ollama:**
    
    Running sequential background prompts alongside on-demand user actions on a single local GPU/CPU can cause VRAM thrashing or high latency. Implement a strict queue concurrency limit (e.g., `max_concurrency = 1`) in your task runner (APScheduler/Celery) to prevent simultaneous Ollama calls from clogging system resources.
    

## 3. High-Value Expansion Features

- **Auto-Tagging & Categorization Engine:**
    
    Include a lightweight tag generator post-ingestion (e.g., `B2B`, `SaaS`, `Hardware`, `Fintech`, `Mobile App`). This allows filtering and grouping ideas by industry domain over time.
    
- **Embedding-Based Duplicate Detection:**
    
    Over time, recurring prompt runs will inevitably generate similar ideas. Use Ollama’s local embedding endpoint (using models like `nomic-embed-text`) to compute vector embeddings of incoming ideas, flagging any concept that has a high similarity score (e.g., >85%) with an existing idea in the database.
    
- **One-Click Export & Knowledge Base Integration:**
    
    Allow admins to export shortlisted ideas (or an entire idea bundle with its refinement and competitor context) directly to **Markdown**, **PDF**, or external tools like **Notion** and **GitHub Issues** to kickstart development.## 8. UI/UX Improvement Plan (Sept 2026)

> STATUS (v0.3.7, 2026-09-13): all items §8.1–§8.8 built, tested (107 passed) and live.
> Follow-ups also built: server-side `?model=` on ideas API (distinct model counts), server-side run-stream
> filters, Ideas/Runs-by-Status split, model-only timing view, burst runs (up to 5), summary teaser with
> richness chips, dropdown overlap fix, no-cache headers on HTML, logout/refresh-token fixes.

Decisions locked with product owner: `/ideas` is the single ideas list (`/dashboard` redirects to it); sessions use a 24h access token; mobile ideas display uses stacked cards. Design guidance: dense-dashboard rhythm (8px base, tabular-nums for metrics), every clickable tile/row gets `cursor-pointer` + hover state + visible keyboard focus, 150–300ms transitions, verified at 375px.

Suggested build order (value ÷ effort): §8.3 session → §8.7 ideas menu → §8.4 users columns → §8.1 activity → §8.2 navigation → §8.6 mobile cards → §8.5 generation params (needs migration).

### 8.1 `/admin/activity` dashboard (Operate mode: scanability first)

**Info tiles become links.** There is no standalone runs page, and runs ≠ ideas, so tiles link back to `/admin/activity` with a `run_status` query param that filters the Recent runs list client-side (Alpine reads it on init; default = all):
- TOTAL RUNS → `/admin/activity?run_status=` (all)
- SUCCESS RATE → `?run_status=SUCCESS`
- AVG GENERATION → no link (unchanged)
- PENDING RUNS → `?run_status=PENDING` (also filter Live now list)
- FAILED RUNS → `?run_status=FAILED`
- Tiles get `cursor-pointer`, hover ring, `aria-label` ("Show failed runs"); active filter shown as a dismissible chip above Recent runs.

**Layout reorder.** Move the four insight panels above Recent runs / Live now, in a 2-col grid (`grid-cols-1 lg:grid-cols-2`): row 1 = Ideas by Prompt + Ideas by Model; row 2 = Speed by model + Ideas by Status. Rename "Most fruitful prompts" → **"Ideas by Prompt"**. All four panels share one card component (same padding, heading scale, bar height) — today their widths/padding drift.

**Every row links somewhere.**
- Ideas by Prompt rows → `/ideas?prompt=<id>` (already partially wired via `data-prompt`; make the whole row clickable, not just text).
- Ideas by Model rows → `/ideas?model=<name>` (same treatment).
- Ideas by Status rows → already link; keep.
- Speed by model rows → `/admin/activity?model=<name>` filtering Recent runs (requires adding `model` to the run payload in the activity stats endpoint).
- Pre-req: verify `/ideas` honours `status`, `model`, `prompt` query params end-to-end; extend where missing.

Acceptance: each tile/row navigates with keyboard (Tab + Enter) as well as mouse; panels align at 1024px and 1440px.

### 8.2 Navigation: one source of truth

Today the same links exist in three places: sidebar (desktop), header (desktop), user dropdown (Dashboard/Prompts/Ideas repeated again) — and `/ideas` vs `/dashboard` show the same list.
- Single nav partial consumed by sidebar, header, and dropdown (no more copy-pasted link lists drifting apart).
- Sidebar stays desktop-only (`lg+`); header keeps Dashboard→Ideas/Prompts/Ideas links for mobile; user dropdown drops the Dashboard/Prompts/Ideas repeats and keeps Admin Panel + Logout.
- `/dashboard` route becomes a 302 redirect to `/ideas`; update `url_for('pages.dashboard')` call sites (sidebar) to the ideas endpoint.
- Active-link highlighting (aria-current) in all three consumers.

Acceptance: add/remove a link once, it changes everywhere; no dead `/dashboard` references.

### 8.3 Session length: 24 hours

Frequent logouts are caused by the 15-minute access token (`JWT_ACCESS_TOKEN_EXPIRES=900`) with no silent refresh in the UI.
- Set `JWT_ACCESS_TOKEN_EXPIRES=86400` via env (no code change; cookie `max_age` derives from the same config). Refresh tokens unchanged (7d, 30d with Remember Me).
- No migration; existing tokens age out naturally.
- Security note (Guardrail): a 24h bearer token widens the leak window. Accepted trade-off for a single-admin homelab tool; revisit silent refresh if multi-user arrives (Phase 2).

Acceptance: fresh login survives 24h of use without re-login, Remember Me or not.

### 8.4 `/admin/users`: Last Login + Number of Logins

- `users` table: add `last_login_at` (nullable DateTime) and `login_count` (int, default 0). New Alembic migration; existing rows read "Never" / 0.
- Login route sets both on every successful login (`last_login_at = now`, `login_count += 1`).
- Table gains two sortable columns; nulls sort last. No PII change (timestamps of own users, admin-visible only).

Acceptance: log in twice as a user; admin sees count 2 and a current timestamp.

### 8.5 Prompt generation params (create + edit)

New "Generation" section at the end of `/prompts/create` (and edit), each field with a tooltip (`?` icon, `title` + Alpine popover on tap for mobile):

| Param | Default | Range (API 400s otherwise) | Tooltip |
|---|---|---|---|
| temperature (exists) | 0.7 | 0–2 | Higher = wilder ideas; lower = safer, structured output |
| top_p | 0.9 | 0–1 | Nucleus sampling; pairs with temperature — lower = more focused |
| repeat_penalty | 1.1 | 0–2 | >1 discourages repetition and rambling |
| num_predict | 1000 | 1–4096 | Max tokens per run; ideas need ~500, rest is headroom |
| seed | empty (= random) | ≥ 0 or null | Empty = random each run. Set a number to reproduce runs. |
| keep_alive | 2h | duration string (`30m`, `2h`, `0` = unload) | How long Ollama keeps the model warm between runs |

Backend: `prompt_configs` columns (`top_p` float 0.9, `repeat_penalty` float 1.1, `num_predict` int 1000, `seed` int nullable, `keep_alive` string "2h"); PATCH/POST validation mirrors `interval_minutes` (400 on out-of-range — clamp nothing silently); worker passes them into `options`/`keep_alive` on every generate + secondary-action call; `to_dict` includes them. Frontend: same fields on edit form, prefilled from API.

Acceptance: out-of-range value → 400 with message; seeded re-run reproduces output; `keep_alive: 0` unloads the model.

### 8.6 Ideas list on mobile: stacked cards

Replace the table below the `md` breakpoint with stacked cards (one idea per card: ref + status badge header, full summary, prompt chip, vote row, 3-dot menu). Desktop table unchanged. Keeps all filters/sort working against the same Alpine store — view-only change, no API work.

Acceptance: usable at 375px with no horizontal scroll; tap targets ≥ 44px.

### 8.7 Ideas 3-dot menu (admin)

Hamburger menu per idea gains, for admins: **Discard**, **Consider** (both = status PATCH + toast), **Refine**, **Competitors** (both = actions POST, existing flow). Items get icons + labels (no icon-only mystery meat); Discard asks for confirm since it hides the idea under the default filter. Non-admin menu unchanged.

Acceptance: each item works from the menu with no page reload; menu closes on selection/outside tap/Escape.

### 8.8 Suggestions (not requested, recommended)

1. **Merge the two PRDs.** DONE (Sept 2026) — `PRD_Brainstormer.md` was stale (Next.js references) and is removed; this file is the single source of truth.
2. **Wire `prompt_body` into generation.** `generate_idea` currently renders the canned initial template and ignores the prompt body admins write — the main input field is decorative. Fix before adding §8.5 knobs.
3. **API-side range validation for all numeric prompt fields**, including the existing `temperature` (HTML has min/max but the API accepts anything).
