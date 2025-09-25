import os   
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/mydatabase")
    USERS_COL = os.getenv("USERS_COL", "users")
    CATS_COL = os.getenv("CATS_COL", "categories")

"""
Create .env like:


SECRET_KEY=super-secret
MONGO_URI=mongodb://localhost:27017
MONGO_DB=admin_panel_db
USERS_COL=users
CATS_COL=agentcategories
"""