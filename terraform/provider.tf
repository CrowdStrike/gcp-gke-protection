provider "google" {
  project     = var.deployment_project_id
  region      = "us-central1"
  billing_project       = var.deployment_project_id
  user_project_override = true
}