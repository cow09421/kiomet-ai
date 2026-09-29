"""Match summaries must come only from explicit visible result labels."""
import asyncio

from kiomet_ai.browser import BrowserHost, extract_visible_result_summary


def test_extracts_explicit_traditional_chinese_result_fields():
    text = """Session Statistics
佔領的塔 0
擊敗的國王 0
遊戲時長（分鐘） 28
最高分 8
Current Rank
候選人
Next Rank
戰術家
Progress towards 戰術家: 14%"""

    assert extract_visible_result_summary(text) == {
        "captured_towers": 0,
        "defeated_rulers": 0,
        "duration_minutes": 28,
        "high_score": 8,
        "current_rank": "候選人",
        "next_rank": "戰術家",
        "rank_progress_percent": 14,
    }


def test_extracts_values_on_the_line_after_english_labels():
    text = """Session Statistics
Conquered towers
12
Kings defeated
3
Playtime (minutes)
24
High score
6400
Current Rank
Strategist
Next Rank: Marshal
Progress towards Marshal: 62%"""

    summary = extract_visible_result_summary(text)

    assert summary["captured_towers"] == 12
    assert summary["defeated_rulers"] == 3
    assert summary["duration_minutes"] == 24
    assert summary["high_score"] == 6400
    assert summary["current_rank"] == "Strategist"
    assert summary["next_rank"] == "Marshal"
    assert summary["rank_progress_percent"] == 62


def test_does_not_infer_score_or_rank_from_leaderboard_rows():
    text = """Current players
Momentum 12024
Crazy Legs 9031
KITT 6960"""

    assert extract_visible_result_summary(text) is None


def test_missing_labeled_values_remain_unknown():
    summary = extract_visible_result_summary(
        "Session Statistics\nConquered towers\nUNKNOWN\nCurrent Rank\nUNKNOWN")

    assert summary is None


def test_rejects_empty_or_non_text_input():
    assert extract_visible_result_summary("") is None
    assert extract_visible_result_summary(None) is None


def test_result_screen_sensor_publishes_summary_from_visible_dom_text():
    visible_text = """Session Statistics
佔領的塔 0
擊敗的國王 0
遊戲時長（分鐘） 28
最高分 8
Current Rank
候選人"""

    class Page:
        def is_closed(self):
            return False

        async def evaluate(self, _script):
            return {
                "play": True, "friends": False,
                "url": "https://kiomet.com/", "title": "Kiomet",
                "canvas": 1, "text_len": len(visible_text),
                "text_head": visible_text[:400],
                "visible_text": visible_text,
            }

    class Browser:
        def is_connected(self):
            return True

    host = object.__new__(BrowserHost)
    host.game_page = Page()
    host.browser = Browser()
    host._page_generation = 0
    host.guard = lambda: None
    host.game = {
        "state": "IN_MATCH", "match_events": [],
        "match": {"index": 1, "id": "match-1", "state": "IN_MATCH",
                   "started_at": 1.0, "ended_at": None},
    }

    result = asyncio.run(host.sense_game_state())

    assert result["state"] == "RESULT_SCREEN"
    assert result["result_summary"]["captured_towers"] == 0
    assert result["result_summary"]["defeated_rulers"] == 0
    assert result["result_summary"]["duration_minutes"] == 28
    assert result["result_summary"]["high_score"] == 8
    assert result["result_summary"]["match_id"] == "match-1"
    assert result["result_summary"]["source"] == "VISIBLE_UI_DOM_TEXT"
    assert isinstance(result["result_summary"]["captured_at"], float)
