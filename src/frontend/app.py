import os, requests, json, base64
from flask import Flask, session, redirect, url_for, render_template
from authlib.integrations.flask_client import OAuth
from jinja2 import ChoiceLoader, FileSystemLoader

app = Flask(__name__,
    static_folder="/app/static",
    template_folder="/app/templates"
)

app.jinja_loader = ChoiceLoader([
    FileSystemLoader("/app/templates"),
    FileSystemLoader("/app/shared"),
])

app.logger.setLevel("INFO")
app.secret_key = "dev-secret"

oauth = OAuth(app)
oauth.register(
    name="keycloak",
    client_id=os.environ["OIDC_CLIENT_ID"],
    client_secret=os.environ["OIDC_CLIENT_SECRET"],
    server_metadata_url=f"{os.environ['OIDC_SERVER']}/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

def get_token_claims(token):
    # JWT is three base64-encoded parts separated by dots
    # The middle part (index 1) is the claims payload
    payload = token.split(".")[1]
    # Add padding if needed — base64 requires length to be multiple of 4
    payload += "=" * (4 - len(payload) % 4)
    return json.loads(base64.b64decode(payload))


@app.route("/")
def index():
    if "token" not in session:
        return redirect(url_for("login"))

    claims = get_token_claims(session["token"])
    username = claims.get("preferred_username", "Unknown")

    resp = requests.get(
        f"{os.environ['LICENSE_SERVICE_URL']}/features",
        headers={"Authorization": f"Bearer {session['token']}"},
    )
    features = resp.json().get("features", [])
    return render_template("index.html", features=features, username=username)

@app.route("/login")
def login():
    # Step 1: redirect the browser to Keycloak's authorization endpoint
    return oauth.keycloak.authorize_redirect(redirect_uri=url_for("callback", _external=True))

@app.route("/callback")
def callback():
    # Step 2: Keycloak redirects back here with an authorization code.
    # Authlib exchanges that code for tokens behind the scenes.
    token = oauth.keycloak.authorize_access_token()
    session["token"] = token["access_token"]
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        "http://localhost:8080/realms/license-demo/protocol/openid-connect/logout"
        f"?post_logout_redirect_uri=http://localhost:5010"
        f"&client_id={os.environ['OIDC_CLIENT_ID']}"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)