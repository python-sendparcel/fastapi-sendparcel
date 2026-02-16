# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2025-02-16

### Added

- FastAPI adapter for python-sendparcel
- SQLAlchemy-based `Shipment` model with async support
- `FastAPIShipmentRepository` with SQLAlchemy async sessions
- FastAPI router with shipment creation, callback, and label endpoints
- Pydantic Settings-based configuration (`SendParcelSettings`)
- Example project with Jinja2 templates and shipping simulation UI
- Full test suite (99 tests)
