"""Entity notifications for optional managers, without refreshing every entity."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.core import callback


class ManagerListeners:
    """Notify only the entities of one optional manager.

    Source events and watchdog ticks change monitoring/curve values but not the
    Modbus snapshot. Updating every coordinator entity for those would rewrite
    hundreds of unrelated states.
    """

    def __init__(self) -> None:
        self._listeners: list[Callable[[], None]] = []

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(update_callback)

        @callback
        def remove() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove

    @callback
    def async_notify(self) -> None:
        for update_callback in list(self._listeners):
            update_callback()
