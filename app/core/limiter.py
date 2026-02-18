from slowapi import Limiter
from slowapi.util import get_remote_address

# Uses the client's IP address as the rate limit key
limiter = Limiter(key_func=get_remote_address)
