import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_connection():
    """
    Establishes an ironclad connection by testing explicit container service names,
    internal bridge aliases, and standard localhost loopbacks.
    """
    possible_hosts = ["postgres", "nexusflow-db", "db", "127.0.0.1", "localhost"]
    
    env_host = os.environ.get("DB_HOST")
    if env_host:
        possible_hosts.insert(0, env_host)
        
    last_error = None
    for host in possible_hosts:
        try:
            return psycopg2.connect(
                host=host,
                database=os.environ.get("DB_NAME", "postgres"),
                user=os.environ.get("DB_USER", "postgres"),
                password=os.environ.get("DB_PASSWORD", "postgres"),
                port=os.environ.get("DB_PORT", "5432"),
                connect_timeout=2
            )
        except Exception as e:
            last_error = e
            continue
            
    print(f"\n⚠️ [Network Mesh Link Failure]: Your app container cannot reach any database hosts.")
    print(f"💡 Attempted host list: {possible_hosts}")
    print(f"💡 Diagnostic Detail: {str(last_error)}\n")
    raise last_error

def check_existing_transaction(transaction_id: str):
    """
    🛡️ Day 16 State-Locking Gatekeeper & Day 20 Schema Architecture:
    Queries the transaction log. Returns a tuple of (status, audit_report).
    If no transaction exists, returns (None, None).
    """
    if not transaction_id:
        return None, None

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 📊 Day 20 Self-healing DDL — includes confidence_score column
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS compliance_logs (
                id SERIAL PRIMARY KEY,
                transaction_id VARCHAR(100) UNIQUE,
                user_id VARCHAR(100),
                session_id VARCHAR(100),
                status VARCHAR(20) DEFAULT 'PROCESSING',
                audit_report TEXT,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                confidence_score FLOAT DEFAULT 0.0,
                policy_matched BOOLEAN DEFAULT FALSE,
                vision_succeeded BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        
        cursor.execute(
            "SELECT status, audit_report FROM compliance_logs WHERE transaction_id = %s;", 
            (transaction_id,)
        )
        row = cursor.fetchone()
        cursor.close()
        
        if row:
            return row[0], row[1]  # (status, audit_report)
            
    except Exception as e:
        print(f"⚠️ [Idempotency Gate Error]: Verification scan failed: {e}")
    finally:
        if conn:
            conn.close()
    return None, None

def get_or_create_session_state(user_id: str, session_id: str, lock_row: bool = False):
    """
    🛡️ Day 17 Upgrade: Retrieves or creates a session.
    If lock_row=True, applies a strict SELECT ... FOR UPDATE database lock.
    """
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return None
            
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id VARCHAR(100) PRIMARY KEY,
                user_id VARCHAR(100),
                chat_state TEXT,
                agent_turn_count INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        
        # Apply Day 17 Row-Level Isolation Lock if explicitly requested
        if lock_row:
            print(f"🔒 [Row-Level Lock] Requesting exclusive row lock on session: {session_id}")
            cursor.execute("SELECT * FROM chat_sessions WHERE session_id = %s FOR UPDATE;", (session_id,))
        else:
            cursor.execute("SELECT * FROM chat_sessions WHERE session_id = %s;", (session_id,))
            
        session = cursor.fetchone()
        
        if not session:
            default_state = {"user_id": user_id, "agent_turn_count": 0, "status": "ACTIVE", "chat_history": []}
            print(f"📝 [Session Provisioning] Creating fresh session record for {session_id}")
            
            try:
                cursor.execute(
                    "INSERT INTO chat_sessions (session_id, user_id, chat_state, agent_turn_count) VALUES (%s, %s, %s, %s) RETURNING *;",
                    (session_id, str(user_id), json.dumps(default_state), 0)
                )
                session = cursor.fetchone()
                conn.commit()
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                if lock_row:
                    cursor.execute("SELECT * FROM chat_sessions WHERE session_id = %s FOR UPDATE;", (session_id,))
                else:
                    cursor.execute("SELECT * FROM chat_sessions WHERE session_id = %s;", (session_id,))
                session = cursor.fetchone()
        
        cursor.close()
        
        if session and 'chat_state' in session and isinstance(session['chat_state'], str):
            try:
                session['chat_state'] = json.loads(session['chat_state'])
            except:
                pass
                
        # Keep connection open if row lock is active so the lock isn't dropped prematurely
        if lock_row:
            session['_db_connection'] = conn
            return session
            
        conn.close()
        return session
    except Exception as e:
        if conn: 
            conn.rollback()
            conn.close()
        print(f"❌ Database error in get_or_create_session_state: {e}")
        return None

def persist_session_state(session_id: str, chat_history_list: list, turn_count: int = 0, open_conn = None):
    """Saves serialized conversational state arrays cleanly back to the database."""
    conn = open_conn if open_conn else None
    try:
        if not conn:
            conn = get_db_connection()
            
        if not conn:
            return False
            
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE chat_sessions SET chat_state = %s, agent_turn_count = %s, updated_at = CURRENT_TIMESTAMP WHERE session_id = %s;",
            (json.dumps(chat_history_list), turn_count, session_id)
        )
        
        # Only commit here if we opened this connection locally. 
        # If open_conn was passed, let the parent pipeline handle the final commit/close tracking.
        if not open_conn:
            conn.commit()
            
        cursor.close()
        return True
    except Exception as e:
        if conn: 
            conn.rollback()
        print(f"❌ Database error in persist_session_state: {e}")
        return False
    finally:
        if not open_conn and conn: 
            conn.close()


def get_last_two_run_states(user_id: str, session_id: str) -> list:
    """
    Retrieves the last two completed runs for a session, returning their
    extracted asset compliance status for memory conflict detection.
    Returns a list of dicts: [{"tx_id", "prompt", "status", "track", "created_at"}, ...]
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT transaction_id, user_prompt, target_track, created_at
            FROM compliance_logs
            WHERE user_id = %s AND session_id = %s AND status = 'COMPLETED'
            ORDER BY id DESC
            LIMIT 2;
        """, (user_id, session_id))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        result = []
        for row in rows:
            result.append({
                "tx_id": row[0],
                "prompt": row[1] or "",
                "track": row[2] or "",
                "created_at": str(row[3]) if row[3] else "",
            })
        return result
    except Exception as e:
        print(f"⚠️ [Conflict Detector] Failed to fetch run states: {e}")
        if conn:
            conn.close()
        return []


def log_appraisal_request(transaction_id: str, user_id: str, session_id: str, estimated_range: str) -> bool:
    """
    Logs an appraisal request to the database — proves the agent can
    initiate real business workflows. Creates the table if it doesn't exist.
    Returns True on success.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appraisal_requests (
                id SERIAL PRIMARY KEY,
                transaction_id VARCHAR(100),
                user_id VARCHAR(100),
                session_id VARCHAR(100),
                estimated_range VARCHAR(200),
                status VARCHAR(50) DEFAULT 'PENDING',
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            INSERT INTO appraisal_requests
                (transaction_id, user_id, session_id, estimated_range, status)
            VALUES (%s, %s, %s, %s, 'SENT')
            ON CONFLICT DO NOTHING;
        """, (transaction_id, user_id, session_id, estimated_range))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"📨 [Appraisal] Request logged for tx={transaction_id}, range={estimated_range}")
        return True
    except Exception as e:
        print(f"❌ [Appraisal] Failed to log request: {e}")
        if conn:
            conn.close()
        return False


def get_appraisal_status(transaction_id: str) -> str | None:
    """Returns the appraisal status for a transaction, or None if not requested."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status, estimated_range, requested_at FROM appraisal_requests WHERE transaction_id=%s ORDER BY id DESC LIMIT 1;",
            (transaction_id,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            return {"status": row[0], "range": row[1], "requested_at": str(row[2])}
    except Exception:
        if conn:
            conn.close()
    return None