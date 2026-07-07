"""Per-channel state machine: IDLE → ACTIVE → TAIL → IDLE."""
import time
from dataclasses import dataclass, field
from enum import Enum


class State(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    TAIL = "tail"   # signal gone but within silence timeout; stay locked


# Silence must persist this long before releasing a locked channel
TAIL_TIMEOUT_S = 3.0


@dataclass
class ChannelState:
    idx: int
    name: str
    state: State = field(default=State.IDLE, init=False)
    _tail_start: float | None = field(default=None, init=False, repr=False)

    def update(self, is_active: bool, now: float | None = None) -> bool:
        """
        Advance the state machine given whether the FFT currently sees activity.
        Returns True if the state changed (useful for logging transitions).
        """
        if now is None:
            now = time.monotonic()
        old = self.state

        if self.state is State.IDLE:
            if is_active:
                self.state = State.ACTIVE

        elif self.state is State.ACTIVE:
            if not is_active:
                self.state = State.TAIL
                self._tail_start = now

        elif self.state is State.TAIL:
            if is_active:
                self.state = State.ACTIVE
                self._tail_start = None
            elif now - self._tail_start >= TAIL_TIMEOUT_S:  # type: ignore[operator]
                self.state = State.IDLE
                self._tail_start = None

        return self.state is not old

    @property
    def is_receiving(self) -> bool:
        """True while the channel should be demodulated (ACTIVE or TAIL)."""
        return self.state in (State.ACTIVE, State.TAIL)
