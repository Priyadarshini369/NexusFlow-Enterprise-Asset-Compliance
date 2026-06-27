-- Day 2-3: Master Plan Relational Schema Execution

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Orders Table (Required for Business Return Workflow)
CREATE TABLE IF NOT EXISTS orders (
    order_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_orders
        FOREIGN KEY(user_id) 
        REFERENCES users(user_id) 
        ON DELETE CASCADE
);

-- 3. Chat Sessions Table (With JSON State Compression & Guardrails)
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id VARCHAR(255) PRIMARY KEY, -- Handled as string for UUID/Streamlit session compatibility
    user_id INT NOT NULL,
    session_title VARCHAR(150) DEFAULT 'New Chat Session',
    chat_state JSONB NOT NULL DEFAULT '{}'::jsonb, -- Day 4-5 Memory Compression
    agent_turn_count INT DEFAULT 0,                 -- Day 18 Counter Guardrail
    account_state VARCHAR(50) DEFAULT 'ACTIVE',    -- Day 19 Circuit Breaker State
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_sessions
        FOREIGN KEY(user_id) 
        REFERENCES users(user_id) 
        ON DELETE CASCADE
);

-- 4. Processed Transactions Table (Day 16 Idempotency Gatekeeper)
CREATE TABLE IF NOT EXISTS processed_transactions (
    idempotency_key VARCHAR(255) PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    response_payload JSONB,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_transaction_session
        FOREIGN KEY(session_id)
        REFERENCES chat_sessions(session_id)
        ON DELETE CASCADE
);