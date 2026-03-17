resource "random_id" "cluster_protection" {
  byte_length = 8
}



# Create ZIP file from function source
data "archive_file" "cluster_protection_function_zip" {
  type        = "zip"
  output_path = "${path.module}/cluster_protection_function-source.zip"
  source_dir  = "${path.module}/functions/cluster_protection"
}

resource "google_storage_bucket_object" "cluster_protection_object" {
  name   = "function-source.${data.archive_file.cluster_protection_function_zip.output_md5}.zip"
  bucket = google_storage_bucket.gke_protection_function_bucket.name
  source = data.archive_file.cluster_protection_function_zip.output_path # Add path to the zipped function source code
}

resource "google_cloudfunctions2_function" "cluster_protection" {
  name        = "gke-protection-cluster-protection-function-${random_id.default.hex}"
  location    = var.location
  description = "Discovers and installs falcon sensor on kubernetes cluster" #TODO create a better description

  build_config {
    runtime     = "python310"
    entry_point = "main"
    source {
      storage_source {
        bucket = google_storage_bucket.gke_protection_function_bucket.name
        object = google_storage_bucket_object.cluster_protection_object.name
      }
    }
 
    
  }

  service_config {
    max_instance_count = 1
    available_memory   = "256M"
    timeout_seconds    = 360
    service_account_email = var.service_account_email
    environment_variables = {
      FALCON_CLIENT_ID      = var.falcon_client_id
      FALCON_CLIENT_SECRET  = var.falcon_client_secret
      FALCON_AUTO_UPDATE    = var.falcon_auto_update
      FALCON_UPDATE_POLICY  = var.falcon_update_policy
      FALCON_SENSOR_TAGS    = var.falcon_sensor_tags
    }
  }

  event_trigger {
    trigger_region = var.location
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.gke_protection_feed_topic.id
    retry_policy   = "RETRY_POLICY_DO_NOT_RETRY"
  }
}

resource "google_cloud_run_service_iam_member" "cluster_protection_member" {
  location = google_cloudfunctions2_function.cluster_protection.location
  service  = google_cloudfunctions2_function.cluster_protection.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "cluster_protection_function_uri" {
  value = google_cloudfunctions2_function.cluster_protection.service_config[0].uri
}