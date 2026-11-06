resource "google_project_service" "secretmanager" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_secret_manager_secret" "falcon_client_secret" {
  secret_id = "falcon-client-secret-${random_id.default.hex}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "falcon_client_secret" {
  secret      = google_secret_manager_secret.falcon_client_secret.id
  secret_data = var.falcon_client_secret
}

resource "google_secret_manager_secret_iam_member" "cluster_protection" {
  secret_id = google_secret_manager_secret.falcon_client_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.service_account_email}"
}
