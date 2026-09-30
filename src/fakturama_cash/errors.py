class ReviewRequired(RuntimeError):
    """A failed guard; callers must not continue with another business write."""

    def __init__(self, reason, *, stage="validation", expected=None, observed=None,
                 next_action="Inspect the evidence and correct the issue before a new controlled run."):
        super().__init__(reason)
        self.details = dict(stage=stage, reason=reason, expected=expected,
                            observed=observed, safe_next_action=next_action)
