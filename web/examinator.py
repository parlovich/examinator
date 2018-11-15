#! /usr/bin/python

import os
from flask import Flask, session, \
    redirect, url_for, escape, request, render_template
from werkzeug.contrib.fixers import ProxyFix
from flask_dance.contrib.github import make_github_blueprint, github
from flask_dance.consumer import oauth_authorized
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

from tasks import TASKS
import jenkins_api

SECURITY_ENABLED = False

GITHUB_CLIENT_ID = ""
GITHUB_SECRET = ""

# TODO enable ssl
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
app.secret_key = os.urandom(12)

github_blueprint = make_github_blueprint(client_id=GITHUB_CLIENT_ID, client_secret=GITHUB_SECRET)
app.register_blueprint(github_blueprint, url_prefix="/login")

login_manager = LoginManager(app)
login_manager.login_view = "/"


class User(UserMixin):
    def __init__(self, id):
        self.id = id


@login_manager.user_loader
def load_user(id):
    return User(id)


@oauth_authorized.connect
def github_logged_in(blueprint, token):
    resp = blueprint.session.get("/user")
    assert resp.ok
    resp_json = resp.json()
    print "Login as @{login}".format(login=resp_json["login"])
    login_user(User(resp_json["login"]))


@app.route('/login')
def login():
    if not current_user.is_authenticated:
        if not github.authorized:
            return redirect(url_for("github.login"))

        resp = github.get("/user")
        assert resp.ok
        user = resp.json()["login"]
        print "Login as @{login}".format(login=user)

        login_user(User(user))

    return redirect(url_for(".tasks"))


@app.route('/logout')
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect("/")


@app.route('/')
def welcome():
    if current_user.is_authenticated:
        return redirect(url_for(".tasks"))
    return render_template("welcome.html")


@app.route('/tasks')
@login_required
def tasks():
    return render_template("tasks.html", tasks=TASKS)


@app.route('/task/check', methods=['GET'])
@login_required
def verify_task():
    try:
        task = get_task_by_id(request.args.get("task"))
        job = task["jenkins_job"]
        repo = request.args.get("repo")
        queue_id = jenkins_api.trigger_job(job, _get_job_params(task, repo))
        print "Job '%s' is added to queue. Queue id: %d" % (job, queue_id)

        print "Waiting for job '%s' to run..." % job
        job_id = jenkins_api.wait_for_job_to_execute(job, queue_id)
        print "Job '%s' has been started. Job id: %d" % (job, job_id)

        print "Waiting for job '%s' to complete..." % job
        jenkins_api.wait_for_job_to_complete(job, job_id)
        print "Job '%s' has been finished." % job

        return create_execution_report(task, job_id)
    except Exception as e:
        return "ERROR: %s" % e


def _get_job_params(task, repo):
    params = {
        "USER_ID": current_user.id,
        "TASK": task["id"],
        "REPO_URL": repo
    }
    if task["type"] in ("java", "js"):
        params["TEST_REPO_URL"] = task["test_repo"]
    return params


def get_task_by_id(task_id):
    task = [t for t in TASKS if t["id"] == task_id]
    if task:
        return task[0]
    raise RuntimeError("No task with name '%s' found" % task_id)


def create_execution_report(task, job_id):
    job = jenkins_api.get_job(task["jenkins_job"], job_id)

    if task["type"] in ("java", "net", "js"):
        return get_test_report_junit(job)
    return get_test_report_default(job)


def get_test_report_default(job):
    return "Duration: %s sec.<br/>" \
           "%s" % (job["duration"] / 1000, job["result"])


def get_test_report_junit(job):
    duration = job["duration"] / 1000
    test_report = [a for a in job["actions"]
                      if "_class" in a and a["_class"] in ("hudson.tasks.junit.TestResultAction", "hudson.maven.reporters.SurefireAggregatedReport")]
    if test_report:
        test_report = test_report[0]
    status = "<div style='color:green;'>OK</div>" if "SUCCESS" == job["result"] else \
        "<div style='color:red;'>FAILED</div>" if test_report else \
        "<div style='color:red;'>ERROR: can't run tests</div>"
    report = "%s\n"\
        "Duration: %s sec." % (status, duration)
    if test_report and "SUCCESS" != job["result"]:
        report = "%s\n<br/>\n%s" % (report, generate_junit_report(job, test_report))
    return report


def get_test_report_js(job):
    # TODO implement JS specific report
    return get_test_report_default()


def generate_junit_report(job, action):
    report = jenkins_api.get_resource(job["url"] + action["urlName"] + "/api/json")
    failed_tests = []
    if "suites" in report:
        for suite in report["suites"]:
            if "cases" in suite:
                for case in suite["cases"]:
                    if not case["skipped"] and case["status"] != "PASSED":
                        failed_tests.append((case["className"] + "." + case["name"], case["errorDetails"]))
    result = ""
    if failed_tests:
        result = "-----------------------------\n<br/>\n" \
                 "Test failed %d out of %d:\n<br/>\n" \
                 "%s" % (action["failCount"], action["totalCount"],
                         "<br/>".join(["%s: %s" % (name, error) for name, error in failed_tests]))
    return result


if __name__ == "__main__":
    app.run(host="0.0.0.0", port="8080")
