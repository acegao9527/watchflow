import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import watchflow


class WatchFlowCoreTests(unittest.TestCase):
    def test_parse_douban_wish_items(self):
        html = """
        <div class="item">
          <ul>
            <li class="title">
              <a href="https://movie.douban.com/subject/1234567/">
                <em>流浪地球 / The Wandering Earth</em>
              </a>
            </li>
            <li class="intro">2019 / 中国大陆 / 科幻 / 125分钟</li>
          </ul>
        </div>
        """

        items = watchflow.parse_wish_items_from_html(html)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].subject_id, "1234567")
        self.assertEqual(items[0].main_title, "流浪地球")
        self.assertEqual(items[0].year, "2019")
        self.assertEqual(items[0].media_type, "movie")

    def test_classify_show_from_episode_hint(self):
        self.assertEqual(watchflow.classify_item("漫长的季节", "全12集 / 悬疑", "2023"), "show")

    def test_candidate_score_prefers_year_match(self):
        item = watchflow.WishItem("1", "流浪地球", "流浪地球", "", "2019", "", "movie")

        self.assertGreater(watchflow.candidate_score(item, {"note": "流浪地球 2019 1080p"}), 0)
        self.assertLess(watchflow.candidate_score(item, {"note": "流浪地球2 2023 1080p"}), 0)

    def test_extract_saved_fids_from_known_shapes(self):
        direct = {"task_result": {"data": {"save_as": {"save_as_top_fids": ["a", "b"]}}}}
        nested = {"data": {"task_resp": {"data": {"save_as": {"save_as_top_fids": ["c"]}}}}}

        self.assertEqual(watchflow.extract_saved_fids(direct), ["a", "b"])
        self.assertEqual(watchflow.extract_saved_fids(nested), ["c"])

    def test_apply_overrides(self):
        item = watchflow.WishItem("42", "Some Title", "Some Title", "", "2020", "", "movie")
        updated = watchflow.apply_overrides(
            [item],
            {"42": {"title": "修正标题", "year": "2021", "media_type": "show", "skip": True}},
        )[0]

        self.assertEqual(updated.main_title, "修正标题")
        self.assertEqual(updated.year, "2021")
        self.assertEqual(updated.media_type, "show")
        self.assertTrue(watchflow.is_skipped_by_override(updated, {"42": {"skip": True}}))

    def test_rank_candidates_marks_validation(self):
        item = watchflow.WishItem("1", "流浪地球", "流浪地球", "", "2019", "", "movie")
        old_search = watchflow.search_quark
        old_validate = watchflow.validate_quark_url
        try:
            watchflow.search_quark = lambda cfg, item: [
                {"note": "错误标题 2020", "url": "https://pan.quark.cn/s/bad", "source": "test"},
                {"note": "流浪地球 2019 1080p", "url": "https://pan.quark.cn/s/good", "source": "test"},
            ]
            watchflow.validate_quark_url = lambda url: (True, "ok")

            candidates, reason = watchflow.rank_candidates(watchflow.Config(), item, validate=True, limit=2)
        finally:
            watchflow.search_quark = old_search
            watchflow.validate_quark_url = old_validate

        self.assertEqual(reason, "ok")
        self.assertEqual(candidates[0]["note"], "流浪地球 2019 1080p")
        self.assertTrue(candidates[0]["valid"])
        self.assertEqual(candidates[0]["validation"], "ok")


if __name__ == "__main__":
    unittest.main()
