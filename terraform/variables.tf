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

variable "falcon_auto_update" {
  type        = string
  default     = "off"
  description = "Falcon sensor auto-update mode (off, normal, force)"

  validation {
    condition     = contains(["off", "normal", "force"], var.falcon_auto_update)
    error_message = "falcon_auto_update must be one of: off, normal, force"
  }
}

variable "falcon_update_policy" {
  type        = string
  default     = ""
  description = "Falcon sensor update policy name from Falcon UI (optional)"
}

variable "falcon_sensor_tags" {
  type        = string
  default     = ""
  description = "Comma-separated sensor grouping tags (e.g., Environment/Production,Team/Security)"
}