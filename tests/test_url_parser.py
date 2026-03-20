from bot.url_parser import extract_video_ids


class TestExtractVideoIds:
    def test_standard_watch_url(self):
        assert extract_video_ids("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == ["dQw4w9WgXcQ"]

    def test_short_url(self):
        assert extract_video_ids("https://youtu.be/dQw4w9WgXcQ") == ["dQw4w9WgXcQ"]

    def test_shorts_url(self):
        assert extract_video_ids("https://youtube.com/shorts/dQw4w9WgXcQ") == ["dQw4w9WgXcQ"]

    def test_embed_url(self):
        assert extract_video_ids("https://youtube.com/embed/dQw4w9WgXcQ") == ["dQw4w9WgXcQ"]

    def test_v_slash_url(self):
        assert extract_video_ids("https://youtube.com/v/dQw4w9WgXcQ") == ["dQw4w9WgXcQ"]

    def test_mobile_url(self):
        assert extract_video_ids("https://m.youtube.com/watch?v=dQw4w9WgXcQ") == ["dQw4w9WgXcQ"]

    def test_music_url(self):
        assert extract_video_ids("https://music.youtube.com/watch?v=dQw4w9WgXcQ") == ["dQw4w9WgXcQ"]

    def test_no_scheme(self):
        assert extract_video_ids("youtube.com/watch?v=dQw4w9WgXcQ") == ["dQw4w9WgXcQ"]

    def test_http_scheme(self):
        assert extract_video_ids("http://youtube.com/watch?v=dQw4w9WgXcQ") == ["dQw4w9WgXcQ"]

    def test_extra_query_params(self):
        assert extract_video_ids("https://youtube.com/watch?v=dQw4w9WgXcQ&t=120") == ["dQw4w9WgXcQ"]

    def test_playlist_url_with_video(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        assert extract_video_ids(url) == ["dQw4w9WgXcQ"]

    def test_multiple_urls(self):
        text = "Check these: https://youtu.be/dQw4w9WgXcQ and https://youtu.be/jNQXAC9IVRw"
        assert extract_video_ids(text) == ["dQw4w9WgXcQ", "jNQXAC9IVRw"]

    def test_deduplicates_same_id(self):
        text = "https://youtu.be/dQw4w9WgXcQ https://youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_video_ids(text) == ["dQw4w9WgXcQ"]

    def test_no_urls(self):
        assert extract_video_ids("just some random text") == []

    def test_empty_string(self):
        assert extract_video_ids("") == []

    def test_id_with_hyphens_and_underscores(self):
        assert extract_video_ids("https://youtu.be/a-B_c1D2e3f") == ["a-B_c1D2e3f"]

    def test_url_embedded_in_text(self):
        text = "hey check this out https://youtu.be/dQw4w9WgXcQ it's great"
        assert extract_video_ids(text) == ["dQw4w9WgXcQ"]

    def test_non_youtube_url_ignored(self):
        assert extract_video_ids("https://vimeo.com/123456789") == []

    def test_too_short_id_ignored(self):
        assert extract_video_ids("https://youtu.be/abc") == []
