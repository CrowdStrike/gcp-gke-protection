resource "google_cloud_asset_organization_feed" "organization_feed" {
  billing_project = var.deployment_project_id
  org_id          = var.scope_identifier
  feed_id         = "crowdstrike-gke-protection-organization-feed"
  content_type    = "RESOURCE"

  asset_types = [
    "container.googleapis.com/Cluster",
  ]

  feed_output_config {
    pubsub_destination {
      topic = google_pubsub_topic.gke_protection_feed_topic.id
    }
  }

  condition {
    expression = <<-EOT
    !temporal_asset.deleted
    EOT
    title = "event"
    description = "Send notifications on cluster events"
  }

  count = var.scope == "organizations" ? 1 : 0
}

resource "google_cloud_asset_project_feed" "project_feed" {
  project          = var.scope_identifier
  feed_id         = "crowdstrike-gke-protection-project-feed"
  content_type    = "RESOURCE"

  asset_types = [
    "container.googleapis.com/Cluster",
  ]

  feed_output_config {
    pubsub_destination {
      topic = google_pubsub_topic.gke_protection_feed_topic.id
    }
  }

  condition {
    expression = <<-EOT
    !temporal_asset.deleted
    EOT
    title = "event"
    description = "Send notifications on cluster events"
  }
  
  count = var.scope == "projects" ? 1 : 0
}

resource "google_cloud_asset_folder_feed" "folder_feed" {
  billing_project = var.deployment_project_id
  folder          = var.scope_identifier
  feed_id         = "crowdstrike-gke-protection-folder-feed"
  content_type    = "RESOURCE"

  asset_types = [
    "container.googleapis.com/Cluster",
  ]

  feed_output_config {
    pubsub_destination {
      topic = google_pubsub_topic.gke_protection_feed_topic.id
    }
  }

  condition {
    expression = <<-EOT
    !temporal_asset.deleted
    EOT
    title = "event"
    description = "Send notifications on cluster events"
  }
  
  count = var.scope == "folders" ? 1 : 0
}