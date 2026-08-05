# Security Policy

## Project status

AegisRoute is an early-stage development project. It does not currently provide
authentication, authorization, rate limiting, quotas, or built-in TLS. Do not
deploy it directly to an untrusted network.

Only the latest revision on the default branch receives security fixes.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's private
vulnerability reporting feature. Do not include credentials, exploit details,
or sensitive logs in a public issue.

Include the affected revision, reproduction steps, impact, and any suggested
mitigation. Please allow time for validation and remediation before public
disclosure.

## Secrets

Never commit `.env` files, database dumps, credentials, provider API keys, or
private keys. Use `.env.example` only as a template and replace every
`replace-me` value in the untracked local `.env` file.
