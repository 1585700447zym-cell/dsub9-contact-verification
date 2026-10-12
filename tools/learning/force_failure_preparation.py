"""Preparation-only config and type: deliberately cannot grant execution authority."""
from .admission import canonical
from .bounded_contact import BoundedAdmission, BoundedUpdater
from .fixed_rotation_cycle import fixed_config
from .episode_rules import FORCE_ONLY


def force_config():
    config = fixed_config()
    config['version'] = 'force_only_preparation_v1'
    config['execution']['stop_on'] = [name for name in config['execution']['stop_on'] if name != 'contact_guard'] + [
        'unqualified_contact_guard', 'force_failure_frequency']
    config['execution'].update(preparation_only=True, authorized_dynamic_starts=0,
        authorized_optimizer_calls=0, publication='whole_eligible_guard_clear_or_force_only',
        episode_rules=FORCE_ONLY.version,
        force_failure_stop=dict(consecutive=2, total=3))
    return config


def validate_force_config(config):
    if canonical(config) != canonical(force_config()):
        raise ValueError('Unregistered force-only preparation config')


class ForceUpdater(BoundedUpdater):
    config_validator = staticmethod(validate_force_config)


class ForcePreparationAdmission(BoundedAdmission):
    episode_rules = FORCE_ONLY
    updater_type = ForceUpdater

    def verify(self, case=None):
        raise ValueError('Force-only preparation has no execution admission or budget')
