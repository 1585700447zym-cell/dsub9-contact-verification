"""New referee only; reference controller and policy observations are inherited."""
from tools.learning.reference_session import ReferenceSearchSession
from tools.model.layered_task import functional_finish


class LayeredReferenceSession(ReferenceSearchSession):
    def completion_ready(self,row):
        return functional_finish(row,self.finish_criteria)
