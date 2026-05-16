terraform {
  required_providers {
    restapi = {
      source  = "Mastercard/restapi"
      version = "~> 1.19"
    }
  }
}

variable "ipam_token" {
  description = "IPAM Forge JWT token (generate via POST /api/auth/login)"
  sensitive   = true
}

provider "restapi" {
  uri                  = "https://ipam.example.com/api"
  write_returns_object = true
  headers = {
    Authorization = "Bearer ${var.ipam_token}"
  }
}

# Look up the subnet by CIDR
data "restapi_object" "subnet" {
  path         = "/subnets"
  search_key   = "cidr"
  search_value = "10.0.1.0/24"
}

# Allocate next free IP, register DNS A record and DHCP reservation.
# Re-running terraform apply is safe: hostname "web-01" is the idempotency key.
resource "restapi_object" "web01_ip" {
  path         = "/subnets/${data.restapi_object.subnet.id}/allocate"
  read_path    = "/addresses/{id}"
  destroy_path = "/addresses/{id}"
  id_attribute = "id"

  data = jsonencode({
    hostname      = "web-01"
    mac_address   = "aa:bb:cc:dd:ee:ff"
    register_dns  = true
    dns_zone      = "example.com"
    register_dhcp = true
  })
}

output "web01_address" {
  description = "Allocated IP address for web-01"
  value       = jsondecode(restapi_object.web01_ip.api_data).address
}
