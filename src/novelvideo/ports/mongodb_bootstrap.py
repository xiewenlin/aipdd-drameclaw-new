"""Register the durable ports used by the Vercel/MongoDB runtime."""

from novelvideo.ports.local.audit import NoOpAuditSink
from novelvideo.ports.local.credit_quote import LocalCreditQuote
from novelvideo.ports.local.lifecycle import NoOpLifecycle
from novelvideo.ports.local.release_feed import LocalReleaseFeed
from novelvideo.ports.local.usage import NoOpProviderInstrumentation, NoOpUsageMeter
from novelvideo.ports.mongodb import (
    MongoAuthPort,
    MongoAuthSession,
    MongoCancellationStore,
    MongoProjectAccess,
    MongoProjectRegistry,
    MongoUserModelSettings,
    ensure_mongo_indexes,
)
from novelvideo.ports.registry import get_port, register_port
from novelvideo.ports.serverless_tasks import ServerlessTaskBackend


def register_mongodb_ports() -> None:
    ensure_mongo_indexes()
    register_port("auth", MongoAuthPort())
    register_port("auth_session", MongoAuthSession())
    register_port("user_model_settings", MongoUserModelSettings())
    register_port("project_registry", MongoProjectRegistry())
    register_port("project_access", MongoProjectAccess())
    register_port("usage_meter", NoOpUsageMeter())
    register_port("provider_instrumentation", NoOpProviderInstrumentation())
    register_port("credit_quote", LocalCreditQuote())
    register_port("task_backend", ServerlessTaskBackend())
    register_port("cancellation_store", MongoCancellationStore())
    register_port("audit_sink", NoOpAuditSink())
    register_port("lifecycle", NoOpLifecycle())
    register_port("release_feed", LocalReleaseFeed())
    get_port("provider_instrumentation").install()


__all__ = ["register_mongodb_ports"]
