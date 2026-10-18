import sys
from pathlib import Path


def _location(frame, line):
    # Report code locations only, never frame locals, credentials or image data.
    return dict(file=str(Path(frame.f_code.co_filename).resolve()),
                line=line, function=frame.f_code.co_name)


def error_sources(error):
    """Locate the raised error and its underlying cause without dumping a stack."""
    def origin(exc):
        trace = exc.__traceback__
        if trace is None:
            return getattr(exc, '_created_at', None)
        while trace.tb_next is not None:
            trace = trace.tb_next
        return _location(trace.tb_frame, trace.tb_lineno)

    result = {'origin': origin(error)}
    cause, seen = error, {id(error)}
    while True:
        parent = cause.__cause__ or (None if cause.__suppress_context__ else cause.__context__)
        if parent is None or id(parent) in seen:
            break
        seen.add(id(parent))
        cause = parent
    if cause is not error:
        result['cause_origin'] = {**(origin(cause) or {}), 'exception_type': type(cause).__name__}
    return result


class ReviewRequired(RuntimeError):
    """A failed guard; callers must not continue with another business write."""

    def __init__(self, reason, *, stage="validation", expected=None, observed=None,
                 next_action="Inspect the evidence and correct the issue before a new controlled run."):
        super().__init__(reason)
        frame = sys._getframe(1)
        self._created_at = _location(frame, frame.f_lineno)
        del frame
        self._details = dict(stage=stage, reason=reason, expected=expected,
                             observed=observed, safe_next_action=next_action)

    @property
    def details(self):
        # Resolve after raising so re-raises and wrapped errors retain their
        # actual source, rather than pointing at this exception constructor.
        self._details.update(error_sources(self))
        return self._details
