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
    condition     = contains(["organizations", "projects", "folders"], var.scope)
    error_message = "Scope must be one of \"organizations\", \"projects\", or \"folders\""
  }

}

variable "scope_identifier" {
  type = string
}