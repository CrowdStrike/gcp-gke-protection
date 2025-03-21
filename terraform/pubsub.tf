resource "google_pubsub_topic" "gke_protection_feed_topic" {
  name = "crowdstrike-gke-protection-feed-topic"
  message_retention_duration = "86600s"
}

resource "google_project_iam_member" "pubsub_" {
  project = var.deployment_project_id  # Replace with your project ID
  role    = "roles/pubsub.publisher"  # Replace with the desired role
  member  = "serviceAccount:${var.service_account_email}"  # Service account email
}