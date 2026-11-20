"""Background lookups on the sites (album notes and ratings, other artist names, artist photos) stop when
asked: a restore asks, so that it doesn't have to wait for hundreds of albums. Each picks up where it
left off on its next run (after the next scan), so stopping one loses nothing."""

import threading

stop = threading.Event()
