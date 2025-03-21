# Create a feed that sends notifications about network resource updates under a
# particular organization.

# Find the project number of the project whose identity will be used for sending
# the asset change notifications.
data "google_project" "project" {
  project_id = var.deployment_project_id
}