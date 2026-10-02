"""Best-effort local sounds; never change a capture's success or failure."""


def capture_finished(*, success):
    try:
        # Synchronous short tones finish before the CLI exits. No sound files,
        # background process or extra dependency is needed on Windows.
        import winsound
        if success:
            winsound.Beep(880, 150)
            winsound.Beep(1175, 200)
        else:
            winsound.Beep(440, 450)
    except Exception:
        # Missing audio support must not turn saved evidence into a failed run.
        # The terminal's JSON and exit code remain the authoritative outcome.
        pass
