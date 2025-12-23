import os
from sqlite3 import OperationalError
from flask import Flask, render_template, redirect, url_for, request
from dotenv import load_dotenv
from flask_migrate import Migrate
from models.connection import db
from flask_login import LoginManager
from routes.default import app as bp_default
from routes.auth import app as bp_auth
from models.model import init_db
from models.model import User

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI',"sqlite:///labo1.db")
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY',"grandepanepanegrande1212121212121212")

app.register_blueprint(bp_default)
app.register_blueprint(bp_auth, url_prefix="/auth")
db.init_app(app)
with app.app_context():
     try:
        init_db()
     except OperationalError:
           print("DB non ancora inizializzato, skip init_db()")

migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    # since the user_id is just the primary key of our user table, use it in the query for the user
    stmt = db.select(User).filter_by(id=user_id)
    user = db.session.execute(stmt).scalar_one_or_none()
    # return User.query.get(int(user_id))   # legacy
    return user

if __name__ == "__main__":
    load_dotenv()
    app.run(debug=True)