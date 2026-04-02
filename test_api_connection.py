
import os
import sys
from core.llm_client import create_planner_client, create_critic_client

def test_connectivity():
    print("=== Testing ForgeCore API Connectivity ===\n")
    
    # 1. Test Planner (OpenAI-compatible / Big Pickle)
    print("--- Testing Planner (Big Pickle) ---")
    try:
        planner = create_planner_client()
        print(f"Backend: {type(planner).__name__}")
        print(f"Model:   {getattr(planner, 'model', 'unknown')}")
        
        print("Sending 'ping'...")
        p_resp = planner.generate("ping")
        print(f"Response: {p_resp[:100]}...")
        print("[OK] Planner connected successfully!\n")
    except Exception as e:
        print(f"[ERROR] Planner test failed: {e}\n")

    # 2. Test Critic (Groq)
    print("--- Testing Critic (Groq) ---")
    try:
        critic = create_critic_client()
        print(f"Backend: {type(critic).__name__}")
        print(f"Model:   {getattr(critic, 'model', 'unknown')}")
        
        print("Sending 'ping'...")
        c_resp = critic.generate("ping")
        print(f"Response: {c_resp[:100]}...")
        print("[OK] Critic connected successfully!\n")
    except Exception as e:
        print(f"[ERROR] Critic test failed: {e}\n")

if __name__ == "__main__":
    test_connectivity()
