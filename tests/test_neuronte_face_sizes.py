"""Every other packed size, upright and italic, sits where its drawing does.

The crop is the same code at every em, so a few characters that fix the
top, the baseline, the descender and the width are enough here: the full
check of each file is the library's own make test.
"""
import harness as H          # noqa: F401  sets up the desktop path

from apps.wordpad import SIZES
from neuronte_face_check import ITALIC, UPRIGHT, check

FULL = {10, 11, 18} | {int(s) for s in SIZES}   # checked whole elsewhere
CHARS = "Hg|."

for em in UPRIGHT:
    if em not in FULL:
        check(em, chars=CHARS)
for em in ITALIC:
    if em not in FULL:
        check(em, italic=True, chars=CHARS)

print("ok")
