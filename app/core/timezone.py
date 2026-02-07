import pytz
from datetime import datetime

# Philippine timezone
PHILIPPINE_TZ = pytz.timezone('Asia/Manila')


def get_philippine_time():
    """Get current Philippine time"""
    return datetime.now(PHILIPPINE_TZ)


def to_philippine_time(utc_time_str):
    """Convert UTC timestamp string to Philippine time"""
    # Parse the UTC timestamp
    utc_time = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
    
    # Convert to Philippine timezone
    return utc_time.astimezone(PHILIPPINE_TZ)


def format_philippine_time(dt):
    """Format datetime to ISO string with Philippine timezone"""
    return dt.isoformat()