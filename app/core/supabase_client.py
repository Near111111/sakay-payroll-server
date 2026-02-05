from supabase import create_client, Client
from app.core.config import settings  # Changed

supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_KEY
)


def get_supabase() -> Client:
    return supabase