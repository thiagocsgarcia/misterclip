import pytest

from app import profiles


def test_builtin_profiles_are_valid_and_readonly():
    ps = {p["id"]: p for p in profiles.list_profiles()}
    assert {"gravura-alquimica", "cinematico-sombrio", "cyber-mistico", "pintura-simbolista"} <= ps.keys()
    for p in ps.values():
        profiles.validate(dict(p))
    with pytest.raises(profiles.ProfileError):
        profiles.update("cyber-mistico", {"name": "x"})
    with pytest.raises(profiles.ProfileError):
        profiles.delete("cyber-mistico")


def test_duplicate_edit_delete_user_profile():
    copy = profiles.duplicate("gravura-alquimica", "Minha gravura")
    assert copy["id"] == "minha-gravura" and copy["builtin"] is False
    upd = profiles.update(copy["id"], {"style_prompt": "ink only", "motion": {"animated_ratio": 0.5}})
    assert upd["style_prompt"] == "ink only" and profiles.get(copy["id"])["motion"]["animated_ratio"] == 0.5
    assert profiles.duplicate("gravura-alquimica", "Minha gravura")["id"] == "minha-gravura-2"
    profiles.delete(copy["id"])
    assert profiles.get(copy["id"]) is None


@pytest.mark.parametrize("bad", [{"name": "x"}, {"name": "x", "style_prompt": "y", "params": {"width": 1000, "height": 768}},
                                 {"name": "x", "style_prompt": "y", "motion": {"clip_engine": "foo"}}])
def test_invalid_profiles_rejected(bad):
    with pytest.raises(profiles.ProfileError):
        profiles.validate(bad)
