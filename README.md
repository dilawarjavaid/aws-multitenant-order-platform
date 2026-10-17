# Multi-Tenant Order Platform

An AWS-oriented SaaS reference implementation for retailers to manage
orders with tenant isolation and reliable asynchronous processing.

## Business scenario

Multiple retailers share the platform. Each retailer can access only its
own orders. Accepted orders progress through inventory reservation,
simulated payment, and completion.

## Planned capabilities

- Tenant isolation and role-based access
- Order API built with Python and FastAPI
- PostgreSQL persistence and transactional outbox
- Asynchronous workers with idempotency and retries
- Automated tests and CI
- Local development with Docker Compose
- AWS infrastructure defined with Terraform
- Observability and recovery exercises

## Delivery approach

Build and verify a complete local workflow first, then deploy to AWS.

## Project status

Initial setup. Application functionality is not implemented yet.