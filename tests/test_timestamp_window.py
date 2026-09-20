"""The post-summary timestamp refinement stays near the summarizer's grounded timestamp."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import utils
except ImportError as exc:  # pandas / dotenv are pipeline dependencies, not test dependencies
    utils = None
    _SKIP = f"pipeline dependencies not installed: {exc}"

# The same subject comes up twice, an hour apart.
TRANSCRIPT = [
    {"name": "Manolis Kellis", "seconds": 1104, "time_str": "0:18:24",
     "text": "let us schedule the leadership call with a poll for everyone this week"},
    {"name": "Manolis Kellis", "seconds": 4952, "time_str": "1:22:32",
     "text": "the leadership call poll was confusing so please answer the scheduling poll again"},
]
CONTENT = "Manolis Kellis asks everyone to answer the scheduling poll for the leadership call again."


@unittest.skipIf(utils is None, "pipeline dependencies not installed")
class RematchWindow(unittest.TestCase):
    def test_refinement_cannot_move_a_topic_across_the_meeting(self):
        match = utils.find_best_timestamp_match(CONTENT, "Manolis Kellis", TRANSCRIPT, near_seconds=4960)
        self.assertEqual(match["seconds"], 4952)

    def test_no_candidate_in_the_window_keeps_the_current_timestamp(self):
        self.assertIsNone(
            utils.find_best_timestamp_match(CONTENT, "Manolis Kellis", TRANSCRIPT, near_seconds=3000)
        )

    def test_update_topics_respects_the_window(self):
        topics = [{"topic": "Poll", "speaker": "Manolis Kellis", "content": CONTENT,
                   "timestamp": "1:22:40", "timestamp_seconds": 4960, "video_link": None}]
        utils.update_speaker_timestamps_for_topics(topics, TRANSCRIPT)
        self.assertEqual(topics[0]["timestamp_seconds"], 4952)


if __name__ == "__main__":
    unittest.main()
