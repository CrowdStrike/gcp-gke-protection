provider "google" {
  project     = var.deployment_project_id
  region      = var.location
  billing_project       = var.deployment_project_id
  user_project_override = true
}