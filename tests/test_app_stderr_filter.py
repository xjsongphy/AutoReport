"""Tests for app-level stderr noise filtering."""

from autoreport.app import _BLOCK_STDERR_PATTERNS


def test_macos_tsm_capslock_noise_is_filtered() -> None:
    line = (
        b"2026-07-06 10:13:44.525 python3[40486:6919406] "
        b"TSM AdjustCapsLockLEDForKeyTransitionHandling - "
        b"_ISSetPhysicalKeyboardCapsLockLED Inhibit"
    )

    assert any(pattern in line for pattern in _BLOCK_STDERR_PATTERNS)
