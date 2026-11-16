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
        # The face above 32 px: the later file, or the earlier where that is
        # all a tree has. An italic above 32 has no file.
        assert name(N.weight_path(40)) == "neuronte-ui-large-latin1-v1.nrt"
        assert N.kind(40) is None
        have("neuronte-ui-large-v0.nrt")
        assert name(N.weight_path(40)) == "neuronte-ui-large-v0.nrt"
        assert N.kind(40) == "large"
        have("neuronte-ui-large-v0.nrt", "neuronte-ui-large-v1.nrt")
        assert name(N.weight_path(40)) == "neuronte-ui-large-v1.nrt"
        assert name(N.weight_path(40, True)) == "neuronte-ui40-italic-v1.nrt"
        assert N.kind(40, True) is None
        # One scaled file draws 17 to 32 px where an em has no file of its own.
        have("neuronte-ui-scaled-v0.nrt", "neuronte-ui12-v1.nrt", "neuronte-ui20-v1.nrt")
        assert name(N.weight_path(24)) == "neuronte-ui-scaled-v0.nrt" and N.kind(24) == "scaled"
        assert name(N.weight_path(17)) == "neuronte-ui-scaled-v0.nrt"
        assert name(N.weight_path(32)) == "neuronte-ui-scaled-v0.nrt"
        assert name(N.weight_path(20)) == "neuronte-ui20-v1.nrt" and N.kind(20) == "pixel"
        assert name(N.weight_path(12)) == "neuronte-ui12-v1.nrt" and N.kind(12) == "pixel"
        assert name(N.weight_path(16)) == "neuronte-ui16-v1.nrt" and N.kind(16) is None
        assert name(N.weight_path(33)) == "neuronte-ui-large-latin1-v1.nrt"
        # Its italic needs the table of italic advances beside it.
        assert name(N.weight_path(24, True)) == "neuronte-ui24-italic-v1.nrt"
        assert N.kind(24, True) is None
        have("neuronte-ui-scaled-v0.nrt", "neuronte-ui-scaled-italic-advances-v0.nrt")
        assert name(N.weight_path(24, True)) == "neuronte-ui-scaled-v0.nrt"
        assert N.kind(24, True) == "scaled"
        # The files with the Latin-1 letters come first, each with its own table.
        have("neuronte-ui-scaled-v0.nrt", "neuronte-ui-scaled-italic-advances-v0.nrt",
             "neuronte-ui-scaled-latin1-v0.nrt", "neuronte-ui-large-v1.nrt",
             "neuronte-ui-large-latin1-v1.nrt")
        assert name(N.weight_path(24)) == "neuronte-ui-scaled-latin1-v0.nrt"
        assert N.kind(24) == "scaled" and N.kind(24, True) is None
        assert name(N.weight_path(40)) == "neuronte-ui-large-latin1-v1.nrt"
        have("neuronte-ui-scaled-latin1-v0.nrt", "neuronte-ui-scaled-latin1-italic-advances-v0.nrt")
        assert name(N.weight_path(24, True)) == "neuronte-ui-scaled-latin1-v0.nrt"
        assert os.path.basename(N._slant_path()) == "neuronte-ui-scaled-latin1-italic-advances-v0.nrt"
        assert N.kind(24, True) == "scaled"
finally:
    N._ROOT = real
print("ok")
