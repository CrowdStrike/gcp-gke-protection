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

from typing import Any, Dict, List, Optional
from kubernetes.client import ApiClient
from google.cloud.container_v1.types import Cluster


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


def main(data: Dict[str, Any], context: Any) -> None:
    """
    Main function to handle GCP Cloud Function execution for Falcon deployment.

    Args:
        data: Dictionary containing the base64 encoded payload with cluster information
        context: Cloud Function context object

    Raises:
        Exception: If there's an unexpected error during execution
    """

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
        operator_manifest = download_operator_manifest()
        falcon_deployment_manifest = configure_falcon_deployment_manifest(is_autopilot=is_autopilot)

        # get kubernetes clients
        api_client = get_kube_clients(cluster)

        # protect cluster
        deploy_operator(api_client)
        deploy_falcon_manifest(api_client, falcon_deployment_manifest)
        logging.info(f"Cluster {cluster_name} protected.")
        return

    except Exception as e:
        logging.error(f"Unexpected error in main function: {str(e)}")
        raise


def configure_falcon_deployment_manifest(is_autopilot: bool) -> Dict[str, Any]:
    """
    Creates and configures the Falcon deployment manifest.

    Args:
        is_autopilot: Boolean indicating if the cluster is running in autopilot mode

    Returns:
        Dict containing the configured Falcon deployment manifest
    """

    manifest = {
        "apiVersion": "falcon.crowdstrike.com/v1alpha1",
        "kind": "FalconDeployment",
        "metadata": {"name": "falcon-deployment"},
        "spec": {
            "falcon_api": {
                "client_id": FALCON_CLIENT_ID,
                "client_secret": FALCON_CLIENT_SECRET,
                "cloud_region": "us-2",
            },
            "deployAdmissionController": True,
            "deployNodeSensor": True,
            "deployImageAnalyzer": False,
            "deployContainerSensor": False,
        },
    }

    autopilot_config = {
        "backend": "bpf",
        "gke": {"autopilot": True},
        "resources": {"requests": {"cpu": "750m", "memory": "1.5Gi"}},
        "tolerations": [{"effect": "NoSchedule", "operator": "Equal", "key": "kubernetes.io/arch", "value": "amd64"}],
    }

    node_config = {"node": autopilot_config}

    if is_autopilot:
        manifest["spec"]["falconNodeSensor"] = node_config

    # convert back to yaml and write file
    manifest_yaml = yaml.dump(manifest)
    with open("node_sensor_manifest.yaml", "w") as yaml_file:
        yaml_file.write(manifest_yaml)
    return manifest


def check_resources_deployed(api_client: ApiClient, namespace_name: str) -> bool:
    """
    Checks if a Kubernetes namespace exists and pods are running.

    Args:
        api_client: Kubernetes API client
        namespace_name: Name of the namespace to check

    Returns:
        bool: True if namespace exists and pods are running, False otherwise

    Raises:
        ApiException: If there's an API error other than 404
    """

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


def check_pods_are_ready(api_client: ApiClient, namespace_name: str) -> bool:
    """
    Checks if all pods in a namespace are in Running state.

    Args:
        api_client: Kubernetes API client
        namespace_name: Name of the namespace to check

    Returns:
        bool: True if at least one pod is running, False otherwise
    """

    pods_ready = False
    v1 = client.CoreV1Api(api_client)
    pod_list = v1.list_namespaced_pod(namespace_name)
    for pod in pod_list.items:
        if pod.status.phase == "Running":
            pods_ready = True
            break
    return pods_ready


def download_operator_manifest():
    urllib.request.urlretrieve(FALCON_OPERATOR_URL, "falcon_operator.yaml")

    with open("falcon_operator.yaml", "r") as yaml_file:
        manifest = yaml_file.read()

    return manifest


def deploy_operator(api_client: ApiClient) -> None:
    """
    Deploys the Falcon operator to the cluster.

    Args:
        api_client: Kubernetes API client

    Raises:
        Exception: If deployment fails
    """

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


def list_falcon_deployments(api_client: ApiClient) -> List[Dict[str, Any]]:
    """
    Lists all FalconDeployments in the cluster.

    Args:
        api_client: Kubernetes API client

    Returns:
        List of FalconDeployment resources

    Raises:
        ApiException: If there's an API error other than 404
    """

    logging.info("Checking to see if there are existing Falcon deployments")

    custom_api = client.CustomObjectsApi(api_client)

    try:
        falcon_deployments = custom_api.list_cluster_custom_object(
            group="falcon.crowdstrike.com", version="v1alpha1", plural="falcondeployments"
        )

        return falcon_deployments["items"]  # Returns list of FalconDeployments

    except client.exceptions.ApiException as e:
        if e.status == 404:

            return []
        else:
            raise


def deploy_falcon_manifest(api_client: ApiClient, manifest_json: Dict[str, Any]) -> None:
    """
    Deploys a Falcon manifest to the cluster if no existing deployments exist.

    Args:
        api_client: Kubernetes API client
        manifest_json: The Falcon deployment manifest

    Raises:
        Exception: If deployment fails
    """

    custom_api = client.CustomObjectsApi(api_client)
    dynamic_client = dynamic.DynamicClient(api_client)

    # Get list of FalconDeployments
    deployments = list_falcon_deployments(api_client)

    if len(deployments) == 0:
        logging.info("There are no existing Falcon deployments")
        logging.info("Deploying Falcon")
        try:
            falcon_deployment = dynamic_client.resources.get(
                api_version="falcon.crowdstrike.com/v1alpha1", kind="FalconDeployment"
            )
            falcon_deployment.create(body=manifest_json, namespace="falcon-operator")
        except Exception as e:
            logging.error(e)
            raise (e)
    else:
        logging.info("There are existing Falcon deployments. Exiting...")
        return
