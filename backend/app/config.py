import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL         = os.environ["DATABASE_URL"]
SUPABASE_URL         = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY    = os.environ["SUPABASE_ANON_KEY"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_JWT_SECRET  = os.environ["SUPABASE_JWT_SECRET"]