from __future__ import annotations

import pytest

from kimi_cli.soul.denwarenji import DenwaRenji, DenwaRenjiError, DMail


def test_send_dmail_rejects_unavailable_non_contiguous_checkpoint() -> None:
    denwa_renji = DenwaRenji()
    denwa_renji.set_checkpoints({0, 2})

    with pytest.raises(DenwaRenjiError, match="There is no checkpoint with the given ID"):
        denwa_renji.send_dmail(DMail(message="try missing", checkpoint_id=1))

    assert denwa_renji.fetch_pending_dmail() is None


def test_send_dmail_accepts_available_non_contiguous_checkpoint() -> None:
    denwa_renji = DenwaRenji()
    denwa_renji.set_checkpoints({0, 2})

    dmail = DMail(message="use available", checkpoint_id=2)
    denwa_renji.send_dmail(dmail)

    assert denwa_renji.fetch_pending_dmail() == dmail


def test_set_n_checkpoints_keeps_contiguous_compatibility() -> None:
    denwa_renji = DenwaRenji()
    denwa_renji.set_n_checkpoints(2)

    dmail = DMail(message="use old API", checkpoint_id=1)
    denwa_renji.send_dmail(dmail)

    assert denwa_renji.fetch_pending_dmail() == dmail
