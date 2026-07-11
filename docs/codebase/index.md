# Codebase

This folder contains detailed source layout, dependency, port, and naming rules.

* [Source Layout](source-layout.md) - Authoritative description of OMYM2's src/ layout and Feature-oriented Hexagonal Architecture, covering the domain, features, adapters, platform, and shared packages and rules for adding new directories.
* [Dependency Boundaries](dependency-boundaries.md) - Defines OMYM2's dependency direction between adapters, features, domain, and shared layers, the forbidden dependencies, and where business rules must live.
* [Ports And UnitOfWork](ports-uow.md) - Defines OMYM2's scan/stat/snapshot ports, ordered batch capture, one-usecase UnitOfWork resource lifetime, independent transactions, and durable FileEvents.
* [Source Naming](naming.md) - Authoritative Python naming conventions for OMYM2 modules, classes, functions, and constants, including banned vague names and per-layer naming rules for domain, features, and adapters.
* [Web Frontend](web-frontend.md) - Authoritative reference for the Next.js web/ frontend layout, its audited static export build and packaging pipeline into the Python package, and the JSON API boundary between frontend and backend.
