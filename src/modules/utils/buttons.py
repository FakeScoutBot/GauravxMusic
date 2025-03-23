from pytdbot import types

PlayButton = types.ReplyMarkupInlineKeyboard(
    [
        [
            types.InlineKeyboardButton(
                text="▶️ Skip", type=types.InlineKeyboardButtonTypeCallback(b"play_skip")
            ),
            types.InlineKeyboardButton(
                text="⏹️ End", type=types.InlineKeyboardButtonTypeCallback(b"play_stop")
            ),
        ],
        [
            types.InlineKeyboardButton(
                text="⏸️ Pause",
                type=types.InlineKeyboardButtonTypeCallback(b"play_pause"),
            ),
            types.InlineKeyboardButton(
                text="⏯️ Resume",
                type=types.InlineKeyboardButtonTypeCallback(b"play_resume"),
            ),
        ],
    ]
)

PauseButton = types.ReplyMarkupInlineKeyboard(
    [
        [
            types.InlineKeyboardButton(
                text="▶️ Skip", type=types.InlineKeyboardButtonTypeCallback(b"play_skip")
            ),
            types.InlineKeyboardButton(
                text="⏹️ End", type=types.InlineKeyboardButtonTypeCallback(b"play_stop")
            ),
        ],
        [
            types.InlineKeyboardButton(
                text="⏯️ Resume",
                type=types.InlineKeyboardButtonTypeCallback(b"play_resume"),
            ),
        ],
    ]
)

ResumeButton = types.ReplyMarkupInlineKeyboard(
    [
        [
            types.InlineKeyboardButton(
                text="▶️ Skip", type=types.InlineKeyboardButtonTypeCallback(b"play_skip")
            ),
            types.InlineKeyboardButton(
                text="⏹️ End", type=types.InlineKeyboardButtonTypeCallback(b"play_stop")
            ),
        ],
        [
            types.InlineKeyboardButton(
                text="⏸️ Pause",
                type=types.InlineKeyboardButtonTypeCallback(b"play_pause"),
            ),
        ],
    ]
)

SupportButton = types.ReplyMarkupInlineKeyboard(
    [
        [
            types.InlineKeyboardButton(
                text="❄ Channel",
                type=types.InlineKeyboardButtonTypeUrl("https://t.me/+v1ubYvri73owZDk9"),
            ),
            types.InlineKeyboardButton(
                text="✨ Group",
                type=types.InlineKeyboardButtonTypeUrl("https://t.me/+rFrVYWJbaCsxNzRl"),
            ),
        ]
    ]
)

AddMeButton = types.ReplyMarkupInlineKeyboard(
    [
        [
            types.InlineKeyboardButton(
                text="Add me to your group",
                type=types.InlineKeyboardButtonTypeUrl(
                    "https://t.me/FallenBeatzBot?startgroup=true"
                ),
            ),
        ],
        [
            types.InlineKeyboardButton(
                text="❄ Channel",
                type=types.InlineKeyboardButtonTypeUrl("https://t.me/+v1ubYvri73owZDk9"),
            ),
            types.InlineKeyboardButton(
                text="✨ Group",
                type=types.InlineKeyboardButtonTypeUrl("https://t.me/+rFrVYWJbaCsxNzRl"),
            ),
        ],
    ]
)
