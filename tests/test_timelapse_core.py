import pytest

from timelapse_core import compute_letterbox_layout, compute_target_resolution, natural_sort_key


def test_natural_sort_key_orders_numbers_numerically():
    files = ["img10.jpg", "img2.jpg", "img1.jpg"]
    assert sorted(files, key=natural_sort_key) == ["img1.jpg", "img2.jpg", "img10.jpg"]


def test_natural_sort_key_handles_full_paths():
    files = [
        "/photos/session/IMG_20.jpg",
        "/photos/session/IMG_3.jpg",
        "/photos/session/IMG_100.jpg",
    ]
    assert sorted(files, key=natural_sort_key) == [
        "/photos/session/IMG_3.jpg",
        "/photos/session/IMG_20.jpg",
        "/photos/session/IMG_100.jpg",
    ]


def test_natural_sort_key_is_case_insensitive():
    files = ["Banana.jpg", "apple.jpg"]
    assert sorted(files, key=natural_sort_key) == ["apple.jpg", "Banana.jpg"]


@pytest.mark.parametrize(
    "width, height, resolution_choice, expected",
    [
        # "Full HD"/"4K" denote the longer (horizontal) side - for a landscape photo that's the width.
        (3840, 2160, "Full HD (Smooth playback)", (1920, 1080)),
        (1920, 1080, "4K (High quality)", (3840, 2160)),
        # For a portrait photo, the longer side is applied to the height, not the width.
        (2160, 3840, "Full HD (Smooth playback)", (1080, 1920)),
        (1080, 1920, "4K (High quality)", (2160, 3840)),
        # "720p"/"480p"/"240p" always denote the height (number of rows), regardless of orientation.
        (1920, 1080, "HD (720p)", (1280, 720)),
        (1080, 1920, "HD (720p)", (404, 720)),
        (1000, 750, "Low quality (240p - very small)", (320, 240)),
        # Odd aspect ratio - verifies the result is rounded to even numbers.
        (640, 427, "SD (480p - small)", (718, 480)),
        # Unknown/original choice ("Original") - the original resolution is returned, just rounded to even numbers.
        (101, 51, "Original (May lag pc)", (100, 50)),
    ],
)
def test_compute_target_resolution(width, height, resolution_choice, expected):
    assert compute_target_resolution(width, height, resolution_choice) == expected


def test_compute_target_resolution_result_is_always_even():
    for width in range(97, 105):
        for height in range(97, 105):
            target_width, target_height = compute_target_resolution(width, height, "HD (720p)")
            assert target_width % 2 == 0
            assert target_height % 2 == 0


def test_compute_letterbox_layout_matching_aspect_ratio_fills_canvas():
    # A photo with the same aspect ratio as the canvas - no bars, no offset.
    assert compute_letterbox_layout(1920, 1080, 1280, 720) == (1280, 720, 0, 0)


def test_compute_letterbox_layout_portrait_photo_into_landscape_canvas():
    # A portrait photo into a landscape canvas (e.g. from the first, landscape photo) - bars on the sides (pillarbox).
    new_width, new_height, x_offset, y_offset = compute_letterbox_layout(1080, 1920, 1920, 1080)
    assert (new_width, new_height) == (608, 1080)
    assert y_offset == 0
    assert x_offset == (1920 - 608) // 2


def test_compute_letterbox_layout_landscape_photo_into_portrait_canvas():
    # A landscape photo into a portrait canvas - bars on top/bottom (letterbox).
    new_width, new_height, x_offset, y_offset = compute_letterbox_layout(1920, 1080, 1080, 1920)
    assert (new_width, new_height) == (1080, 608)
    assert x_offset == 0
    assert y_offset == (1920 - 608) // 2


def test_compute_letterbox_layout_never_exceeds_canvas():
    for src_width in range(97, 105):
        for src_height in range(97, 105):
            new_width, new_height, x_offset, y_offset = compute_letterbox_layout(
                src_width, src_height, 100, 100
            )
            assert 1 <= new_width <= 100
            assert 1 <= new_height <= 100
            assert x_offset >= 0
            assert y_offset >= 0
            assert x_offset + new_width <= 100
            assert y_offset + new_height <= 100
