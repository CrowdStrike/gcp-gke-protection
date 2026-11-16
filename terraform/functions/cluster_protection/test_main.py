"""Unit tests for cluster protection function payload validation."""

import base64
import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub out GCP/Kubernetes imports that require live credentials so the module
# can be imported in a plain Python environment without any SDK setup.
# ---------------------------------------------------------------------------

def _stub_module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod

# google.cloud.logging
_gcl = _stub_module("google.cloud.logging")
_gcl_client = MagicMock()
_gcl.Client = MagicMock(return_value=_gcl_client)
_stub_module("google.cloud", logging=_gcl)
_stub_module("google", cloud=sys.modules["google.cloud"])

# google.cloud.container_v1
_gcc = _stub_module("google.cloud.container_v1")
_gcct = _stub_module("google.cloud.container_v1.types")
_gcct.Cluster = MagicMock
_gcc.types = _gcct
sys.modules["google.cloud.container_v1"] = _gcc
sys.modules["google.cloud.container_v1.types"] = _gcct

# kubernetes
_k8s = _stub_module("kubernetes")
_k8s_client = _stub_module("kubernetes.client")
_k8s_client.ApiClient = MagicMock
_k8s_utils = _stub_module("kubernetes.utils")
_k8s_dynamic = _stub_module("kubernetes.dynamic")
_k8s.client = _k8s_client
_k8s.utils = _k8s_utils
_k8s.dynamic = _k8s_dynamic

# googleapiclient
_gapi = _stub_module("googleapiclient")
_gapi_disc = _stub_module("googleapiclient.discovery")
_gapi._auth = MagicMock()
sys.modules["googleapiclient.discovery"] = _gapi_disc

# utils (local)
_utils = _stub_module("utils")
_utils.get_cluster = MagicMock()
_utils.get_kube_clients = MagicMock()

# ---------------------------------------------------------------------------
# Now set the env vars the module reads at import time
# ---------------------------------------------------------------------------
os.environ.setdefault("ENV", "LOCAL")
os.environ["FALCON_CLIENT_ID"] = "test-client-id"
os.environ["FALCON_CLIENT_SECRET"] = "test-client-secret"
os.environ["DEPLOYMENT_PROJECT"] = "my-project"

import main  # noqa: E402  (must come after stubs)


def _encode_payload(asset_name: str) -> dict:
    """Return a data dict that main() would receive from a Pub/Sub trigger."""
    payload = {"asset": {"name": asset_name}}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    return {"data": encoded}


class TestParseAssetName(unittest.TestCase):
    """Tests for _parse_asset_name() covering format and project validation."""

    def test_valid_asset_name_returns_parts(self):
        project_id, zone, cluster_name = main._parse_asset_name(
            "//container.googleapis.com/projects/my-project/locations/us-central1-a/clusters/my-cluster"
        )
        self.assertEqual(project_id, "my-project")
        self.assertEqual(zone, "us-central1-a")
        self.assertEqual(cluster_name, "my-cluster")

    def test_regional_location_accepted(self):
        project_id, zone, cluster_name = main._parse_asset_name(
            "//container.googleapis.com/projects/my-project/locations/us-central1/clusters/autopilot-cluster"
        )
        self.assertEqual(project_id, "my-project")
        self.assertEqual(zone, "us-central1")
        self.assertEqual(cluster_name, "autopilot-cluster")

    def test_wrong_project_raises(self):
        with self.assertRaises(ValueError) as ctx:
            main._parse_asset_name(
                "//container.googleapis.com/projects/other-project/locations/us-central1-a/clusters/evil-cluster"
            )
        self.assertIn("other-project", str(ctx.exception))
        self.assertIn("my-project", str(ctx.exception))

    def test_malformed_scheme_raises(self):
        with self.assertRaises(ValueError):
            main._parse_asset_name(
                "//storage.googleapis.com/projects/my-project/locations/us/clusters/x"
            )

    def test_positional_path_string_raises(self):
        # Old-style format that the previous split("/")[N] code accepted
        with self.assertRaises(ValueError):
            main._parse_asset_name(
                "projects/my-project/locations/us-central1-a/clusters/my-cluster"
            )

    def test_empty_string_raises(self):
        with self.assertRaises(ValueError):
            main._parse_asset_name("")

    def test_missing_cluster_segment_raises(self):
        with self.assertRaises(ValueError):
            main._parse_asset_name(
                "//container.googleapis.com/projects/my-project/locations/us-central1-a"
            )

    def test_path_traversal_in_cluster_name_raises(self):
        # A crafted name with "/" inside would exceed the expected segment count
        with self.assertRaises(ValueError):
            main._parse_asset_name(
                "//container.googleapis.com/projects/my-project/locations/us-central1-a/clusters/../../etc"
            )


class TestMainPayloadValidation(unittest.TestCase):
    """Tests for the main() entry point — validates rejection before any GCP call."""

    def setUp(self):
        _utils.get_cluster.reset_mock()
        _utils.get_kube_clients.reset_mock()

    def test_wrong_project_rejected_before_gcp_call(self):
        data = _encode_payload(
            "//container.googleapis.com/projects/attacker-project/locations/us-central1-a/clusters/pwned"
        )
        with self.assertRaises(ValueError):
            main.main(data, None)
        _utils.get_cluster.assert_not_called()

    def test_malformed_asset_name_rejected_before_gcp_call(self):
        data = _encode_payload("not-a-valid-asset-name")
        with self.assertRaises(ValueError):
            main.main(data, None)
        _utils.get_cluster.assert_not_called()

    def test_valid_project_proceeds_to_gcp(self):
        # get_cluster returns a mock cluster; get_kube_clients and downstream
        # calls will also return mocks — we just want to confirm execution
        # passes the validation gate and reaches the cluster status check.
        mock_cluster = MagicMock()
        mock_cluster.status.name = "RUNNING"
        _utils.get_cluster.return_value = mock_cluster

        mock_api_client = MagicMock()
        _utils.get_kube_clients.return_value = mock_api_client

        with patch.object(main, "deploy_operator"), \
             patch.object(main, "ensure_falcon_api_secret"), \
             patch.object(main, "deploy_falcon_manifest"), \
             patch.object(main, "download_operator_manifest", return_value="yaml"), \
             patch.object(main, "configure_falcon_deployment_manifest", return_value={}):
            main.main(
                _encode_payload(
                    "//container.googleapis.com/projects/my-project/locations/us-central1-a/clusters/good-cluster"
                ),
                None,
            )

        _utils.get_cluster.assert_called_once_with(
            cluster_name="good-cluster", zone="us-central1-a", project_id="my-project"
        )


if __name__ == "__main__":
    unittest.main()
