"""Best-effort local completion sounds; never change the program's outcome."""


def operator_input_required():
    """Bring a real CMD console forward and sound a short attention tone."""
    try:
        import ctypes
        console = ctypes.windll.kernel32.GetConsoleWindow()
        if console:
            # SetForegroundWindow can be refused by Windows focus-stealing
            # rules. Restore first, then flash the taskbar button as fallback.
            ctypes.windll.user32.ShowWindow(console, 9)  # SW_RESTORE
            if not ctypes.windll.user32.SetForegroundWindow(console):
                ctypes.windll.user32.FlashWindow(console, True)
    except Exception:
        # Windows Terminal and IDE terminals may not expose a foregroundable
        # console HWND. The prompt and attention tone still remain available.
        pass
    try:
        import winsound
        winsound.Beep(660, 100)
        winsound.Beep(880, 140)
    except Exception:
        # Notification support must never interrupt or fail calibration.
        pass


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
