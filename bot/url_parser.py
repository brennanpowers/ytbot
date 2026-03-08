import re

YOUTUBE_REGEX = re.compile(
    r'(?:https?://)?(?:(?:www|m|music)\.)?'
    r'(?:youtube\.com/(?:watch\?.*?v=|shorts/|embed/|v/)|youtu\.be/)'
    r'([\w-]{11})'
)


def extract_video_ids(text: str) -> list[str]:
    return list(dict.fromkeys(YOUTUBE_REGEX.findall(text)))
