# Security Policy

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Report privately using GitHub's private vulnerability reporting:

➡️ **[Report a vulnerability](https://github.com/betz-anthony/ipforge/security/advisories/new)**
(repo **Security** tab → **Advisories** → **Report a vulnerability**)

This opens a private advisory visible only to you and the maintainers.

Please include, where possible:

- A description of the issue and its impact
- Steps to reproduce (or a proof of concept)
- Affected version / commit and deployment type (Docker Compose or Kubernetes)
- Any relevant configuration (which DNS/DHCP providers, auth backend)

### What to expect

- **Acknowledgement** within 72 hours.
- An initial assessment and a remediation or mitigation timeline within 7 days.
- We will keep you updated on progress and coordinate a disclosure date. Credit
  is given to reporters who wish to be named.

## Supported Versions

Security fixes are applied to the latest released version. Run a current
release before reporting; an issue may already be fixed on `master`.

## Scope notes

IPForge manages sensitive infrastructure — DNS/DHCP control credentials (WinRM,
TSIG, cloud API tokens), LDAP bind secrets, JWT/API tokens, and network
topology. Provider and LDAP secrets are encrypted at rest with `SECRET_KEY`
(Fernet); reports involving credential exposure, authentication/authorization
bypass, SSRF via provider endpoints, or RBAC escalation are especially welcome.
