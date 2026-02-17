# API Reference

Auto-generated documentation for the `fastapi_sendparcel` package.

## Public API

```{autodoc2-summary}
fastapi_sendparcel
```

## Configuration

```{autodoc2-object} fastapi_sendparcel.config.SendparcelConfig
```

## Router factory

```{autodoc2-object} fastapi_sendparcel.router.create_shipping_router
```

## Plugin registry

```{autodoc2-object} fastapi_sendparcel.registry.FastAPIPluginRegistry
```

## Protocols

```{autodoc2-object} fastapi_sendparcel.protocols.CallbackRetryStore
```

## Schemas

```{autodoc2-object} fastapi_sendparcel.schemas.CreateShipmentRequest
```

```{autodoc2-object} fastapi_sendparcel.schemas.ShipmentResponse
```

```{autodoc2-object} fastapi_sendparcel.schemas.CallbackResponse
```

## Dependencies

```{autodoc2-object} fastapi_sendparcel.dependencies.get_config
```

```{autodoc2-object} fastapi_sendparcel.dependencies.get_repository
```

```{autodoc2-object} fastapi_sendparcel.dependencies.get_registry
```

```{autodoc2-object} fastapi_sendparcel.dependencies.get_flow
```

## SQLAlchemy contrib

### Models

```{autodoc2-object} fastapi_sendparcel.contrib.sqlalchemy.models.ShipmentModel
```

```{autodoc2-object} fastapi_sendparcel.contrib.sqlalchemy.models.CallbackRetryModel
```

### Repository

```{autodoc2-object} fastapi_sendparcel.contrib.sqlalchemy.repository.SQLAlchemyShipmentRepository
```

### Retry store

```{autodoc2-object} fastapi_sendparcel.contrib.sqlalchemy.retry_store.SQLAlchemyRetryStore
```
