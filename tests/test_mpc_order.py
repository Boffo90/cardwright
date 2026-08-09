"""
MPC Autofill order files.

The <backs> section went unparsed for a long time, so an imported double-faced
card arrived with no back at all. The XML below matches the shape MPC Autofill
itself exports (see its own ExportXML tests): <backs> entries are keyed by the
same slot numbers the fronts use.
"""

import mpcfill


def _order(fronts, backs="", cardback="cb-id"):
    return f"""<order>
  <details><quantity>3</quantity><stock>(S30) Standard Smooth</stock></details>
  <fronts>{fronts}</fronts>
  {f'<backs>{backs}</backs>' if backs else ''}
  <cardback>{cardback}</cardback>
</order>"""


def _card(cid, slots, name):
    return (f"<card><id>{cid}</id><slots>{slots}</slots>"
            f"<name>{name}</name><query>q</query></card>")


def test_a_double_faced_card_brings_its_back():
    cards, problems = mpcfill.parse_order_xml(_order(
        fronts=_card("front-id", "0", "Delver of Secrets.png"),
        backs=_card("back-id", "0", "Insectile Aberration.png")))
    assert problems == []
    assert len(cards) == 1
    c = cards[0]
    assert c["identifier"] == "front-id"
    assert c["back_identifier"] == "back-id"
    assert "back-id" in c["back_download"]
    assert c["back_name"] == "Insectile Aberration"


def test_a_single_faced_card_has_no_back_key():
    """<cardback> is the shared back and is deliberately not imported: the app
    has its own card-back setting."""
    cards, _ = mpcfill.parse_order_xml(_order(
        fronts=_card("front-id", "0", "Island.png")))
    assert "back_download" not in cards[0]
    assert "back_identifier" not in cards[0]


def test_quantity_is_the_slot_count_and_the_back_is_shared():
    cards, _ = mpcfill.parse_order_xml(_order(
        fronts=_card("front-id", "0,1,2", "Delver of Secrets.png"),
        backs=_card("back-id", "0,1,2", "Insectile Aberration.png")))
    assert len(cards) == 1
    assert cards[0]["qty"] == 3
    assert cards[0]["back_identifier"] == "back-id"


def test_slots_of_one_entry_with_different_backs_are_split():
    """One front entry can cover slots that do not share a back. Letting the
    first slot speak for all of them would silently give copies a back they
    were never assigned."""
    cards, _ = mpcfill.parse_order_xml(_order(
        fronts=_card("front-id", "0,1,2", "Card.png"),
        backs=_card("back-id", "1", "Other Face.png")))
    assert len(cards) == 2
    by_qty = {c["qty"]: c for c in cards}
    assert by_qty[2].get("back_identifier") is None      # slots 0 and 2
    assert by_qty[1]["back_identifier"] == "back-id"     # slot 1


def test_a_missing_backs_section_still_parses():
    cards, problems = mpcfill.parse_order_xml(_order(
        fronts=_card("front-id", "0", "Island.png")))
    assert problems == []
    assert len(cards) == 1


def test_a_back_with_no_id_is_ignored_rather_than_crashing():
    cards, _ = mpcfill.parse_order_xml(_order(
        fronts=_card("front-id", "0", "Island.png"),
        backs="<card><id></id><slots>0</slots><name>x.png</name></card>"))
    assert len(cards) == 1
    assert "back_identifier" not in cards[0]


def test_the_front_is_still_rejected_without_an_id():
    cards, problems = mpcfill.parse_order_xml(_order(
        fronts="<card><id></id><slots>0</slots><name>Island.png</name></card>"))
    assert cards == []
    assert problems and "no image id" in problems[0]
