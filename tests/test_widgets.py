"""Exercise GTK polling and layout callbacks without a display or desktop bus."""
import ast
import json
from pathlib import Path
import queue
import threading
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def widget_class(main_loop):
    # Load the real class without importing optional GTK/Cairo desktop libraries.
    tree = ast.parse((ROOT / '.local/bin/underlight-widgets').read_text())
    definition = next(node for node in tree.body
                      if isinstance(node, ast.ClassDef) and node.name == 'UnderlightWidgets')
    namespace = {'threading': threading, 'GLib': main_loop, 'json': json}
    exec(compile(ast.Module(body=[definition], type_ignores=[]), str(ROOT / '.local/bin/underlight-widgets'), 'exec'), namespace)
    return namespace['UnderlightWidgets']


class WidgetPollingTests(unittest.TestCase):
    def setUp(self):
        self.callbacks = queue.Queue()
        self.main_loop = Mock()
        self.main_loop.idle_add.side_effect = lambda *args: self.callbacks.put(args)
        widgets = widget_class(self.main_loop)
        self.widget = widgets.__new__(widgets)
        self.widget._pending_polls = set()
        self.widget._drive_refresh_requested = False

    def dispatch(self):
        callback, *arguments = self.callbacks.get(timeout=2)
        self.assertIs(callback(*arguments), False)

    def test_slow_query_does_not_block_or_duplicate_and_only_applies_on_main_loop(self):
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        applied = Mock()
        failed = Mock()

        def read():
            entered.set()
            release.wait(timeout=2)
            return ['volume']

        self.widget._poll_in_background('drives', read, applied, failed)
        self.assertTrue(entered.wait(timeout=1))
        duplicate = Mock()
        self.widget._poll_in_background('drives', duplicate, applied, failed)
        duplicate.assert_not_called()
        applied.assert_not_called()
        release.set()
        self.dispatch()
        applied.assert_called_once_with(['volume'])
        failed.assert_not_called()
        self.assertEqual(self.widget._pending_polls, set())

    def test_failed_query_releases_pending_slot_and_can_retry(self):
        failure = OSError('player unavailable')
        read = Mock(side_effect=[failure, 'playing'])
        applied = Mock()
        failed = Mock()
        self.widget._poll_in_background('media', read, applied, failed)
        self.dispatch()
        failed.assert_called_once_with(failure)
        applied.assert_not_called()
        self.widget._poll_in_background('media', read, applied, failed)
        self.dispatch()
        applied.assert_called_once_with('playing')

    def test_player_timeout_is_not_treated_as_confirmed_playback_shutdown(self):
        class BusError(Exception):
            pass

        self.main_loop.Error = BusError
        bus = Mock()
        names = Mock()
        names.unpack.return_value = (['org.mpris.MediaPlayer2.slow'],)
        bus.call_sync.side_effect = [names, BusError('timeout')]
        self.widget._session_bus = Mock(return_value=bus)
        self.widget._media_properties.__func__.__globals__['Gio'] = Mock()
        with self.assertRaisesRegex(BusError, 'timeout'):
            self.widget._media_properties()

    def test_transient_media_error_keeps_existing_panel(self):
        self.widget._media_properties = Mock(side_effect=OSError('bus unavailable'))
        self.widget._apply_media = Mock()
        self.assertIs(self.widget._update_media(), True)
        self.dispatch()
        self.widget._apply_media.assert_not_called()

    def test_unchanged_media_does_not_remap_or_restack_windows(self):
        self.widget._media_visible = True
        for name in ('media_state', 'media_title', 'media_artist', 'media_window', '_queue_restack'):
            setattr(self.widget, name, Mock())
        self.widget._apply_media(('player', 'Playing', 'Song', 'Artist'))
        self.widget.media_title.set_text.assert_called_once_with('Song')
        self.widget.media_window.show_all.assert_not_called()
        self.widget._queue_restack.assert_not_called()
        self.widget._apply_media(None)
        self.widget.media_window.hide.assert_called_once()
        self.widget._queue_restack.assert_called_once()
        self.assertFalse(self.widget._media_visible)

    def test_mount_completion_during_poll_requests_fresh_drive_result(self):
        self.widget._pending_polls.add('drives')
        self.widget._update_drives(force=True)
        self.assertTrue(self.widget._drive_refresh_requested)
        self.widget._pending_polls.clear()
        self.widget._update_drives = Mock()
        self.widget._apply_drives([{'mountpoint': None}])
        self.widget._update_drives.assert_called_once_with(force=True)
        self.assertFalse(self.widget._drive_refresh_requested)

    def test_mount_refresh_is_not_lost_when_old_query_fails(self):
        self.widget._drive_refresh_requested = True
        self.widget.status = Mock()
        self.widget._update_drives = Mock()
        self.widget._drive_poll_failed(OSError('lsblk timed out'))
        self.widget._update_drives.assert_called_once_with(force=True)


if __name__ == '__main__':
    unittest.main()
