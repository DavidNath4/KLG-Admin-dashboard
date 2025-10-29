# service/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash
from pathlib import Path
import json
from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint("auth", __name__, url_prefix="/admin-klg")

def verify_password(plain: str, stored: str) -> bool:
    """Verify password against stored hash with specific error handling"""
    if not stored:
        return False
    try:
        return check_password_hash(stored, plain)
    except (ValueError, TypeError) as e:
        current_app.logger.error(f"[Auth] Password verification error: {e}")
        return False
    except Exception as e:
        current_app.logger.error(f"[Auth] Unexpected password verification error: {e}")
        return False

def _load_creds(username: str):
    """Load credentials with comprehensive error handling"""
    try:
        try:
            project_root = Path(current_app.root_path)
        except RuntimeError:
            project_root = Path(__file__).resolve().parents[1]
        
        json_path = (project_root / "credentials.json").resolve()
        current_app.logger.info(f"[Auth] Loading credentials for user: {username}")
        
        if not json_path.exists():
            current_app.logger.error(f"[Auth] Credentials file not found: {json_path}")
            return None, None
            
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if not isinstance(data, list):
            current_app.logger.error("[Auth] Invalid credentials file format - expected list")
            return None, None
            
        for cred in data:
            if not isinstance(cred, dict):
                current_app.logger.warning("[Auth] Invalid credential entry - skipping")
                continue
            if username == cred.get("username"):
                return cred.get("username"), cred.get("password_hash")
                
        current_app.logger.warning(f"[Auth] User not found: {username}")
        return None, None
        
    except json.JSONDecodeError as e:
        current_app.logger.error(f"[Auth] JSON decode error in credentials file: {e}")
        return None, None
    except PermissionError as e:
        current_app.logger.error(f"[Auth] Permission denied reading credentials: {e}")
        return None, None
    except FileNotFoundError as e:
        current_app.logger.error(f"[Auth] Credentials file not found: {e}")
        return None, None
    except OSError as e:
        current_app.logger.error(f"[Auth] OS error reading credentials: {e}")
        return None, None
    except Exception as e:
        current_app.logger.error(f"[Auth] Unexpected error loading credentials: {e}")
        return None, None

@bp.route("/login", methods=["GET", "POST"])
def login():
    """Login route with comprehensive error handling"""
    try:
        if session.get("logged_in"):
            return redirect(url_for("users.admin_users"))
            
        if request.method == "POST":
            try:
                username = request.form.get("username", "").strip()
                password = request.form.get("password", "")
                
                if not username or not password:
                    flash("Username and password are required", "danger")
                    return redirect(url_for("auth.login", next=request.args.get("next")))
                
                cfg_user, cfg_pw_hash = _load_creds(username)
                
                if not cfg_user or not cfg_pw_hash:
                    flash("Invalid credentials configuration", "danger")
                    current_app.logger.warning(f"[Auth] Login attempt with invalid config: {username}")
                    return redirect(url_for("auth.login", next=request.args.get("next")))
                
                if username == cfg_user and verify_password(password, cfg_pw_hash):
                    session.permanent = True
                    session["logged_in"] = True
                    session["admin_username"] = username
                    flash("Login successful", "success")
                    current_app.logger.info(f"[Auth] Successful login: {username}")
                    
                    next_url = request.args.get("next") or url_for("users.admin_users")
                    return redirect(next_url)
                else:
                    flash("Invalid username or password", "danger")
                    current_app.logger.warning(f"[Auth] Failed login attempt: {username}")
                    return redirect(url_for("auth.login", next=request.args.get("next")))
                    
            except (ValueError, TypeError) as e:
                current_app.logger.error(f"[Auth] Login form validation error: {e}")
                flash("Invalid form data. Please try again.", "danger")
                return redirect(url_for("auth.login"))
            except RuntimeError as e:
                current_app.logger.error(f"[Auth] Login runtime error: {e}")
                flash("Login system error. Please try again.", "danger")
                return redirect(url_for("auth.login"))
            except Exception as e:
                current_app.logger.error(f"[Auth] Login processing error: {e}")
                flash("Login system error. Please try again.", "danger")
                return redirect(url_for("auth.login"))
                
        return render_template("login.html", hide_sidebar=True)
        
    except Exception as e:
        current_app.logger.error(f"[Auth] Login route error: {e}")
        flash("System error. Please contact administrator.", "danger")
        return render_template("login.html", hide_sidebar=True)

@bp.route("/logout", methods=["POST", "GET"])
def logout():
    """Logout route with error handling"""
    try:
        username = session.get("admin_username", "unknown")
        session.clear()
        flash("Logout successful", "info")
        current_app.logger.info(f"[Auth] User logged out: {username}")
        return redirect(url_for("auth.login"))
    except (KeyError, AttributeError) as e:
        current_app.logger.error(f"[Auth] Session error during logout: {e}")
        # Clear session anyway
        session.clear()
        return redirect(url_for("auth.login"))
    except Exception as e:
        current_app.logger.error(f"[Auth] Logout error: {e}")
        # Clear session anyway
        session.clear()
        return redirect(url_for("auth.login"))

@bp.route("/_dev/hash", methods=["GET"])
def dev_hash():
    """Development hash generator with error handling"""
    try:
        if not current_app.debug:
            current_app.logger.warning("[Auth] Dev hash endpoint accessed in production")
            return "Not available", 404
            
        pwd = request.args.get("p")
        if not pwd:
            return "Usage: ?p=password", 400
            
        hash_result = generate_password_hash(pwd)
        current_app.logger.info("[Auth] Password hash generated")
        return hash_result, 200, {"Content-Type": "text/plain; charset=utf-8"}
        
    except (ValueError, TypeError) as e:
        current_app.logger.error(f"[Auth] Hash generation validation error: {e}")
        return "Invalid password format", 400
    except RuntimeError as e:
        current_app.logger.error(f"[Auth] Hash generation runtime error: {e}")
        return "Hash generation failed", 500
    except Exception as e:
        current_app.logger.error(f"[Auth] Hash generation error: {e}")
        return "Hash generation failed", 500
