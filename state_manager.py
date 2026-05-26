import time

user_states = {}
CONVERSATION_TIMEOUT = 30 * 60  # 30 minutes in seconds

def set_user_state(user_id: str, state: str, **data):
    user_states[user_id] = {
        "state": state,
        **data,
        "timestamp": time.time()
    }

def get_user_state(user_id: str) -> dict:
    state = user_states.get(user_id)
    if not state:
        return None
    
    if time.time() - state["timestamp"] > CONVERSATION_TIMEOUT:
        if user_id in user_states:
            del user_states[user_id]
        return None
        
    return state

def clear_user_state(user_id: str):
    if user_id in user_states:
        del user_states[user_id]
