#! /usr/bin/python

import os
from flask import Flask, session, \
    redirect, url_for, escape, request, render_template
from werkzeug.contrib.fixers import ProxyFix
from flask_dance.contrib.github import make_github_blueprint, github

SECURITY_ENABLED = False
NON_SECURE_ENDPOINTS = ("github.login")

GITHUB_CLIENT_ID = ""
GITHUB_SECRET = ""

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
app.secret_key = os.urandom(12)
blueprint = make_github_blueprint(
    client_id=GITHUB_CLIENT_ID,
    client_secret=GITHUB_SECRET,
)
app.register_blueprint(blueprint, url_prefix="/login")


@app.before_request
def before_request():
    print("Request: %s" % request.endpoint)

    if not SECURITY_ENABLED or \
            request.endpoint in NON_SECURE_ENDPOINTS:
        return

    if not github.authorized:
        return redirect(url_for("github.login"))

    resp = github.get("/user")
    assert resp.ok
    print "You are @{login} on GitHub".format(login=resp.json()["login"])


@app.route('/tasks')
def tasks():
    return render_template("tasks.html")


@app.route('/tasks', methods=['POST'])
def submit_task():
    task = request.form("task")
    app.logger.debug("Submit task: %s", task)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port="5000")
