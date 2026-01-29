from flask import render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required
from models import db
from models.user import User
from routes import auth_bp

@auth_bp.get("/login")
def login_get():
    return render_template("login.html")

@auth_bp.post("/login")
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    user = db.session.query(User).filter(User.email == email, User.is_active == True).first()
    if not user or not user.check_password(password):
        flash("Credenciales inválidas", "error")
        return redirect(url_for("auth.login_get"))

    login_user(user)

    # Limpiar contexto anterior
    session.pop("company_id", None)
    session.pop("branch_id", None)

    return redirect(url_for("context.select_context"))

@auth_bp.get("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login_get"))
