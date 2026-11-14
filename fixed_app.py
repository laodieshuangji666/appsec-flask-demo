import os
import sqlite3
from functools import wraps

from flask import (
    Flask,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config.update(
    
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-this-secret"),
    DATABASE=os.path.join(BASE_DIR, "users.db"),
)


def get_db():
   
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
        """
    )

    
    columns = {
        row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()
    }
    if "password" not in columns and "password_hash" in columns:
        db.execute("ALTER TABLE users RENAME COLUMN password_hash TO password")

    
    admin = db.execute("SELECT id FROM users WHERE id = 0").fetchone()
    if admin is None:
        db.execute(
            "INSERT INTO users (id, username, password) VALUES (?, ?, ?)",
            (0, "admin", "admin"),
        )
    else:
        db.execute(
            "UPDATE users SET password = ? WHERE id = 0",
            ("admin",),
        )

    db.commit()


def admin_required(view):
    

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("请先登录。", "error")
            return redirect(url_for("login"))
        if session["user_id"] != 0:
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("home"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not password:
            flash("用户名和密码都不能为空。", "error")
        elif len(username) > 20:
            flash("用户名不能超过 20 个字符。", "error")
        elif len(password) < 6:
            flash("密码至少需要 6 位。", "error")
        elif password != confirm_password:
            flash("两次输入的密码不一致。", "error")
        else:
            db = get_db()
            try:
                db.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (username, password),
                )
                db.commit()
            except sqlite3.IntegrityError:
                db.rollback()
                flash("这个用户名已经被注册了，请换一个。", "error")
            else:
                flash("注册成功，请登录。", "success")
                return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        sql = "SELECT id, username FROM users WHERE username = ? AND password = ?"
        user = get_db().execute(sql, (username, password)).fetchone()

       
        if user:
            session.clear()
            session["user_id"] = user["id"]
            if user["id"] == 0:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("profile", user_id=user["id"]))
        else:
            flash("用户名或密码不正确。", "error")

    return render_template("login.html")


@app.route("/profile/<int:user_id>")
def profile(user_id):
    
    if "user_id" not in session:
        flash("请先登录。", "error")
        return redirect(url_for("login"))

    
    if user_id == 0:
        if str(session["user_id"]) != "0":
            abort(403) 
        return redirect(url_for("admin_dashboard"))

    
    if str(user_id) != str(session["user_id"]):
        abort(403)  

    
    user = get_db().execute(
        "SELECT id, username FROM users WHERE id = ?", (user_id,)
    ).fetchone()

    if user is None:
        abort(404)

    return render_template("profile.html", username=user["username"])


@app.route("/home")
def home():
    if "user_id" not in session:
        flash("请先登录。", "error")
        return redirect(url_for("login"))

    user = get_db().execute(
        "SELECT id FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()

    if user is None:
        
        session.clear()
        return redirect(url_for("login"))

    if session["user_id"] == 0:
        return redirect(url_for("admin_dashboard"))

    return redirect(url_for("profile", user_id=session["user_id"]))


@app.route("/admin")
@admin_required
def admin_dashboard():
    users = get_db().execute(
        "SELECT id, username FROM users ORDER BY id"
    ).fetchall()
    user_count = sum(1 for user in users if user["id"] != 0)
    return render_template("admin.html", users=users, user_count=user_count)


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    if user_id == 0:
        flash("管理员账号不能删除。", "error")
        return redirect(url_for("admin_dashboard"))

    db = get_db()
    result = db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()

    if result.rowcount == 0:
        flash("用户不存在或已经被删除。", "error")
    else:
        flash("用户已删除。", "success")

    return redirect(url_for("admin_dashboard"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("你已退出登录。", "success")
    return redirect(url_for("login"))


# 启动时自动创建数据库和用户表。
with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True)
