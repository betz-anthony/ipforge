terraform {
  required_providers {
    ipforge = {
      source  = "betz-anthony/ipforge"
      version = "~> 0.1"
    }
  }
}

variable "ipforge_token" {
  description = "IPForge API token (ipfg_...). Or set the IPFORGE_TOKEN env var."
  type        = string
  sensitive   = true
}

provider "ipforge" {
  url   = "https://ipforge.example.com" # or set IPFORGE_URL
  token = var.ipforge_token             # or set IPFORGE_TOKEN
}

# Look up an existing subnet by CIDR.
data "ipforge_subnet" "app" {
  cidr = "10.0.1.0/24"
}

# Allocate the next free IP for web-01, registering a DNS A record and a DHCP
# reservation. Idempotent by hostname — re-running `terraform apply` is safe.
resource "ipforge_allocation" "web01" {
  subnet_id     = data.ipforge_subnet.app.id
  hostname      = "web-01"
  mac_address   = "aa:bb:cc:dd:ee:ff"
  register_dns  = true
  dns_zone      = "example.com"
  register_dhcp = true
}

output "web01_address" {
  description = "Allocated IP address for web-01"
  value       = ipforge_allocation.web01.address
}
