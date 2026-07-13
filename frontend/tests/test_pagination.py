"""Tests for the PaginationBar widget (ui.widgets.pagination)."""

import pytest

from ui.widgets.pagination import PaginationBar


@pytest.fixture()
def bar(qapp):
    return PaginationBar()


def _spy(signal):
    """Collect signal emissions into a list."""
    received = []
    signal.connect(lambda *args: received.append(args))
    return received


class TestInitialState:
    def test_hidden_on_single_page(self, bar):
        assert not bar.isVisible()

    def test_buttons_disabled_on_single_page(self, bar):
        assert not bar._prev.isEnabled()
        assert not bar._next.isEnabled()


class TestSetState:
    def test_multipage_shows_bar(self, bar):
        bar.set_state(0, 3)
        assert bar.isVisible()

    def test_first_page_disables_prev(self, bar):
        bar.set_state(0, 5)
        assert not bar._prev.isEnabled()
        assert bar._next.isEnabled()

    def test_last_page_disables_next(self, bar):
        bar.set_state(4, 5)
        assert bar._prev.isEnabled()
        assert not bar._next.isEnabled()

    def test_middle_page_enables_both(self, bar):
        bar.set_state(2, 5)
        assert bar._prev.isEnabled()
        assert bar._next.isEnabled()

    def test_label_text(self, bar):
        bar.set_state(1, 4)
        assert "2" in bar._label.text()
        assert "4" in bar._label.text()


class TestNavigation:
    def test_next_emits_signal(self, bar):
        bar.set_state(0, 3)
        received = _spy(bar.page_changed)
        bar._next.click()
        assert len(received) == 1
        assert received[0] == (1,)

    def test_prev_emits_signal(self, bar):
        bar.set_state(2, 3)
        received = _spy(bar.page_changed)
        bar._prev.click()
        assert len(received) == 1
        assert received[0] == (1,)

    def test_next_at_last_page_does_nothing(self, bar):
        bar.set_state(2, 3)
        received = _spy(bar.page_changed)
        bar._next.click()
        assert len(received) == 0

    def test_prev_at_first_page_does_nothing(self, bar):
        bar.set_state(0, 3)
        received = _spy(bar.page_changed)
        bar._prev.click()
        assert len(received) == 0


class TestEdgeCases:
    def test_zero_total_pages_clamped_to_one(self, bar):
        bar.set_state(0, 0)
        assert bar._total == 1
        assert not bar.isVisible()

    def test_negative_total_pages_clamped(self, bar):
        bar.set_state(0, -5)
        assert bar._total == 1
