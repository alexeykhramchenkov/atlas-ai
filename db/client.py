import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY)

def get_or_create_user(tg_user_id: int, wb_api_key: str):
    result = supabase.table("users").select("*").eq("tg_user_id", tg_user_id).execute()
    if result.data:
        return result.data[0]
    new_user = supabase.table("users").insert({
        "tg_user_id": tg_user_id,
        "wb_api_key": wb_api_key
    }).execute()
    return new_user.data[0]

def log_sync(user_id, table_name, status, rows=0, error=None, date_from=None, date_to=None):
    supabase.table("sync_log").insert({
        "user_id": user_id,
        "table_name": table_name,
        "status": status,
        "rows_upserted": rows,
        "error_msg": error,
        "date_from": str(date_from) if date_from else None,
        "date_to": str(date_to) if date_to else None
    }).execute()
