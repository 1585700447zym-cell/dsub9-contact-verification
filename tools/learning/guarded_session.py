"""Zero-residual B2 under candidate common guards, never a training permission."""
from .session import EpisodeSession
from .outcome import classify_outcome
from .action import normalized_action


class CandidateEpisodeSession(EpisodeSession):
    def __init__(self, *, environment, controller_factory=None, finish_criteria=None, geometry_checker=None):
        from .guarded_environment import LearningEnvironment
        if not isinstance(environment, LearningEnvironment):
            raise TypeError('Candidate session requires the explicit candidate environment')
        super().__init__(environment=environment, controller_factory=controller_factory,
                         finish_criteria=finish_criteria, geometry_checker=geometry_checker)

    def _post_task_cycle(self, row):
        facts = self.env.guard_facts
        if facts['contact_reasons'] or facts['motion_reasons']:
            # Suppress the legacy cumulative-load classifier, not the physical facts.
            self.guard_latched = True
            reason = 'CONTACT_GUARD' if facts['contact_reasons'] else 'MOTION_VIOLATION'
            if self.stop_time is None:
                self._finish(reason)
            else:
                # Upgrade the reason without extending the already running task
                # observation window. Physical STOPPING has its own event clock.
                self.reason = reason
            self.recovery_state = None
        super()._post_task_cycle(row)

    def adjudicate(self):
        from tools.validation.native313_matrix_audit import actual_stop_pass
        from tools.validation.run_contact_candidate_stop import physical_tail_pass
        e = self.env
        facts = e.guard_facts
        stopped = bool(self.done and e.phase == 'STOPPING' and
                       actual_stop_pass(e.stop_samples, e.events, self.stop_time,
                                        e.data.time, e.config.timestep) and
                       physical_tail_pass(e.stop_samples, e.data.time, e.config.timestep))
        outcome = classify_outcome(simulation_valid=facts['simulation_valid'],
                                   contact_guard=bool(facts['contact_reasons']),
                                   motion_violation=bool(facts['motion_reasons']),
                                   full_success=self.task_finished and self.reason == 'GEOMETRIC_SUCCESS',
                                   physical_stopped=stopped)
        # Candidate tests cannot establish the model-trust premise needed to learn
        # from a finite motion violation. No switch here can bypass that gate.
        outcome.update(valid_for_learning=False, model_scope_qualified=False,
                       training_admitted=False, guard_facts=facts)
        return outcome

    def advance_cycle(self, action4):
        if self._ready and not self.done:
            try:
                normalized_action(action4)
            except ValueError:
                self.env._terminate('INVALID_COMMAND')
                self._cache = None
                self.prepare_cycle()  # Close task and expose a terminal snapshot.
                raise
        result = super().advance_cycle(action4)
        result.outcome = self.adjudicate()
        return result
