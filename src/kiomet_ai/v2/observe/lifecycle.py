"""Conservative document-local match epochs from ordinary client lifecycle."""
from uuid import uuid4
from ..state import Lifecycle


class MatchLifecycle:
    def __init__(self, document_id):
        self.document_id = document_id
        self.state = Lifecycle.UNKNOWN
        self.identity = None
        self.key = None
        self.join_pending = False
        self.invalidated = False
        self.last_at = None
        self.last_live_at = None
        self.last_live_source = None

    def begin_join(self):
        """Called immediately before an explicitly authorized official Play click."""
        self.identity = None
        self.key = None
        self.join_pending = True
        self.invalidated = False
        self.state = Lifecycle.JOINING
        self.last_live_at = None
        self.last_live_source = None

    def observe(self, raw, at_ms):
        play = (raw.get("play_text") or "").strip()
        key = (raw.get("document_time_origin"),raw.get("player_id"))
        if self.identity and (
            self.last_at is not None and at_ms - self.last_at > 1000 or
            self.last_live_at is not None and at_ms - self.last_live_at > 1000):
            # A missed terminal transition cannot be ruled out from two live polls.
            # Polling unavailable metadata does not extend world continuity.
            self.invalidated = True
            self.identity = None
        self.last_at = at_ms
        if raw.get('transport_mode')=='OFFLINE':
            # Local simulation cannot continue the identity of a network life.
            self.identity=None
            self.invalidated=True
        if raw.get("online") is False or raw.get("transport_connected") is False:
            state = Lifecycle.DISCONNECTED
        elif play in ("Play Again", "再玩一次") and not raw.get("active"):
            state = Lifecycle.RESULT
        elif self.join_pending and not raw.get("active"):
            state = Lifecycle.JOINING
        elif play in ("Play", "開始遊戲", "開始") and not raw.get("active"):
            state = Lifecycle.MENU
        elif (raw.get("active") is True and not play and raw.get("player_id") and
              raw.get("tick") is not None and raw.get("transport_connected") is True):
            state = Lifecycle.IN_MATCH
        else:
            state = Lifecycle.UNKNOWN
        if state in (Lifecycle.MENU,Lifecycle.RESULT):
            self.identity = self.key = None
            self.invalidated = False
            self.last_live_at = None
            self.last_live_source = None
        elif state == Lifecycle.IN_MATCH:
            if self.key is not None and self.key != key:
                self.identity = None
                self.invalidated = False
            if self.identity is None and not self.invalidated:
                # Composite observation epoch, not an official arena/session ID.
                self.identity = f"{self.document_id}:p{raw['player_id']}:{uuid4().hex}"
            self.key = key
            self.join_pending = False
            live_source = (key, raw.get('transport_mode'), raw['tick'])
            if live_source != self.last_live_source:
                # A connected socket and repeated active metadata do not prove
                # that another world update was actually observed.
                self.last_live_at = at_ms
                self.last_live_source = live_source
        self.state = state
        return state, self.identity if state == Lifecycle.IN_MATCH else None
