import subprocess
import base64
import json
import google.cloud.logging
import time
import logging
import urllib.request
import yaml
import os
from utils import get_cluster, get_kube_clients
from kubernetes import utils, client, dynamic
import sys
from datetime import datetime


if os.environ.get("ENV", "N/A") == "LOCAL":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
else:
    gcloud_logging_client = google.cloud.logging.Client()
    gcloud_logging_client.setup_logging()

# define global variables
MAX_CLUSTER_STATUS_CHECK_COUNT = 20
POD_READY_STATE_SECONDS_TO_SLEEP = 10
NODE_SENSOR_URL = "https://raw.githubusercontent.com/crowdstrike/falcon-operator/main/config/samples/falcon_v1alpha1_falconnodesensor.yaml"
FALCON_ADMISSION_CONTROLLER_URL = (
    "https://raw.githubusercontent.com/crowdstrike/falcon-operator/main/docs/deployment/gke/falconadmission.yaml"
)
FALCON_OPERATOR_URL = "https://github.com/crowdstrike/falcon-operator/releases/latest/download/falcon-operator.yaml"
FALCON_CLIENT_ID = os.environ["FALCON_CLIENT_ID"]
FALCON_CLIENT_SECRET = os.environ["FALCON_CLIENT_SECRET"]


def main(data, context):

    try:
        # decode payload
        payload = json.loads(base64.b64decode(data["data"]).decode("utf-8"))
        # parse fields
        asset_name = payload["asset"]["name"]
        cluster_name = asset_name.split("/")[8]
        project_id = asset_name.split("/")[4]
        zone = asset_name.split("/")[6]
        is_autopilot = True

        logging.info(f"asset name: {asset_name}")
        logging.info(f"cluster_name: {cluster_name}")
        logging.info(f"project_id: {project_id}")
        logging.info(f"zone: {zone}")

        # check if cluster is ready
        cluster_status_check_counter = 0
        cluster_status = ""
        while cluster_status != "RUNNING" and cluster_status_check_counter <= MAX_CLUSTER_STATUS_CHECK_COUNT:
            cluster = get_cluster(cluster_name=cluster_name, zone=zone, project_id=project_id)
            cluster_status = cluster.status.name
            logging.debug(f"Cluster status: {cluster_status} ")

            if cluster_status in ["STOPPING", "ERROR", "DEGRADED", "STATUS_UNSPECIFIED"]:
                logging.warning(f"Cluster in unmanageable state: {cluster_status}... Exiting")
                return
            elif cluster_status in ["PROVISIONING"]:
                logging.info("Cluster in provisioning state... Sleeping.")
                time.sleep(60)
            elif cluster_status in ["RUNNING"]:
                logging.info("Deploying operator on cluster")
            cluster_status_check_counter += 1

        # retrieve manifests
        node_sensor_manifest = download_and_config_node_sensor_manifest(is_autopilot=is_autopilot)
        admissions_controller_manifest = download_and_config_admissions_controller_manifest()
        operator_manifest = download_operator_manifest()

        # get kubernetes clients
        api_client = get_kube_clients(cluster)

        # protect cluster
        deploy_operator(api_client)
        deploy_node_sensor(api_client, node_sensor_manifest)
        deploy_falcon_admissions_controller(api_client, admissions_controller_manifest)
        logging.info(f"Cluster {cluster_name} protected.")
        return

    except Exception as e:
        logging.error(f"Unexpected error in main function: {str(e)}")
        raise


def download_and_config_node_sensor_manifest(is_autopilot):
    autopilot_config = {
        "backend": "bpf",
        "gke": {"autopilot": True},
        "resources": {"requests": {"cpu": "750m", "memory": "1.5Gi"}},
        "tolerations": [{"effect": "NoSchedule", "operator": "Equal", "key": "kubernetes.io/arch", "value": "amd64"}],
    }

    # download node sensor manifest
    urllib.request.urlretrieve(NODE_SENSOR_URL, "node_sensor_manifest.yaml")

    # convert to json
    with open("node_sensor_manifest.yaml", "r") as yaml_file:
        manifest = yaml.safe_load(yaml_file)

    # replace username and password
    manifest["spec"]["falcon_api"]["client_id"] = FALCON_CLIENT_ID
    manifest["spec"]["falcon_api"]["client_secret"] = FALCON_CLIENT_SECRET

    # if autopilot cluster add required config
    if is_autopilot:
        manifest["spec"]["node"] = autopilot_config

    # convert back to yaml and write file
    manifest_yaml = yaml.dump(manifest)
    with open("node_sensor_manifest.yaml", "w") as yaml_file:
        yaml_file.write(manifest_yaml)
    return manifest


def check_namespace_exists(api_client, namespace_name):
    logging.debug(f"Checking for namespace: {namespace_name}.")

    try:
        v1 = client.CoreV1Api(api_client)
        v1.read_namespace(name=namespace_name)
        logging.debug(f"Namespace {namespace_name} exists.")
        return True
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return False
        else:
            raise


def check_resources_deployed(api_client, namespace_name):
    logging.debug(f"Checking for namespace: {namespace_name}.")

    v1 = client.CoreV1Api(api_client)

    try:
        v1.read_namespace(name=namespace_name)
        logging.debug(f"Namespace {namespace_name} exists.")

    except client.exceptions.ApiException as e:
        if e.status == 404:
            return False
        else:
            raise

    try:
        pod_list = v1.list_namespaced_pod(namespace_name)
        if len(pod_list.items) > 0:
            return True
        else:
            return False
    except Exception as e:
        logging.error(str(e))
        raise (e)


def check_pods_are_ready(api_client, namespace_name):
    pods_ready = False
    v1 = client.CoreV1Api(api_client)
    pod_list = v1.list_namespaced_pod(namespace_name)
    for pod in pod_list.items:
        if pod.status.phase == "Running":
            pods_ready = True
            break
    return pods_ready


def download_and_config_admissions_controller_manifest():

    # download node sensor manifest
    urllib.request.urlretrieve(FALCON_ADMISSION_CONTROLLER_URL, "admission_controller_manifest.yaml")

    # convert to json
    with open("admission_controller_manifest.yaml", "r") as yaml_file:
        manifest = yaml.safe_load(yaml_file)

    # replace username and password
    manifest["spec"]["falcon_api"]["client_id"] = FALCON_CLIENT_ID
    manifest["spec"]["falcon_api"]["client_secret"] = FALCON_CLIENT_SECRET

    # change registry to crowdstrike
    manifest["spec"]["registry"]["type"] = "crowdstrike"

    # convert back to yaml and write file
    manifest_yaml = yaml.dump(manifest)
    with open("admission_controller_manifest.yaml", "w") as yaml_file:
        yaml_file.write(manifest_yaml)

    return manifest


def download_operator_manifest():
    urllib.request.urlretrieve(FALCON_OPERATOR_URL, "falcon_operator.yaml")

    with open("falcon_operator.yaml", "r") as yaml_file:
        manifest = yaml_file.read()

    return manifest


def deploy_operator(api_client):
    # Check if namespace already exists
    if check_resources_deployed(api_client, "falcon-operator"):
        logging.info("Pod resources exist... Skipping deployment")

    else:
        try:
            # deploy manifest
            logging.info("Deploying Falcon operator")

            utils.create_from_yaml(api_client, yaml_file="falcon_operator.yaml")
        except Exception as e:
            logging.error(e)
            raise (e)

    # Check if pods are ready
    logging.info("Checking to see if pods in falcon-operator are ready.")

    pods_ready = check_pods_are_ready(api_client=api_client, namespace_name="falcon-operator")

    while not pods_ready:
        logging.info(f"Pods are not yet ready. Sleeping for {POD_READY_STATE_SECONDS_TO_SLEEP} seconds")

        time.sleep(POD_READY_STATE_SECONDS_TO_SLEEP)

        pods_ready = check_pods_are_ready(api_client=api_client, namespace_name="falcon-operator")

    if pods_ready:
        logging.info(f"Pods are in ready state. Proceeding with deployment.")


def deploy_node_sensor(api_client, manifest_json):

    dynamic_client = dynamic.DynamicClient(api_client)
    # Check if namespace already exists
    if check_resources_deployed(api_client, "falcon-system"):
        logging.info("Pod resources exist... Skipping deployment")

    else:
        try:
            logging.info("Deploying node sensor")
            nodesensor_api = dynamic_client.resources.get(
                api_version="falcon.crowdstrike.com/v1alpha1", kind="FalconNodeSensor"
            )
            nodesensor_api.create(body=manifest_json, namespace="falcon-operator")
        except Exception as e:
            logging.error(e)
            raise (e)

    # Check if pods are ready
    logging.info("Checking to see if pods in falcon-system are ready.")

    pods_ready = check_pods_are_ready(api_client=api_client, namespace_name="falcon-system")

    while not pods_ready:
        logging.info(f"Pods are not yet ready. Sleeping for {POD_READY_STATE_SECONDS_TO_SLEEP} seconds")

        time.sleep(POD_READY_STATE_SECONDS_TO_SLEEP)

        pods_ready = check_pods_are_ready(api_client=api_client, namespace_name="falcon-system")

    if pods_ready:
        logging.info(f"Pods are in ready state. Proceeding with deployment.")


def deploy_falcon_admissions_controller(api_client, manifest_json):

    dynamic_client = dynamic.DynamicClient(api_client)

    if check_resources_deployed(api_client, "falcon-kac"):
        logging.info("Pod resources exist... Skipping deployment")

    else:
        try:
            logging.info("Deploying admission controller")
            admissions_controller_api = dynamic_client.resources.get(
                api_version="falcon.crowdstrike.com/v1alpha1", kind="FalconAdmission"
            )
            admissions_controller_api.create(body=manifest_json, namespace="falcon-operator")
        except Exception as e:
            logging.error(e)
            raise (e)

    # Check if pods are ready
    logging.info("Checking to see if pods in falcon-kac are ready.")

    pods_ready = check_pods_are_ready(api_client=api_client, namespace_name="falcon-kac")

    while not pods_ready:
        logging.info(f"Pods are not yet ready. Sleeping for {POD_READY_STATE_SECONDS_TO_SLEEP} seconds")

        time.sleep(POD_READY_STATE_SECONDS_TO_SLEEP)

        pods_ready = check_pods_are_ready(api_client=api_client, namespace_name="falcon-kac")

    if pods_ready:
        logging.info(f"Pods are in ready state. Proceeding with deployment.")
