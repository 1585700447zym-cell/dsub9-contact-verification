"""Report playback must preserve sample identity, pause, and clock continuity."""
import unittest
from tools.usage.report_demo_core import Timeline, checked_payload


class TimelineTests(unittest.TestCase):
    def test_paused_and_resume_without_skipping(self):
        t = Timeline([0., .5, 1., 2.])
        self.assertEqual(t.update(100), 0)
        t.play(100)
        self.assertEqual(t.update(100.7), 1)
        t.pause(100.7)
        self.assertEqual(t.update(200), 1)
        t.play(200)
        self.assertEqual(t.update(200.4), 2)

    def test_change_speed_keeps_current_time(self):
        t = Timeline([0., 1., 2., 3.])
        t.play(10)
        t.set_speed(.5, 11)
        self.assertAlmostEqual(t.position, 1.)
        t.update(13)
        self.assertAlmostEqual(t.position, 2.)

    def test_seek_clamps_and_never_interpolates_pose(self):
        t = Timeline([0., .4, .9])
        t.seek(.7, 1)
        self.assertEqual(t.index, 1)
        t.seek(5, 1)
        self.assertEqual(t.index, 2)
        t.seek(-5, 1)
        self.assertEqual(t.index, 0)

    def test_end_pauses_and_restart_is_paused(self):
        t = Timeline([0., 1.])
        t.play(1)
        t.update(3)
        self.assertTrue(t.paused)
        t.restart(4)
        self.assertEqual(t.index, 0)
        self.assertTrue(t.paused)

    def test_reject_bad_clock_and_speed(self):
        for times in ([], [0, 0], [1, .5], [0, float('nan')]):
            with self.assertRaises(ValueError):
                Timeline(times)
        t = Timeline([0, 1])
        with self.assertRaises(ValueError):
            t.set_speed(0, 0)

    def test_changed_archive_is_rejected(self):
        import hashlib
        b = b'real saved sample'
        self.assertEqual(checked_payload(b, hashlib.sha256(b).hexdigest()), b)
        with self.assertRaises(ValueError):
            checked_payload(b + b' altered', hashlib.sha256(b).hexdigest())


if __name__ == '__main__':
    unittest.main()
