#! /usr/bin/python

import os
from flask import Flask, session, \
    redirect, url_for, escape, request, render_template
from werkzeug.contrib.fixers import ProxyFix
from flask_dance.contrib.github import make_github_blueprint, github
from tasks import TASKS
import jenkins_api

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
    return render_template("tasks.html", tasks=TASKS)


@app.route('/task/check', methods=['GET'])
def verify_task():
    try:
        task = get_task_by_id(request.args.get("task"))
        job = task["jenkins_job"]
        repo = request.args.get("repo")
        queue_id = jenkins_api.trigger_job(job, {"REPO_URL": repo})
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


def get_task_by_id(task_id):
    task = [t for t in TASKS if t["id"] == task_id]
    if task:
        return task[0]
    raise RuntimeError("No task with name '%s' found" % task_id)


def create_execution_report(task, job_id):
    job = jenkins_api.get_job(task["jenkins_job"], job_id)
    duration = job["duration"] / 1000
    if "FAILURE" == job["result"]:
        return "Duration: %s sec.<br/>" \
               "Error occurred while running tests" % duration
    else:
        status = "All tests passed" if "SUCCESS" == job["result"] else "Not all tests passed"

        # TODO process test results for other type of projects
        total, failed, skipped = get_test_results_java(job)

        return "Duration: %s sec.<br/>" \
               "%s<br/>" \
               "----------------------<br/>" \
               "Total number of tests: %d<br/>" \
               "Failed tests: %d<br/>" \
               "Skipped tests: %d" % (duration, status, total, failed, skipped)


def get_test_results_java(job):
    surfire_report = [a for a in job["actions"]
                      if "_class" in a and a["_class"] == "hudson.maven.reporters.SurefireAggregatedReport"]
    if surfire_report:
        return (surfire_report[0]["totalCount"],
                surfire_report[0]["failCount"],
                surfire_report[0]["skipCount"])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port="80")
