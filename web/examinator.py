#! /usr/bin/python

import os
from flask import Flask, session, \
    redirect, url_for, escape, request, render_template
from werkzeug.contrib.fixers import ProxyFix
from flask_dance.contrib.github import make_github_blueprint, github
from tasks import TASKS
import jenkins_api

SECURITY_ENABLED = False
GITHUB_CLIENT_ID = "d560b12f5bc9453309ae"
GITHUB_SECRET = "71fd5f824fcac8cf4d5fe0af34a16e820dd8cb9a"

# TODO enable ssl
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

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
    if not SECURITY_ENABLED:
        return

    if request.endpoint and request.endpoint == "tasks":
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

    if task["type"] in ("java", "net"):
        return get_test_report_junit(job)
    elif task["type"] == "js":
        return get_test_report_js(job)
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
