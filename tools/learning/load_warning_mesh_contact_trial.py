"""Isolated SEARCH authority diagnostic domain with verified mesh contact expansion."""
from . import load_warning_search_authority as previous
from .load_warning_trial import OBSERVATION_VERSION, receipt_fields


VERSION = "nano100_yaw_on_load_warning_900_mesh_contact_v3"
RUNTIME_RECORD = "deliverables/contact_invalid_t04_20261110/runtime.json"
RUNTIME_SHA256 = "d586be6e14e338089937c13b8f2db67fbeff48121b320856c68e7b9e7b601102"


def protocol_config(search_speed_um_s=900):
    return dict(previous.protocol_config(search_speed_um_s), version=VERSION,
                collision_runtime_sha256=RUNTIME_SHA256)


def environment_class():
    class MeshContactEnvironment(previous.environment_class()):
        mesh_contact_version = VERSION

        def __init__(self, profile=None):
            from .runtime import active_package, verify_runtime
            runtime = verify_runtime(active_package())
            if runtime["compatibility_record_sha256"] != RUNTIME_SHA256:
                raise ValueError("Registered mesh contact runtime required")
            super().__init__(profile)

    return MeshContactEnvironment


def session_class(search_speed_um_s=900):
    class MeshContactSession(previous.session_class(search_speed_um_s)):
        def __init__(self, environment):
            if getattr(environment, "mesh_contact_version", None) != VERSION:
                raise TypeError("Registered mesh contact environment required")
            super().__init__(environment)
            self.contract = protocol_config(search_speed_um_s)

    return MeshContactSession
