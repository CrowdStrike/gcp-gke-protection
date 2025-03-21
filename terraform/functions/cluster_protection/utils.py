from google.cloud.container_v1 import ClusterManagerClient
import google.cloud.logging
import logging
from google.cloud.container_v1.types import Cluster
from kubernetes import client as client, config, dynamic
import googleapiclient.discovery
from tempfile import NamedTemporaryFile
import base64
import yaml

# client = google.cloud.logging.Client()
# client.setup_logging()


def get_cluster(cluster_name, project_id, zone):
    cluster_path = f"projects/{project_id}/locations/{zone}/clusters/{cluster_name}"
    logging.info(f"Getting cluster information for: {cluster_path}")

    try:
        client = ClusterManagerClient()
        cluster = client.get_cluster(name=cluster_path)
        logging.debug(
            f"Retrieved cluster details: Name={cluster.name}, Status={cluster.status.name}, "
            f"Node Count={cluster.current_node_count}, Location={cluster.location}"
        )
        return cluster
    except Exception as e:
        logging.error(f"Error retrieving cluster information: {str(e)}")
        raise


def token(*scopes):
    credentials = googleapiclient._auth.default_credentials()
    scopes = [f"https://www.googleapis.com/auth/{s}" for s in scopes]
    scoped = googleapiclient._auth.with_scopes(credentials, scopes)
    googleapiclient._auth.refresh_credentials(scoped)
    return scoped.token


def kubernetes_api(cluster):
    config = kubernetes.client.Configuration()
    config.host = f"https://{cluster.control_plane_endpoints_config.dns_endpoint_config.endpoint}"

    config.api_key_prefix["authorization"] = "Bearer"
    config.api_key["authorization"] = token("cloud-platform")

    with NamedTemporaryFile(delete=False) as cert:
        cert.write(base64.decodebytes(cluster.master_auth.cluster_ca_certificate.encode()))
        config.ssl_ca_cert = cert.name

    client = kubernetes.client.ApiClient(configuration=config)
    api = kubernetes.client.CoreV1Api(client)

    return api


def get_kube_clients(cluster):

    SERVER = cluster.endpoint
    CERT = cluster.master_auth.cluster_ca_certificate

    configuration = client.Configuration()

    NAME = cluster.name
    CONFIG = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{"cluster": {"certificate-authority-data": CERT, "server": f"https://{SERVER}"}, "name": NAME}],
        "contexts": [{"context": {"cluster": NAME, "user": NAME}, "name": NAME}],
        "current-context": NAME,
        "preferences": {},
        "users": [
            {
                "name": NAME,
                "user": {
                    "auth-provider": {
                        "name": "gcp",
                        "config": {"scopes": "https://www.googleapis.com/auth/cloud-platform"},
                    },
                },
            }
        ],
    }

    kubeconfig = yaml.safe_load(yaml.dump(CONFIG))

    loader = config.kube_config.KubeConfigLoader(kubeconfig)
    loader.load_and_set(configuration)

    api_client = client.ApiClient(configuration)
    dynamic_client = dynamic.DynamicClient(api_client)

    return api_client
