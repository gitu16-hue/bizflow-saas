from datetime import datetime

def is_allowed_to_reply():
    hour = datetime.now().hour
    return 8 <= hour <= 23
