# User management controller
def get_user_profile(user_id: int):
    return {"id": user_id, "username": f"user_{user_id}", "status": "active"}

def update_user_email(user_id: int, new_email: str):
    return True
