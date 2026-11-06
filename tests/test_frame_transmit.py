"""The blit decision: unchanged, a row band, or a full placement."""
import harness  # noqa: F401  (puts the desktop and host SDK on the path)
import main as desk_main


def test_identical_frames_send_nothing():
    rgb = bytes(40 * 20 * 3)
    assert desk_main.frame_transmit(rgb, rgb, 40, 20) == ("unchanged", None)


def test_one_row_is_a_band():
    width, height = 40, 20
    prev = bytearray(width * height * 3)
    cur = bytearray(prev)
    cur[0] = 1
    kind, band = desk_main.frame_transmit(bytes(prev), bytes(cur), width, height)
    assert kind == "band", kind
    assert band == (0, 1), band


def test_a_tall_change_is_a_full_frame():
    width, height = 10, 10
    prev = bytearray(width * height * 3)
    cur = bytearray(prev)
    stride = width * 3
    for row in range(8):
        cur[row * stride] = 9
    assert desk_main.frame_transmit(bytes(prev), bytes(cur), width, height) == (
        "full", None)


def test_missing_history_is_a_full_frame():
    rgb = bytes(2 * 5 * 3)
    assert desk_main.frame_transmit(None, rgb, 2, 5) == ("full", None)


test_identical_frames_send_nothing()
test_one_row_is_a_band()
test_a_tall_change_is_a_full_frame()
test_missing_history_is_a_full_frame()
print("ok")
