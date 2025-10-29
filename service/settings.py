from flask import Blueprint, render_template, request, flash, current_app, redirect, url_for
from time import perf_counter
from config.mongo import init_mongo, reload_mongo
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, PyMongoError
import json
import os

CONFIG_FILE = os.path.join("config", "db_config.json")

def db_exists(uri, dbname):
    """Check if database exists with specific error handling"""
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        dblist = client.list_database_names()
        return dbname in dblist
    except ServerSelectionTimeoutError as e:
        current_app.logger.error(f"[Settings] Connection timeout checking database: {e}")
        return False
    except PyMongoError as e:
        current_app.logger.error(f"[Settings] MongoDB error checking database: {e}")
        return False
    except Exception as e:
        current_app.logger.error(f"[Settings] Unexpected error checking database existence: {e}")
        return False

def load_db_config():
    """Load database configuration with error handling"""
    try:
        if not os.path.exists(CONFIG_FILE):
            current_app.logger.info(f"[Settings] Config file not found, using defaults: {CONFIG_FILE}")
            return {"MONGO_URI": "mongodb://localhost:27017/", "MONGO_DB": "LibreChat"}
            
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        # Validate config structure
        if not isinstance(config, dict):
            current_app.logger.error("[Settings] Invalid config format - not a dictionary")
            return {"MONGO_URI": "mongodb://localhost:27017/", "MONGO_DB": "LibreChat"}
            
        # Ensure required keys exist
        config.setdefault("MONGO_URI", "mongodb://localhost:27017/")
        config.setdefault("MONGO_DB", "LibreChat")
        
        return config
        
    except json.JSONDecodeError as e:
        current_app.logger.error(f"[Settings] JSON decode error in config file: {e}")
        return {"MONGO_URI": "mongodb://localhost:27017/", "MONGO_DB": "LibreChat"}
    except PermissionError as e:
        current_app.logger.error(f"[Settings] Permission denied reading config: {e}")
        return {"MONGO_URI": "mongodb://localhost:27017/", "MONGO_DB": "LibreChat"}
    except Exception as e:
        current_app.logger.error(f"[Settings] Unexpected error loading config: {e}")
        return {"MONGO_URI": "mongodb://localhost:27017/", "MONGO_DB": "LibreChat"}

def save_db_config(uri: str, dbname: str):
    """Save database configuration with error handling"""
    try:
        # Validate inputs
        if not uri or not dbname:
            raise ValueError("URI and database name cannot be empty")
            
        # Create config directory if it doesn't exist
        config_dir = os.path.dirname(CONFIG_FILE)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
            
        cfg = {"MONGO_URI": uri.strip(), "MONGO_DB": dbname.strip()}
        
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            
        current_app.logger.info(f"[Settings] Configuration saved: {dbname}")
        
    except PermissionError as e:
        current_app.logger.error(f"[Settings] Permission denied saving config: {e}")
        raise Exception("Permission denied. Cannot save configuration.")
    except OSError as e:
        current_app.logger.error(f"[Settings] OS error saving config: {e}")
        raise Exception("File system error. Cannot save configuration.")
    except Exception as e:
        current_app.logger.error(f"[Settings] Unexpected error saving config: {e}")
        raise

bp = Blueprint("settings", __name__, url_prefix="/admin-klg/admin")

@bp.route("/settings", methods=["GET", "POST"])
def db_settings():
    """Database settings with comprehensive error handling"""
    try:
        # Load default configuration
        cfg = load_db_config()
        uri = request.form.get("MONGO_URI", cfg["MONGO_URI"]).strip()
        dbname = request.form.get("MONGO_DB", cfg["MONGO_DB"]).strip()
        action = request.form.get("action", "").strip()
        test_result = None

        if request.method == "POST":
            try:
                # Validate inputs
                if not uri or not dbname:
                    flash("MongoDB URI and database name are required", "danger")
                    return redirect(url_for("settings.db_settings"))
                
                # Validate URI format (basic check)
                if not uri.startswith(("mongodb://", "mongodb+srv://")):
                    flash("Invalid MongoDB URI format", "danger")
                    return redirect(url_for("settings.db_settings"))
                
                if action == "test":
                    try:
                        current_app.logger.info(f"[Settings] Testing connection to {uri}/{dbname}")
                        t0 = perf_counter()
                        
                        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
                        client.admin.command("ping")

                        if not db_exists(uri, dbname):
                            test_result = {
                                "ok": False, 
                                "message": f"⚠️ Database '{dbname}' does not exist on server"
                            }
                        else:
                            # Test collection listing
                            collections = list(client[dbname].list_collections())
                            dt = (perf_counter() - t0) * 1000
                            test_result = {
                                "ok": True, 
                                "message": f"✅ Connection successful to {dbname} ({dt:.0f}ms, {len(collections)} collections)"
                            }
                            
                    except ServerSelectionTimeoutError as e:
                        current_app.logger.error(f"[Settings] Connection timeout: {e}")
                        test_result = {"ok": False, "message": "❌ Connection timeout - server unreachable"}
                    except PyMongoError as e:
                        current_app.logger.error(f"[Settings] MongoDB error: {e}")
                        test_result = {"ok": False, "message": f"❌ MongoDB error: {str(e)[:100]}"}
                    except Exception as e:
                        current_app.logger.error(f"[Settings] Connection test error: {e}")
                        test_result = {"ok": False, "message": f"❌ Connection failed: {str(e)[:100]}"}

                elif action == "save":
                    try:
                        save_db_config(uri, dbname)
                        flash("Configuration saved successfully", "success")
                        current_app.logger.info(f"[Settings] Config saved: {dbname}")
                    except Exception as e:
                        flash(f"Failed to save configuration: {str(e)}", "danger")
                    return redirect(url_for("settings.db_settings"))

                elif action == "apply":
                    try:
                        save_db_config(uri, dbname)
                        reload_mongo(current_app, uri, dbname)
                        flash("MongoDB connection applied successfully", "success")
                        current_app.logger.info(f"[Settings] Connection applied: {dbname}")
                    except (ValueError, TypeError) as e:
                        current_app.logger.error(f"[Settings] Configuration validation error: {e}")
                        flash("Invalid configuration format", "danger")
                    except Exception as e:
                        current_app.logger.error(f"[Settings] Unexpected error in POST processing: {e}")
                        flash("Error processing request. Please try again.", "danger")

            except (ValueError, TypeError) as e:
                current_app.logger.error(f"[Settings] Form validation error: {e}")
                flash("Invalid form data. Please check your input.", "danger")
            except Exception as e:
                current_app.logger.error(f"[Settings] POST processing error: {e}")
                flash("Error processing request. Please try again.", "danger")

        return render_template(
            "settings.html",
            title="Database Settings",
            active="settings",
            MONGO_URI=uri,
            MONGO_DB=dbname,
            test_result=test_result,
        )
        
    except Exception as e:
        current_app.logger.error(f"[Settings] Route error: {e}")
        flash("System error. Please contact administrator.", "danger")
        
        # Return safe defaults
        return render_template(
            "settings.html",
            title="Database Settings",
            active="settings",
            MONGO_URI="mongodb://localhost:27017/",
            MONGO_DB="LibreChat",
            test_result={"ok": False, "message": "System error occurred"},
        )
