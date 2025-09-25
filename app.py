from flask import flask
from config import config
from extensions.db import init_db
from bluprints.admin_bp import admin_bp
from bluprints.category_bp import category_bp

def create_app():
    app = flask(__name__)
    app.config.from_object(Config)

    # init mongo client
    init_db(app)

    Register bluprints
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(category_bp, url_prefix='/admin')

    app.get("/")
    def index():
        from flask import refirect, url_for
        return redirect(url_for('admin.users'))
    return app 

if __name__ == "__main__":
    app=create_app()
    app.run(debug=True)