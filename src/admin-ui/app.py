import os, requests
from flask import Flask, session, redirect, request, url_for, render_template
from jinja2 import ChoiceLoader, FileSystemLoader
from authlib.integrations.flask_client import OAuth

app = Flask(__name__,
    static_folder="/app/static",
    template_folder="/app/templates"
)

app.jinja_loader = ChoiceLoader([
    FileSystemLoader("/app/templates"),  # local index.html, user.html
    FileSystemLoader("/app/shared"),     # shared base.html
])

app.secret_key = "admin-secret"
app.config["SESSION_COOKIE_SIZE"] = 4096
app.permanent_session_lifetime = 3600

oauth = OAuth(app)
oauth.register(
    name="keycloak",
    client_id=os.environ["OIDC_CLIENT_ID"],
    client_secret=os.environ["OIDC_CLIENT_SECRET"],
    server_metadata_url=f"{os.environ['OIDC_SERVER']}/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

LICENSE_SERVICE = os.environ["LICENSE_SERVICE_URL"]

# Helper Functions
# ---------------------------

# -- Get Service Token --
def get_service_token():
    resp = requests.post(
        f"{os.environ['OIDC_SERVER']}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["OIDC_CLIENT_ID"],
            "client_secret": os.environ["OIDC_CLIENT_SECRET"],
        },
    )
    return resp.json()["access_token"]

# -- Get Keycloak Users -- 
def get_keycloak_users():
    token = get_service_token()
    resp = requests.get(
        f"{os.environ['KEYCLOAK_ADMIN_URL']}/admin/realms/license-demo/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()


# ---------------------------
@app.route("/")
def index():
    if "token" not in session:
        return redirect(url_for("login"))
    users = get_keycloak_users()
    return render_template("index.html", users=users)

@app.route("/user/<user_id>")
def user(user_id):
    if "token" not in session:
        return redirect(url_for("login"))

    all_resp = requests.get(
        f"{LICENSE_SERVICE}/admin/features",
        headers={"Authorization": f"Bearer {session['token']}"},
    )
    all_features = all_resp.json().get("features", [])

    assigned_resp = requests.get(
        f"{LICENSE_SERVICE}/admin/users/{user_id}/features",
        headers={"Authorization": f"Bearer {session['token']}"},
    )
    assigned_names = assigned_resp.json().get("features", [])

    unassigned = [f for f in all_features if f["name"] not in assigned_names]
    assigned = [f for f in all_features if f["name"] in assigned_names]

    return render_template("user.html",
        user_id=user_id,
        assigned=assigned,
        unassigned=unassigned,
    )

@app.route("/assign", methods=["POST"])
def assign():
    if "token" not in session:
        return redirect(url_for("login"))
    user_id = request.form["user_id"]
    requests.post(
        f"{LICENSE_SERVICE}/admin/assign",
        json={"user_id": user_id, "feature": request.form["feature"]},
        headers={"Authorization": f"Bearer {session['token']}"},
    )
    return redirect(f"/user/{user_id}")

@app.route("/revoke", methods=["POST"])
def revoke():
    if "token" not in session:
        return redirect(url_for("login"))
    user_id = request.form["user_id"]
    requests.post(
        f"{LICENSE_SERVICE}/admin/revoke",
        json={"user_id": user_id, "feature": request.form["feature"]},
        headers={"Authorization": f"Bearer {session['token']}"},
    )
    return redirect(f"/user/{user_id}")

@app.route("/login")
def login():
    return oauth.keycloak.authorize_redirect(redirect_uri=url_for("callback", _external=True))

@app.route("/callback")
def callback():
    token = oauth.keycloak.authorize_access_token()
    session.permanent = True
    session["token"] = token["access_token"]
    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        "http://localhost:8080/realms/license-demo/protocol/openid-connect/logout"
        f"?post_logout_redirect_uri=http://localhost:5001"
        f"&client_id={os.environ['OIDC_CLIENT_ID']}"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)