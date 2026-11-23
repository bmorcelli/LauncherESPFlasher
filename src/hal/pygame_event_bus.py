"""Shared drain point for pygame's event queue (dev mode only).

pygame.event.get() drains the OS-level event queue. If the keyboard dev
backend and the pointer dev backend each called it independently, whichever
one polled first would silently steal the other's events (a KEYDOWN drained
by the pointer backend's poll is gone forever, and vice versa). Every dev
backend must go through pump()/register() here instead of calling
pygame.event.get() directly.

Push-based on purpose: pump() fans every drained event out to all
registered listeners, so it doesn't matter which backend happens to trigger
the drain in a given loop iteration — everyone still sees everything.
"""
import sys

_listeners = []


def register(listener):
    """listener: callable(event) -> None, invoked for every pygame event
    drained by pump(), for as long as it stays registered."""
    if listener not in _listeners:
        _listeners.append(listener)


def unregister(listener):
    if listener in _listeners:
        _listeners.remove(listener)


def pump():
    """Drains pygame's real event queue and fans each event out to every
    registered listener. Safe to call redundantly from multiple backends
    within the same loop iteration — pygame.event.get() only ever returns
    events that arrived since the previous drain, so a second call in the
    same tick is simply a (cheap) no-op."""
    import pygame
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            sys.exit(0)
        for listener in list(_listeners):
            listener(event)
