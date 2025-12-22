from flask import Blueprint
from flask import render_template
from flask import request
from flask import redirect
from flask import url_for
from flask import flash
from flask import current_app   # definisce il contesto del modulo

from flask_login import login_user  # https://flask-login.readthedocs.io/en/latest/#flask_login.login_user
from flask_login import logout_user
from flask_login import login_required
from flask_login import current_user

from models.model import *

app = Blueprint("auth", __name__)

@app.route("/")
def login():
    return render_template("auth/login.html")

@app.route('/login', methods=['POST'])
def login_post():
    # manages the login form post request
    email = request.form.get('email')
    password = request.form.get('password')
    remember = True if request.form.get('remember') else False

    stmt = db.select(User).filter_by(email=email)
    user = db.session.execute(stmt).scalar_one_or_none()

    # check if the user actually exists
    # take the user-supplied password, hash it, and compare it to the hashed password in the database
    if not user:
        flash('We couldn\'t find your account')
        return redirect(url_for('auth.login')) # if the user doesn't exist or password is wrong, reload the page
    if not user.check_password(password):
        flash('Wrong password')
        return redirect(url_for('auth.login'))
    # if the above check passes, then we know the user has the right credentials
    login_user(user, remember=remember)
    return render_template('auth/profile.html' , name=current_user.username)

@app.route('/logout')
@login_required
def logout():
    username = current_user.username
    logout_user()
    return redirect(url_for('default.home'))

@app.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html', name=current_user.username)

@app.route('/signup', methods=['GET'])
def signup():
    return render_template('auth/signup.html')

@app.route('/signup', methods=['POST'])
def signup_post():
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')

    user = User(username=username, email=email)
    user.set_password(password)  # Imposta la password criptata
    db.session.add(user)  # equivalente a INSERT
    db.session.commit()
    flash('User created, please login')
    return render_template('auth/login.html')

@login_required
@app.route('/admin')
def admin_page():
    if current_user.is_authenticated and not current_user.has_role('admin'):
        flash("Accesso non autorizzato!")
        return redirect(url_for('default.home'))
    users = db.session.execute(db.select(User)).scalars().all()
    return render_template('admin.html', users=users)
