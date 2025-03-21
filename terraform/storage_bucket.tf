

resource "google_storage_bucket" "gke_protection_function_bucket" {
  name                        = "${random_id.default.hex}-gke-protection-source"
  location                    = "US"
  uniform_bucket_level_access = true
}