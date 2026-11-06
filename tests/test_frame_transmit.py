"""The blit decision: unchanged, presenter rectangles, or a full placement."""
import harness  # noqa: F401  (puts the desktop and host SDK on the path)
import main as desk_main


def test_identical_frames_send_nothing():
    rgb = bytes(40 * 20 * 3)
    assert desk_main.frame_transmit(rgb, rgb, 40, 20) == ("unchanged", None)


def test_one_pixel_is_a_rectangle():
    width, height = 40, 20
    prev = bytearray(width * height * 3)
    cur = bytearray(prev)
    cur[0] = 1
    assert desk_main.frame_transmit(bytes(prev), bytes(cur), width, height) == (
        "rects", ((0, 0, 1, 1),))


def test_a_narrow_column_stays_rectangles():
    width, height = 10, 10
    prev = bytearray(width * height * 3)
    cur = bytearray(prev)
    stride = width * 3
    for row in range(8):
        cur[row * stride] = 9
    assert desk_main.frame_transmit(bytes(prev), bytes(cur), width, height) == (
        "rects", ((0, 0, 1, 8),))


def test_two_separated_pixels_stay_two_rectangles():
    width, height = 10, 10
    prev = bytearray(width * height * 3)
    cur = bytearray(prev)
    cur[0] = 1
    cur[(height - 1) * width * 3 + 5 * 3] = 2
    assert desk_main.frame_transmit(bytes(prev), bytes(cur), width, height) == (
        "rects", ((0, 0, 1, 1), (5, 9, 1, 1)))


def test_a_change_past_65_percent_is_a_full_frame():
    width, height = 10, 10
    prev = bytearray(width * height * 3)
    cur = bytearray(prev)
    stride = width * 3
    for row in range(8):
        cur[row * stride:row * stride + stride] = bytes([9]) * stride
    assert desk_main.frame_transmit(bytes(prev), bytes(cur), width, height) == (
        "full", None)


def test_missing_history_is_a_full_frame():
    rgb = bytes(2 * 5 * 3)
    assert desk_main.frame_transmit(None, rgb, 2, 5) == ("full", None)


test_identical_frames_send_nothing()
test_one_pixel_is_a_rectangle()
test_a_narrow_column_stays_rectangles()
test_two_separated_pixels_stay_two_rectangles()
test_a_change_past_65_percent_is_a_full_frame()
test_missing_history_is_a_full_frame()
print("ok")
