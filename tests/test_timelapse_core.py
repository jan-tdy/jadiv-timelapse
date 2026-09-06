import pytest

from timelapse_core import compute_target_resolution, natural_sort_key


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
        # "Full HD"/"4K" udávajú dlhšiu (vodorovnú) stranu - pri landscape fotke ide o šírku.
        (3840, 2160, "Full HD (Plynulé prehrávanie)", (1920, 1080)),
        (1920, 1080, "4K (Vysoká kvalita)", (3840, 2160)),
        # Pri portrétnej fotke sa dlhšia strana aplikuje na výšku, nie šírku.
        (2160, 3840, "Full HD (Plynulé prehrávanie)", (1080, 1920)),
        (1080, 1920, "4K (Vysoká kvalita)", (2160, 3840)),
        # "720p"/"480p"/"240p" udávajú vždy výšku (počet riadkov), bez ohľadu na orientáciu.
        (1920, 1080, "HD (720p)", (1280, 720)),
        (1080, 1920, "HD (720p)", (404, 720)),
        (1000, 750, "Nízka kvalita (240p - veľmi malé)", (320, 240)),
        # Nepárny pomer strán - overuje zaokrúhlenie výsledku na párne čísla.
        (640, 427, "SD (480p - malé)", (718, 480)),
        # Neznáma/pôvodná voľba ("Originál") - vráti sa pôvodné rozlíšenie, len zarovnané na párne čísla.
        (101, 51, "Originál (Môže sekať pc)", (100, 50)),
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
