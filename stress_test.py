import threading
import time
import uuid
from agent_brain import run_contextual_agent_turn

def execute_agent_thread(thread_name: str, user_id: str, session_id: str, message: str, tx_id: str):
    print(f"🚀 [{thread_name}] Launching thread payload into engine...")
    start_time = time.time()
    
    # Execute the live turn
    response = run_contextual_agent_turn(
        user_id=user_id,
        session_id=session_id,
        user_message=message,
        transaction_id=tx_id
    )
    
    duration = time.time() - start_time
    print(f"⏱️ [{thread_name}] Completed in {duration:.2f}s.")
    print(f"📥 [{thread_name}] System Output Snippet: {response[:80]}...\n")

if __name__ == "__main__":
    print("🔥 ======================================================= 🔥")
    print("   NEXUSFLOW ENTERPRISE ENGINE: DAY 21 LIVE STRESS TEST     ")
    print("   Simulating high-velocity multi-threaded race conditions... ")
    print("🔥 ======================================================= 🔥\n")

    shared_user = "user_priya_88"
    shared_session = "session_stress_zone_999"
    shared_message = "Verify data integrity rules for multi-tenant asset schemas."
    
    # 💥 CRITICAL: We pass the EXACT same transaction ID across threads 
    # to force the Idempotency Shield and Row locks into a direct collision.
    collision_tx_id = f"tx_stress_race_{int(time.time())}"

    # Define our parallel racing workers
    thread_1 = threading.Thread(
        target=execute_agent_thread, 
        args=("Thread-1 (Alpha)", shared_user, shared_session, shared_message, collision_tx_id)
    )
    thread_2 = threading.Thread(
        target=execute_agent_thread, 
        args=("Thread-2 (Beta)", shared_user, shared_session, shared_message, collision_tx_id)
    )
    thread_3 = threading.Thread(
        target=execute_agent_thread, 
        args=("Thread-3 (Gamma)", shared_user, shared_session, shared_message, collision_tx_id)
    )

    # Launch them simultaneously to invoke a true thread race condition
    print("⚡ Triggering concurrent thread ignition sequence...")
    thread_1.start()
    thread_2.start()
    thread_3.start()

    # Wait for all workers to conclude before exiting the process
    thread_1.join()
    thread_2.join()
    thread_3.join()

    print("🏁 Stress test sequence concluded. Analyze logs above for structural isolation leaks!")