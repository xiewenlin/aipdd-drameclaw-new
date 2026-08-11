"""Local CE port registration."""

from __future__ import annotations

from novelvideo.ports.local.audit import NoOpAuditSink
from novelvideo.ports.local.auth import PostgresAuthPort, PostgresAuthSession
from novelvideo.ports.local.credit_quote import LocalCreditQuote
from novelvideo.ports.local.lifecycle import NoOpLifecycle
from novelvideo.ports.local.project import AllowAllProjectAccess, PostgresProjectRegistry
from novelvideo.ports.local.release_feed import LocalReleaseFeed
from novelvideo.ports.local.tasks import InlineTaskBackend, InMemoryCancellationStore
from novelvideo.ports.local.usage import NoOpProviderInstrumentation, NoOpUsageMeter
from novelvideo.ports.local.user_settings import PostgresUserModelSettings
from novelvideo.ports.registry import get_port, register_port


def register_local_ports() -> None:
    register_port("auth", PostgresAuthPort())
    register_port("auth_session", PostgresAuthSession())
    register_port("user_model_settings", PostgresUserModelSettings())
    register_port("project_registry", PostgresProjectRegistry())
    register_port("project_access", AllowAllProjectAccess())
    register_port("usage_meter", NoOpUsageMeter())
    register_port("provider_instrumentation", NoOpProviderInstrumentation())
    register_port("credit_quote", LocalCreditQuote())
    register_port("task_backend", InlineTaskBackend())
    register_port("cancellation_store", InMemoryCancellationStore())
    register_port("audit_sink", NoOpAuditSink())
    register_port("lifecycle", NoOpLifecycle())
    register_port("release_feed", LocalReleaseFeed())
    get_port("provider_instrumentation").install()
