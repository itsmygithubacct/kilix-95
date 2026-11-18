"""Which generation of a face or flame file is opened: the later one where
the tree has it, else the earlier one."""
import os
import tempfile
import harness as H  # noqa: F401
import neuronte_face as N

real = N._ROOT
try:
    with tempfile.TemporaryDirectory(prefix="k95-neuronte-generation-") as tmp:
        N._ROOT = tmp
        weights = os.path.join(tmp, "weights")
        os.makedirs(weights)

        def have(*names):
            for old in os.listdir(weights):
                os.unlink(os.path.join(weights, old))
            for name in names:
                open(os.path.join(weights, name), "wb").close()

        def name(path):
            return os.path.basename(path)

        # Nothing there: the later name, which the caller then finds missing.
        have()
        assert name(N.weight_path(12)) == "neuronte-ui12-v1.nrt"
        assert not os.path.isfile(N.weight_path(12))
        # The slim set.
        have("neuronte-ui12-v1.nrt", "neuronte-ui12-italic-v1.nrt", "neuronte-flame-v1.nrt")
        assert name(N.weight_path(12)) == "neuronte-ui12-v1.nrt"
        assert name(N.weight_path(12, True)) == "neuronte-ui12-italic-v1.nrt"
        assert name(N.newest("neuronte-flame", (1, 0))) == "neuronte-flame-v1.nrt"
        # An earlier tree.
        have("neuronte-ui12-v0.nrt", "neuronte-ui12-italic-v0.nrt", "neuronte-flame-v0.nrt")
        assert name(N.weight_path(12)) == "neuronte-ui12-v0.nrt"
        assert name(N.weight_path(12, True)) == "neuronte-ui12-italic-v0.nrt"
        assert name(N.newest("neuronte-flame", (1, 0))) == "neuronte-flame-v0.nrt"
        # Both: the later one.
        have("neuronte-ui12-v0.nrt", "neuronte-ui12-v1.nrt")
        assert name(N.weight_path(12)) == "neuronte-ui12-v1.nrt"
        # The scalable face has one generation; an italic above 32 has no file.
        assert name(N.weight_path(40)) == "neuronte-ui-large-v0.nrt"
        assert name(N.weight_path(40, True)) == "neuronte-ui40-italic-v1.nrt"
finally:
    N._ROOT = real
print("ok")
