

# Create ZIP file from function source
data "archive_file" "discover_existing_function_zip" {
  type        = "zip"
  output_path = "${path.module}/discover_existing_function-source.zip"
  source_dir  = "${path.module}/functions/discover_existing"
}

resource "google_storage_bucket_object" "discover_existing_object" {
  name   = "function-source.${data.archive_file.discover_existing_function_zip.output_md5}.zip"
  bucket = google_storage_bucket.gke_protection_function_bucket.name
  source = data.archive_file.discover_existing_function_zip.output_path # Add path to the zipped function source code
}

resource "google_cloudfunctions2_function" "discover_existing" {
  name        = "gke-protection-discover-existing-function-${random_id.default.hex}"
  location    = var.location
  description = "Discovers and installs falcon sensor on kubernetes cluster" #TODO create a better description

  build_config {
    runtime     = "python310"
    entry_point = "main"
    source {
      storage_source {
        bucket = google_storage_bucket.gke_protection_function_bucket.name
        object = google_storage_bucket_object.discover_existing_object.name
      }
    }

  }

  service_config {
    max_instance_count = 1
    available_memory   = "256M"
    timeout_seconds    = 360
    service_account_email = var.service_account_email
    environment_variables = {
    TOPIC_NAME = "${google_pubsub_topic.gke_protection_feed_topic.name}"
    PROJECT_ID = "${var.deployment_project_id}"
    }
  }
}

resource "google_cloud_run_service_iam_member" "member" {
  location = google_cloudfunctions2_function.discover_existing.location
  service  = google_cloudfunctions2_function.discover_existing.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "discover_existing_function_uri" {
  value = google_cloudfunctions2_function.discover_existing.service_config[0].uri
}