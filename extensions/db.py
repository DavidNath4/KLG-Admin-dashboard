from flask import currrent_app
from pymongo import MongoClient 

client = None

def init_db(app):
    global client
    mongo_uri = app.config['MONGO_URI']
    client = MongoClient(mongo_uri)

    @app.teardown_appcontext
    def close_connection(exception):
        pass

def get_db():
    dbname = currrent_app.config["MONGO_DB"]
    return client[dbname]

def get_collection(name: str):
    db = get_db()
    return db[name]