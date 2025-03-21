import google.cloud.logging
import sys
import os
import logging
from googleapiclient import discovery
from google.cloud.resourcemanager_v3 import ProjectsClient
import google.auth
from googleapiclient.errors import HttpError
import base64
from google.cloud import pubsub_v1
import json
import urllib.request

if os.environ.get("ENV", "N/A") == "LOCAL":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
else:
    gcloud_logging_client = google.cloud.logging.Client()
    gcloud_logging_client.setup_logging()

PARENT = ""
TOPIC_NAME = os.environ.get("TOPIC_NAME")
PROJECT_ID = os.environ.get("PROJECT_ID")


def main(request):
    logging.debug(f"Request received: {request}")
    logging.info("Discovering existing clusters")
    projects = list_all_projects(PARENT)
    discovered_clusters = discover_existing_clusters(projects)
    for cluster in discovered_clusters:
        ...
        # send_to_pubsub(cluster)
    return f"{len(discovered_clusters)} existing GKE clusters discovered and to be protected."


def list_all_projects(parent):
    """List all projects in the organization."""

    return ProjectsClient().search_projects()


def discover_existing_clusters(projects):
    clusters = []
    for project in projects:
        try:
            print(f"Discovering existing clusters for project: {project.name}")
            service = discovery.build("container", "v1")
            endpoint = service.projects().zones().clusters()
            request = endpoint.list(projectId=project.project_id, zone="-")
            response = request.execute()
            if "clusters" in response:
                logging.info(f"{len(response['clusters'])} cluster discovered in project: {project.name}")
                clusters.extend([x["selfLink"] for x in response["clusters"]])

        except HttpError as exc:
            if exc.status_code == 403:
                for detail in exc.error_details:
                    if "reason" in detail:
                        reason = detail.get("reason", "")
                    if "message" in detail:
                        message = detail.get("message", "")
                logging.warning(
                    f"Unable to discover clusters in {project.display_name}. Reason: {reason}. Message: {message}"
                )
    return clusters


def send_to_pubsub(cluster):

    logging.info(f"Sending cluster: {cluster} to pub/sub topic: {TOPIC_NAME} in {PROJECT_ID}")

    # Define and encode payload
    payload = {"asset": {"name": cluster.replace("https:", "").replace("/v1", "")}}
    payload_string = json.dumps(payload)
    string_bytes = payload_string.encode("utf-8")
    # encoded_bytes = base64.b64encode(string_bytes)
    # encoded_string = encoded_bytes.decode("utf-8")

    # publish to pbsub topic
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_NAME)

    future = publisher.publish(topic_path, data=string_bytes)
    print(future.result())

    print(f"Published message to {topic_path}.")
