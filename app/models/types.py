import uuid
from datetime import timezone
from sqlalchemy import types
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


def ensure_aware(dt):
    """Treat naive datetimes as UTC.

    SQLite ignores DateTime(timezone=True) and returns naive values, while
    Postgres returns aware ones. Normalise before any datetime maths so
    expiry/duration checks never raise TypeError on SQLite.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class GUID(types.TypeDecorator):
    """Platform-independent GUID type.
    
    Uses PostgreSQL's UUID type, otherwise uses CHAR(36).
    """
    impl = types.CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(types.CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return value
        else:
            if isinstance(value, uuid.UUID):
                return str(value)
            return value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return value
        else:
            if isinstance(value, str):
                return uuid.UUID(value)
            return value