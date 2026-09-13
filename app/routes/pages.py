from flask import Blueprint, render_template, redirect, url_for

bp = Blueprint("pages", __name__)

@bp.route("/", methods=["GET"])
def index():
    return redirect(url_for("pages.login"))

@bp.route("/dashboard", methods=["GET"])
def dashboard():
    # Single ideas list lives at /ideas (PRD §8.2); keep the old URL working.
    return redirect(url_for("pages.ideas"))

@bp.route("/ideas", methods=["GET"])
def ideas():
    return render_template("ideas/dashboard.html")

@bp.route("/prompts", methods=["GET"])
def prompts():
    return render_template("prompts/list.html")

@bp.route("/prompts/create", methods=["GET"])
def create_prompt():
    return render_template("prompts/create.html")

@bp.route("/login", methods=["GET"])
def login():
    return render_template("auth/login.html")

@bp.route("/register", methods=["GET"])
def register():
    return render_template("auth/register.html")
