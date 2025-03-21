variable "deployment_project_id" {
  type = string
}

variable "location" {
  type = string
}

variable "service_account_email" {
  type = string
}

variable "falcon_client_id" {
  type = string
  sensitive = true
}

variable "falcon_client_secret" {
  type = string
  sensitive = true
}

variable "scope" {
  type = string

  validation {
    condition     = contains(["organization", "project", "folder"], var.scope)
    error_message = "Scope must be one of \"organization\", \"project\", or \"folder\""
  }

}

variable "scope_identifier" {
  type = string
}