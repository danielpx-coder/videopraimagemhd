import unittest

from video_tools import FFmpegError, VideoInfo, format_timestamp, parse_probe_output, parse_timestamp


class TimestampTests(unittest.TestCase):
    def test_parse_seconds_and_decimal_comma(self):
        self.assertEqual(parse_timestamp("12.5"), 12.5)
        self.assertEqual(parse_timestamp("1,25"), 1.25)

    def test_parse_minute_and_hour_forms(self):
        self.assertEqual(parse_timestamp("02:03.5"), 123.5)
        self.assertEqual(parse_timestamp("01:02:03.250"), 3723.25)

    def test_rejects_invalid_values(self):
        for value in ("", "-1", "1:60", "1:60:00", "1:02:60", "nan", "inf", "1:2:3:4"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_timestamp(value)

    def test_format_timestamp(self):
        self.assertEqual(format_timestamp(0), "00:00:00.000")
        self.assertEqual(format_timestamp(62.345), "00:01:02.345")
        self.assertEqual(format_timestamp(3600), "01:00:00.000")


class ProbeOutputTests(unittest.TestCase):
    def test_reads_resolution_duration_and_frame_rate(self):
        sample = """
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'clip.mp4':
  Duration: 00:01:23.45, start: 0.000000, bitrate: 12000 kb/s
  Stream #0:0(und): Video: h264 (High), yuv420p, 1920x1080, 30 fps, 30 tbr
"""
        self.assertEqual(
            parse_probe_output(sample),
            VideoInfo(width=1920, height=1080, duration=83.45, fps=30.0),
        )

    def test_duration_can_be_unknown(self):
        sample = "Stream #0:0: Video: rawvideo, yuv420p, 640x480, 25 fps"
        self.assertEqual(
            parse_probe_output(sample),
            VideoInfo(width=640, height=480, duration=None, fps=25.0),
        )

    def test_rejects_audio_only_input(self):
        with self.assertRaises(FFmpegError):
            parse_probe_output("Stream #0:0: Audio: aac, 44100 Hz, stereo")

    def test_rejects_video_without_resolution(self):
        with self.assertRaises(FFmpegError):
            parse_probe_output("Stream #0:0: Video: rawvideo, unknown size")


if __name__ == "__main__":
    unittest.main()
