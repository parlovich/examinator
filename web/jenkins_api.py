#! /usr/bin/python

import argparse
import requests
import re
import time
import pprint
import json

JENKINS_URL = "http://52.90.189.123:8080"
JENKINS_USER = "admin"
JENKINS_TOKEN = "117654622048d9c2779c573b625c416ccc"  # Generate token via Jenkins UI


def trigger_job(job, params):
    response = requests.post(
        "{jenkins_url}/job/{job_name}/buildWithParameters".format(
            jenkins_url=JENKINS_URL,
            job_name=job),
        params=params,
        auth=(JENKINS_USER, JENKINS_TOKEN))
    if response.status_code != 201 or 'Location' not in response.headers:
        raise RuntimeError("Job can't be started")
    return _get_queue_id_from_location_url(response.headers['Location'])


def _get_queue_id_from_location_url(location_url):
    return int(filter(len, location_url.split("/"))[-1])


def wait_for_job_to_execute(job, queue_id, interval=2, max_retries=60):
    queue_item_url = '{jenkins_url}/queue/item/{queue_id}/api/json'.format(
        jenkins_url=JENKINS_URL,
        queue_id=queue_id
    )
    response = requests.get(queue_item_url, auth=(JENKINS_USER, JENKINS_TOKEN))
    retry = 1
    while True:
        if response.status_code == 404:
            return _get_job_id_by_queue_id(job, queue_id)

        queue_item = response.json()
        if "cancelled" in queue_item and queue_item["cancelled"]:
            raise RuntimeError("Error while executing '%s' build. Build was cancelled" % job)

        if 'executable' in queue_item:
            executable = queue_item["executable"]
            if executable and 'number' in executable:
                return executable["number"]

        retry += 1
        if retry > max_retries:
            raise RuntimeError("Waiting for build to start timeout")

        time.sleep(interval)
        response = requests.get(queue_item_url, auth=(JENKINS_USER, JENKINS_TOKEN))


def _get_job_id_by_queue_id(job, queue_id):
    response = requests.get(
        "{jenkins_url}/job/{job}/api/xml?tree=builds[id,number,queueId]&xpath=//build[queueId={queue_id}]".format(
            jenkins_url=JENKINS_URL,
            job=job,
            queue_id=queue_id),
        auth=(JENKINS_USER, JENKINS_TOKEN)
    )
    response.raise_for_status()
    #TODO parse xml
    number_search = re.search('<number>(.*)</number>', response.content, re.IGNORECASE)
    assert number_search
    job_id = int(number_search.group(1))
    return job_id


def wait_for_job_to_complete(job, job_id, interval=5, max_retries=120):
    job_url = '{jenkins_url}/job/{job}/{job_id}/api/json?tree=building'.format(
        jenkins_url=JENKINS_URL,
        job=job,
        job_id=job_id
    )
    response = get_resource(job_url)
    retry = 1
    while True:
        if not response["building"]:
            break

        retry += 1
        if retry > max_retries:
            raise RuntimeError("Waiting for build to start timeout")

        time.sleep(interval)
        response = get_resource(job_url)


def get_job(job, job_id):
    return get_resource(
        "{jenkins_url}/job/{job}/{job_id}/api/json".format(
            jenkins_url=JENKINS_URL,
            job=job,
            job_id=job_id)
    )


def get_resource(url):
    response = requests.get(url, auth=(JENKINS_USER, JENKINS_TOKEN))
    response.raise_for_status()
    return response.json()


def parse_args():
    parser = argparse.ArgumentParser(description="Run Jenkins job and wait till the execution is complete")
    parser.add_argument("--job", dest="job", required=True, type=str,
                        help="Name of the job to execute")
    parser.add_argument("--params", dest="params", required=True, type=str,
                        help="JSON representing job parameters, ex.: {\\\"REPO_URL\\\": \\\"https://github.com/user/repo\\\",..}")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    params = json.loads(args.params)
    print "Trigger Jenkins job '%s' with params: %s ..." % (args.job, str(params))

    queue_id = trigger_job(args.job, params)
    print "Job is added to queue. Queue id: %d" % queue_id

    print "Waiting for job to run..."
    job_id = wait_for_job_to_execute(args.job, queue_id)
    print "Job has been started. Job id: %d" % job_id

    print "Waiting for job to complete..."
    wait_for_job_to_complete(args.job, job_id)
    print "Job has been finished."
    pprint.pprint(get_job(args.job, job_id))
